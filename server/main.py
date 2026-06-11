import asyncio
import json as _json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import Config
from foundation.db import get_pool, apply_schema, close_pool
from foundation.identity import check_consent, SCOPE_AI_INTERACTION
from foundation import metrics as metrics_mod
from foundation.observability import configure_logging, get_logger
from foundation.outbox import relay_loop
from kernel.context import KernelContext
from kernel.orchestrator import Orchestrator
from kernel.router import Router

# ── Module registry ───────────────────────────────────────────────────────────
from modules.moderation_ops.module import ModerationOpsModule
from modules.learner_state.module import LearnerStateModule
from modules.curriculum_graph.module import CurriculumGraphModule
from modules.tutor_runtime.module import TutorRuntimeModule
from modules.practice_engine.module import PracticeEngineModule
from modules.parent_dashboard.module import ParentDashboardModule
from modules.attention_federated.module import AttentionFederatedModule
from modules.puzzle_engine.module import PuzzleEngineModule

configure_logging("INFO")
log = get_logger("parth.main")

# ── Monitor broadcast infrastructure ─────────────────────────────────────────
_monitor_queues: list[asyncio.Queue] = []
_server_start = datetime.utcnow()

def _broadcast(event: dict):
    dead = []
    for q in list(_monitor_queues):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try: _monitor_queues.remove(q)
        except ValueError: pass

# Build module registry
_modules_list = [
    ModerationOpsModule(),
    LearnerStateModule(),
    CurriculumGraphModule(),
    TutorRuntimeModule(),
    PracticeEngineModule(),
    ParentDashboardModule(),
    AttentionFederatedModule(),
    PuzzleEngineModule(),
]
_module_registry = {m.name: m for m in _modules_list}
_router = Router(_module_registry)
_orchestrator = Orchestrator(_router)

app = FastAPI(title="Parth AI Server", version="4.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup():
    await apply_schema()
    asyncio.create_task(relay_loop(interval_ms=200))
    log.info("parth_started", version="4.0.0", modules=list(_module_registry.keys()))


@app.on_event("shutdown")
async def shutdown():
    await close_pool()


# ── Rate limiter ──────────────────────────────────────────────────────────────
_buckets: dict[str, list[float]] = defaultdict(list)


def rate_limit(request: Request):
    ip = request.headers.get("cf-connecting-ip") or (
        request.client.host if request.client else "unknown"
    )
    now = time.time()
    _buckets[ip] = [t for t in _buckets[ip] if now - t < 60]
    if len(_buckets[ip]) >= Config.RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Ek minute ruko! Too many questions at once — try again shortly.",
        )
    _buckets[ip].append(now)


# ── Request / Response models ─────────────────────────────────────────────────
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []
    subject: str = "General"
    grade: int = 6
    learner_id: str = "anonymous"
    learner_name: str = ""
    model: str | None = None
    request_id: str | None = None  # client can supply for idempotency


class ChatResponse(BaseModel):
    response: str
    model: str
    duration_ms: int
    request_id: str


# ── Consent grant request model ───────────────────────────────────────────────
class ConsentGrantRequest(BaseModel):
    guardian_id: str
    child_id: str
    scopes: list[str] = ["ai_interaction", "learner_data", "progress_report"]


# ── Chat endpoint ─────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    _: None = Depends(rate_limit),
):
    # Consent gate — blocks child learners without guardian approval
    consent_ok = await check_consent(req.learner_id, SCOPE_AI_INTERACTION)
    if not consent_ok:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "parental_consent_required",
                "message": (
                    "A parent or guardian must give consent before Parth can begin. "
                    "Please complete onboarding."
                ),
            },
        )

    history = [{"role": m.role, "content": m.content} for m in req.history]
    try:
        result = await _orchestrator.handle(
            learner_id=req.learner_id,
            message=req.message,
            subject=req.subject,
            grade=req.grade,
            history=history,
            model_override=req.model,
            request_id=req.request_id,
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Ollama is not running. Please start it with: ollama serve",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="AI is thinking hard — please try again in a moment!",
        )
    except Exception as e:
        log.error("chat_error", error=str(e))
        raise HTTPException(status_code=503, detail=str(e))

    _broadcast({
        "type":         "interaction",
        "ts":           datetime.utcnow().isoformat(),
        "learner_id":   req.learner_id,
        "learner_name": req.learner_name or "",
        "subject":      req.subject,
        "grade":        req.grade,
        "model":        result["model"],
        "duration_ms":  result["duration_ms"],
        "emotion":      result.get("_emotion", "neutral"),
        "engagement":   result.get("_engagement", 5.0),
        "misconception": result.get("_misconception", ""),
        "distress":     result.get("distress_detected", False),
    })

    return ChatResponse(
        response=result["response"],
        model=result["model"],
        duration_ms=result["duration_ms"],
        request_id=result["request_id"],
    )


# ── Consent grant endpoint ───────────────────────────────────────────────────
@app.post("/consent/grant")
async def consent_grant(req: ConsentGrantRequest):
    """
    Guardian grants consent for a child.
    Body: {"guardian_id": str, "child_id": str, "scopes": [...]}
    Upserts guardian_links row with consent_given=true.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO foundation.guardian_links
                (guardian_id, child_id, consent_given, consent_ts, scope)
            VALUES ($1::uuid, $2::uuid, true, now(), $3)
            ON CONFLICT (guardian_id, child_id) DO UPDATE
                SET consent_given = true,
                    consent_ts    = now(),
                    scope         = $3
            """,
            req.guardian_id,
            req.child_id,
            req.scopes,
        )
    log.info(
        "consent_granted",
        guardian_id=req.guardian_id,
        child_id=req.child_id,
        scopes=req.scopes,
    )
    return {"status": "consent_granted"}


# ── Learner profile endpoint ──────────────────────────────────────────────────
@app.get("/learner/{learner_id}")
async def get_learner(learner_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        profile = await conn.fetchrow(
            "SELECT * FROM learner_state.profiles WHERE learner_id = $1",
            learner_id,
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Learner not found")

        from modules.learner_state.knowledge import weak_concepts, strong_concepts
        weak  = await weak_concepts(conn, learner_id)
        strong = await strong_concepts(conn, learner_id)

        return {
            **dict(profile),
            "weak_concepts": weak,
            "strong_concepts": strong,
        }


# ── Learner psyche endpoint ───────────────────────────────────────────────────
@app.get("/learner/{learner_id}/psyche")
async def get_learner_psyche(learner_id: str):
    from modules.learner_state.psyche import get_psyche, interpret_psyche
    pool = await get_pool()
    async with pool.acquire() as conn:
        psyche = await get_psyche(conn, learner_id)
    return interpret_psyche(psyche)


# ── Erase learner (GDPR / DPDP right to erasure) ─────────────────────────────
@app.delete("/learner/{learner_id}")
async def erase_learner(learner_id: str):
    await _orchestrator.erase_learner(learner_id)
    return {"erased": True, "learner_id": learner_id}


# ── Puzzle engine endpoints ──────────────────────────────────────────────────

class PuzzleResponseRequest(BaseModel):
    learner_id: str
    puzzle_id: str
    response: str
    time_seconds: int = 0
    reached_deeper: bool = False
    grade: int = 6


@app.get("/puzzle/next/{learner_id}")
async def puzzle_next(learner_id: str, grade: int = 6, subject: str = "General"):
    from kernel.context import Event, KernelContext
    pool = await get_pool()
    async with pool.acquire() as conn:
        ctx = KernelContext(
            request_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            learner_id=learner_id,
            subject=subject,
            grade=grade,
            message="",
            db=conn,
        )
        event = Event(
            type="puzzle.next_requested",
            aggregate="learner",
            aggregate_id=learner_id,
            payload={"grade": grade},
        )
        result = await _module_registry["puzzle.engine"].handle(event, ctx)
    return result.data


@app.post("/puzzle/respond")
async def puzzle_respond(req: PuzzleResponseRequest, background_tasks: BackgroundTasks):
    from kernel.context import Event, KernelContext
    pool = await get_pool()
    async with pool.acquire() as conn:
        ctx = KernelContext(
            request_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            learner_id=req.learner_id,
            subject="puzzle",
            grade=req.grade,
            message=req.response,
            db=conn,
        )
        event = Event(
            type="puzzle.response_recorded",
            aggregate="learner",
            aggregate_id=req.learner_id,
            payload={
                "puzzle_id":      req.puzzle_id,
                "response":       req.response,
                "time_seconds":   req.time_seconds,
                "reached_deeper": req.reached_deeper,
            },
        )

        # Persist the raw response
        await conn.execute("""
            INSERT INTO puzzle_engine.responses
                (learner_id, puzzle_id, thinker_id, sphere, level,
                 response_text, time_seconds, reached_deeper)
            SELECT $1,$2,
                   COALESCE((SELECT thinker_id FROM puzzle_engine.responses
                              WHERE puzzle_id=$2 LIMIT 1), 'unknown'),
                   'unknown', 'beginner', $3, $4, $5
        """, req.learner_id, req.puzzle_id, req.response,
             req.time_seconds, req.reached_deeper)

        result = await _module_registry["puzzle.engine"].handle(event, ctx)
    return result.data


@app.get("/puzzle/portrait/{learner_id}")
async def puzzle_portrait(learner_id: str):
    from modules.puzzle_engine.module import _load_portrait, _load_register_state
    from modules.puzzle_engine.register import RegisterState, register_visualisation
    pool = await get_pool()
    async with pool.acquire() as conn:
        portrait = await _load_portrait(conn, learner_id)
        reg_raw = await _load_register_state(conn, learner_id)
    reg = RegisterState(
        learner_id=learner_id,
        probs=reg_raw.get("probs", {}),
        n_messages=reg_raw.get("n_messages", 0),
    )
    return {
        "portrait":   portrait,
        "register":   register_visualisation(reg),
    }


@app.get("/puzzle/bridge/{concept_id}")
async def puzzle_bridge(concept_id: str, learner_id: str | None = None):
    """Return the best conceptual bridge for this concept, personalised to the learner."""
    import json as _j
    from pathlib import Path
    bridges_path = Path(__file__).parent / "data" / "concept_bridges.json"
    bridges = _j.loads(bridges_path.read_text()) if bridges_path.exists() else {}

    if learner_id:
        from modules.puzzle_engine.module import _load_register_state
        from modules.puzzle_engine.register import RegisterState, best_bridge_for_concept
        pool = await get_pool()
        async with pool.acquire() as conn:
            reg_raw = await _load_register_state(conn, learner_id)
        reg = RegisterState(
            learner_id=learner_id,
            probs=reg_raw.get("probs", {}),
            n_messages=reg_raw.get("n_messages", 0),
        )
        bridge = best_bridge_for_concept(concept_id, reg, bridges)
        return {"concept": concept_id, "learner_id": learner_id, "bridge": bridge}

    # No learner — return all bridges for this concept
    return {"concept": concept_id, "bridges": bridges.get(concept_id, {})}


# ── Pilot metrics endpoint ───────────────────────────────────────────────────
@app.get("/metrics/pilot/{learner_id}")
async def pilot_metrics(learner_id: str):
    """Compute and return pilot gate metrics for a learner."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        gates = await metrics_mod.compute_pilot_gates(conn, learner_id)
    return {"learner_id": learner_id, "gates": gates}


# ── Parent dashboard endpoints ────────────────────────────────────────────────
@app.get("/parent/{learner_id}/report")
async def parent_report(learner_id: str):
    from modules.parent_dashboard.module import build_report
    pool = await get_pool()
    async with pool.acquire() as conn:
        report = await build_report(conn, learner_id)
    return report


@app.get("/parent/{learner_id}/alerts")
async def parent_alerts(learner_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT alert_type, message, acknowledged, created_at
            FROM parent_dashboard.alerts
            WHERE learner_id = $1
            ORDER BY created_at DESC
            LIMIT 20
            """,
            learner_id,
        )
        return [dict(r) for r in rows]


# ── Monitor dashboard ─────────────────────────────────────────────────────────
@app.get("/monitor", include_in_schema=False)
async def monitor_ui():
    return FileResponse("static/monitor.html")


@app.get("/monitor/stream")
async def monitor_stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _monitor_queues.append(q)

    async def generate():
        try:
            # Send a heartbeat immediately so the browser knows it connected
            yield f"data: {_json.dumps({'type': 'connected', 'ts': datetime.utcnow().isoformat()})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {_json.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"type\":\"heartbeat\"}\n\n"
        finally:
            try: _monitor_queues.remove(q)
            except ValueError: pass

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/monitor/stats")
async def monitor_stats():
    pool = await get_pool()
    async with pool.acquire() as conn:
        today   = await conn.fetchval(
            "SELECT COUNT(*) FROM learner_state.interactions WHERE created_at > now() - interval '24 hours'"
        ) or 0
        active  = await conn.fetchval(
            "SELECT COUNT(DISTINCT learner_id) FROM learner_state.interactions WHERE created_at > now() - interval '1 hour'"
        ) or 0
        avg_eng = await conn.fetchval(
            "SELECT AVG(engagement) FROM learner_state.interactions WHERE created_at > now() - interval '1 hour'"
        )
        recent  = await conn.fetch(
            """SELECT learner_id, subject, grade, emotion, engagement, misconception,
                      model, duration_ms, created_at
               FROM learner_state.interactions
               ORDER BY created_at DESC LIMIT 30"""
        )
        subject_dist = await conn.fetch(
            """SELECT subject, COUNT(*) as cnt
               FROM learner_state.interactions
               WHERE created_at > now() - interval '24 hours'
               GROUP BY subject ORDER BY cnt DESC"""
        )
        emotion_dist = await conn.fetch(
            """SELECT emotion, COUNT(*) as cnt
               FROM learner_state.interactions
               WHERE created_at > now() - interval '24 hours'
               GROUP BY emotion"""
        )

    uptime_s = int((datetime.utcnow() - _server_start).total_seconds())
    h, rem   = divmod(uptime_s, 3600)
    m, s     = divmod(rem, 60)

    return {
        "today_interactions": int(today),
        "active_learners":    int(active),
        "avg_engagement":     round(float(avg_eng or 5.0), 1),
        "uptime":             f"{h}h {m}m {s}s",
        "live_clients":       len(_monitor_queues),
        "recent":             [dict(r) for r in recent],
        "subject_dist":       [dict(r) for r in subject_dist],
        "emotion_dist":       [dict(r) for r in emotion_dist],
        "ts":                 datetime.utcnow().isoformat(),
    }


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            r = await client.get(f"{Config.OLLAMA_URL}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
        ollama_ok = True
    except Exception:
        models = []
        ollama_ok = False

    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        pg_ok = True
    except Exception:
        pg_ok = False

    from modules.curriculum_graph.graph import _get_collection
    try:
        rag_chunks = _get_collection().count()
    except Exception:
        rag_chunks = 0

    return {
        "status": "ok" if (ollama_ok and pg_ok) else "degraded",
        "version": "4.0.0",
        "ollama": ollama_ok,
        "postgres": pg_ok,
        "default_model": Config.DEFAULT_MODEL,
        "fast_model": Config.FAST_MODEL,
        "available_models": models,
        "rag_chunks": rag_chunks,
        "modules": list(_module_registry.keys()),
        "server_ip": Config.local_ip(),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Investor Demo ────────────────────────────────────────────────────────────
@app.get("/demo")
async def demo_ui():
    return FileResponse("static/demo.html")


# ── Knowledge Graph UI & API ─────────────────────────────────────────────────
@app.get("/graph")
async def graph_ui():
    return FileResponse("static/graph.html")


@app.get("/graph/data")
async def graph_data(learner_id: str | None = None):
    from config import Config
    import json as _json

    mastery_map = {}

    # ── Try Postgres first ────────────────────────────────────────────────
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            concept_rows = await conn.fetch(
                "SELECT id, label, subject, grade_min, grade_max, description, video_ids "
                "FROM curriculum_graph.concepts ORDER BY subject, grade_min"
            )
            if concept_rows:
                edge_rows = await conn.fetch(
                    "SELECT from_id, to_id, type FROM curriculum_graph.concept_edges"
                )
                video_counts = await conn.fetch(
                    "SELECT concept_id, count(*) as cnt FROM curriculum_graph.ka_videos "
                    "WHERE embedded=true GROUP BY concept_id"
                )
                vc_map = {r["concept_id"]: r["cnt"] for r in video_counts}

                if learner_id:
                    mastery_rows = await conn.fetch(
                        "SELECT concept_id, p_mastery FROM learner_state.knowledge WHERE learner_id=$1",
                        learner_id,
                    )
                    mastery_map = {r["concept_id"]: r["p_mastery"] for r in mastery_rows}

                nodes = []
                for r in concept_rows:
                    node = {
                        "id": r["id"], "label": r["label"], "subject": r["subject"],
                        "grade_min": r["grade_min"], "grade_max": r["grade_max"],
                        "description": r["description"],
                        "video_count": vc_map.get(r["id"], 0),
                        "video_ids": list(r["video_ids"] or []),
                    }
                    if learner_id:
                        node["mastery"] = mastery_map.get(r["id"])
                    nodes.append(node)

                edges = [{"source": r["from_id"], "target": r["to_id"], "type": r["type"]} for r in edge_rows]
                return {"nodes": nodes, "edges": edges, "source": "postgres"}
    except Exception:
        pass

    # ── Fallback: JSON file written by ingest script ──────────────────────
    graph_json = Config.DATA_DIR / "concept_graph.json"
    if graph_json.exists():
        data = _json.loads(graph_json.read_text())
        if learner_id:
            try:
                pool = await get_pool()
                async with pool.acquire() as conn:
                    mastery_rows = await conn.fetch(
                        "SELECT concept_id, p_mastery FROM learner_state.knowledge WHERE learner_id=$1",
                        learner_id,
                    )
                    mastery_map = {r["concept_id"]: r["p_mastery"] for r in mastery_rows}
            except Exception:
                pass
            for node in data["nodes"]:
                node["mastery"] = mastery_map.get(node["id"])
        data["source"] = "json_cache"
        return data

    # ── Fallback: hardcoded structure (first run before any ingest) ───────
    from rag.ingest_graph import NCERT_CONCEPTS, NCERT_EDGES
    nodes = [{**c, "video_count": 0, "video_ids": []} for c in NCERT_CONCEPTS]
    edges = [{"source": f, "target": t, "type": tp} for f, t, tp in NCERT_EDGES]
    return {"nodes": nodes, "edges": edges, "source": "hardcoded"}


# ── Model list ────────────────────────────────────────────────────────────────
@app.get("/models")
async def list_models():
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{Config.OLLAMA_URL}/api/tags")
        return r.json()


# ── Shared World (Playground) ────────────────────────────────────────────────

from modules.shared_world.locations import LOCATIONS, PLAYGROUND_PERSONAS, PERSONA_MAP, get_location
from modules.shared_world.chat import generate_response as _world_generate


class WorldArriveRequest(BaseModel):
    learner_id: str
    location_id: str


class WorldChatRequest(BaseModel):
    learner_id: str
    location_id: str
    message: str


_PRESENCE_TTL = "10 minutes"


async def _active_presence(conn, location_id: str) -> list[dict]:
    """Return learners present at a location in the last 10 min."""
    rows = await conn.fetch(
        f"""SELECT learner_id, learner_name, emoji, color FROM shared_world.presence
            WHERE location_id=$1 AND last_seen > now() - interval '{_PRESENCE_TTL}'
            ORDER BY last_seen DESC""",
        location_id,
    )
    return [dict(r) for r in rows]


async def _learner_context_brief(conn, learner_id: str, grade: int, subject: str) -> str:
    """One-line knowledge/affect summary for the group prompt."""
    try:
        knowledge = await conn.fetch(
            "SELECT concept_id, p_mastery FROM learner_state.knowledge "
            "WHERE learner_id=$1 ORDER BY p_mastery DESC LIMIT 3",
            learner_id,
        )
        emotion_row = await conn.fetchrow(
            "SELECT last_emotion, engagement_score FROM learner_state.profiles WHERE learner_id=$1",
            learner_id,
        )
        parts = []
        if knowledge:
            parts.append("knows: " + ", ".join(
                f"{r['concept_id']}({r['p_mastery']:.2f})" for r in knowledge
            ))
        if emotion_row and emotion_row["last_emotion"] not in ("neutral", None):
            parts.append(f"feeling {emotion_row['last_emotion']}")
        return "; ".join(parts) if parts else "new here"
    except Exception:
        return "new here"


@app.get("/world/locations")
async def world_locations():
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = []
        for loc in LOCATIONS.values():
            present = await _active_presence(conn, loc["id"])
            result.append({
                "id": loc["id"],
                "name": loc["name"],
                "emoji": loc["emoji"],
                "tagline": loc["tagline"],
                "bg_from": loc["bg_from"],
                "bg_to": loc["bg_to"],
                "accent": loc["accent"],
                "depth_levels": loc["depth_levels"],
                "present": present,
                "present_count": len(present),
            })
    return result


@app.post("/world/arrive")
async def world_arrive(req: WorldArriveRequest):
    if req.location_id not in LOCATIONS:
        raise HTTPException(status_code=404, detail="Unknown location")
    persona = PERSONA_MAP.get(req.learner_id, {})
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO shared_world.presence
               (learner_id, location_id, learner_name, emoji, color, last_seen)
               VALUES ($1,$2,$3,$4,$5,now())
               ON CONFLICT (learner_id) DO UPDATE
               SET location_id=$2, learner_name=$3, emoji=$4, color=$5, last_seen=now()""",
            req.learner_id,
            req.location_id,
            persona.get("name", req.learner_id),
            persona.get("emoji", "👤"),
            persona.get("color", "#64748b"),
        )
        present = await _active_presence(conn, req.location_id)
        # Fetch recent messages for this location (last 20)
        msgs = await conn.fetch(
            "SELECT learner_id, learner_name, role, content, created_at "
            "FROM shared_world.messages WHERE location_id=$1 "
            "ORDER BY created_at DESC LIMIT 20",
            req.location_id,
        )
    location = LOCATIONS[req.location_id]
    return {
        "location": {k: location[k] for k in ("id","name","emoji","description","wonder_hook","solo_opener","depth_levels","group_bonus")},
        "present": present,
        "messages": list(reversed([dict(m) for m in msgs])),
    }


@app.post("/world/depart")
async def world_depart(req: WorldArriveRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM shared_world.presence WHERE learner_id=$1",
            req.learner_id,
        )
    return {"departed": True}


@app.get("/world/presence/{location_id}")
async def world_presence(location_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        present = await _active_presence(conn, location_id)
        # Also return messages since a given timestamp (for polling)
        msgs = await conn.fetch(
            "SELECT learner_id, learner_name, role, content, created_at "
            "FROM shared_world.messages WHERE location_id=$1 "
            "ORDER BY created_at DESC LIMIT 5",
            location_id,
        )
    return {
        "present": present,
        "recent_messages": list(reversed([dict(m) for m in msgs])),
    }


@app.post("/world/chat")
async def world_chat(req: WorldChatRequest):
    if req.location_id not in LOCATIONS:
        raise HTTPException(status_code=404, detail="Unknown location")

    persona = PERSONA_MAP.get(req.learner_id)
    if not persona:
        raise HTTPException(status_code=400, detail="Unknown learner — use a Playground persona")

    location = LOCATIONS[req.location_id]
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Touch presence so learner stays active
        await conn.execute(
            "UPDATE shared_world.presence SET last_seen=now() WHERE learner_id=$1",
            req.learner_id,
        )

        # Who else is here?
        present_rows = await _active_presence(conn, req.location_id)

        # Build learner dicts for the prompt (include real knowledge context)
        learners = []
        for row in present_rows:
            p = PERSONA_MAP.get(row["learner_id"], {})
            ctx = await _learner_context_brief(conn, row["learner_id"], p.get("grade", 6), p.get("subject", "General"))
            learners.append({
                "id": row["learner_id"],
                "name": row["learner_name"] or row["learner_id"],
                "grade": p.get("grade", 6),
                "subject": p.get("subject", "General"),
                "context": ctx,
            })

        # If somehow speaker not in present list (race condition), add them
        if not any(l["id"] == req.learner_id for l in learners):
            p = persona
            ctx = await _learner_context_brief(conn, req.learner_id, p["grade"], p["subject"])
            learners.append({
                "id": req.learner_id,
                "name": p["name"],
                "grade": p["grade"],
                "subject": p["subject"],
                "context": ctx,
            })

        # Fetch last 12 messages from shared thread as history
        history_rows = await conn.fetch(
            "SELECT learner_id, learner_name, role, content FROM shared_world.messages "
            "WHERE location_id=$1 ORDER BY created_at DESC LIMIT 12",
            req.location_id,
        )
        history = [dict(r) for r in reversed(history_rows)]

        # Store child message
        await conn.execute(
            "INSERT INTO shared_world.messages (location_id, learner_id, learner_name, role, content) "
            "VALUES ($1,$2,$3,'child',$4)",
            req.location_id, req.learner_id, persona["name"], req.message,
        )

    # Generate Parth's response (outside DB transaction)
    try:
        reply = await _world_generate(
            location=location,
            learners=learners,
            new_message=req.message,
            speaker_name=persona["name"],
            history=history,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    async with pool.acquire() as conn:
        # Store Parth's reply
        await conn.execute(
            "INSERT INTO shared_world.messages (location_id, learner_id, learner_name, role, content) "
            "VALUES ($1,'parth','Parth','parth',$2)",
            req.location_id, reply,
        )
        # Final presence snapshot
        present_rows = await _active_presence(conn, req.location_id)

    return {
        "response": reply,
        "present": present_rows,
        "group_size": len(present_rows),
    }


@app.get("/playground", include_in_schema=False)
async def playground_ui():
    return FileResponse("static/playground.html")


# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    ip = Config.local_ip()
    return {
        "name": "Parth AI Server",
        "version": "4.0.0",
        "endpoints": {
            "chat":    f"POST http://{ip}:{Config.PORT}/chat",
            "health":  f"GET  http://{ip}:{Config.PORT}/health",
            "learner": f"GET  http://{ip}:{Config.PORT}/learner/{{id}}",
            "erase":   f"DELETE http://{ip}:{Config.PORT}/learner/{{id}}",
            "alerts":  f"GET  http://{ip}:{Config.PORT}/parent/{{id}}/alerts",
            "docs":    f"GET  http://{ip}:{Config.PORT}/docs",
        },
    }
