import asyncio
import json as _json
import logging
import re
import time
import uuid as _uuid_mod
from collections import defaultdict
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(override=False)

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import Config
from foundation.db import get_pool, apply_schema, close_pool
from foundation.identity import (
    check_consent,
    register_pilot_learner,
    SCOPE_AI_INTERACTION,
)
from foundation import metrics as metrics_mod
from foundation.observability import configure_logging, get_logger
from foundation.outbox import relay_loop
from foundation.iam_schema import apply_iam_schema
from foundation.policy import load_rbac_cache
from modules.iam.routes import router as iam_router
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

# ── Agent trace cache (observer / investor demo) ──────────────────────────────
# In-memory only; bounded per-learner by Config.AGENT_TRACE_HISTORY.
_agent_traces: dict[str, list[dict]] = defaultdict(list)
_TRACE_HISTORY = Config.AGENT_TRACE_HISTORY

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
    allow_headers=["*", "X-Parth-Key", "X-Admin-Key", "Authorization"],
)

from modules.teacher.routes import router as teacher_router
from modules.notify.routes import router as notify_router
from modules.survey.routes import router as survey_router

app.include_router(iam_router)
app.include_router(teacher_router)
app.include_router(notify_router)
app.include_router(survey_router)

# ── Input sanitization ────────────────────────────────────────────────────────
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize(s: str, max_len: int = 200) -> str:
    """Strip control characters and trim to max_len."""
    return _CTRL_RE.sub(" ", s).strip()[:max_len]


# ── Auth middleware ───────────────────────────────────────────────────────────
# Admin-gated paths: require X-Admin-Key header or ?admin_key= query param.
_ADMIN_EXACT = frozenset({
    "/monitor", "/demo", "/mirror", "/graph", "/models",
    "/playground", "/observer", "/onboarding",
})
_ADMIN_PREFIXES = ("/monitor/", "/graph/", "/api/trace/")


def _is_admin_path(path: str) -> bool:
    return path in _ADMIN_EXACT or path.startswith(_ADMIN_PREFIXES)


# Public paths: no auth required.
_PUBLIC_EXACT = frozenset({"/", "/health", "/docs", "/openapi.json", "/redoc"})


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Static assets are always public (admin UIs load from /static/).
    if path.startswith("/static/"):
        return await call_next(request)

    # Fully public — Fly.io health checks, API docs.
    if path in _PUBLIC_EXACT:
        return await call_next(request)

    # Admin-only endpoints.
    if _is_admin_path(path):
        if Config.ADMIN_KEY:
            key = (
                request.headers.get("X-Admin-Key")
                or request.query_params.get("admin_key", "")
            )
            if key != Config.ADMIN_KEY:
                return JSONResponse(
                    {"detail": "Admin access required"},
                    status_code=401,
                )
        return await call_next(request)

    # All other app endpoints — require X-Parth-Key when configured.
    if Config.PARTH_API_KEY:
        key = request.headers.get("X-Parth-Key", "")
        if key != Config.PARTH_API_KEY:
            return JSONResponse(
                {"detail": "Invalid or missing API key"},
                status_code=401,
            )

    return await call_next(request)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup():
    await apply_schema()
    try:
        await apply_iam_schema()
        await load_rbac_cache()
    except Exception as exc:
        # IAM schema errors are non-fatal so the demo keeps working
        log.warning("iam_startup_error", error=str(exc))
    asyncio.create_task(relay_loop(interval_ms=200))
    log.info("parth_started", version="4.0.0", modules=list(_module_registry.keys()))


@app.on_event("shutdown")
async def shutdown():
    await close_pool()


# ── Rate limiter ──────────────────────────────────────────────────────────────
_buckets: dict[str, list[float]] = defaultdict(list)


def rate_limit(request: Request):
    if not Config.RATE_LIMIT_ENABLED:
        return
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


# ── UUID validation ───────────────────────────────────────────────────────────
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _require_uuid(learner_id: str) -> str:
    """Raise 400 if learner_id is not a valid UUID. Returns the id unchanged."""
    if not _UUID_RE.match(learner_id):
        raise HTTPException(status_code=400, detail="Invalid learner ID format")
    return learner_id


# ── Per-learner daily cap ─────────────────────────────────────────────────────

async def _check_daily_cap(learner_id: str) -> None:
    """Raise 429 if this learner has exceeded their daily interaction cap."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM learner_state.interactions "
            "WHERE learner_id=$1 AND created_at > now() - interval '24 hours'",
            learner_id,
        ) or 0
    if count >= Config.DAILY_REQUEST_CAP:
        raise HTTPException(
            status_code=429,
            detail=(
                "Aaj bahut mehnat ki! You've reached today's learning limit — "
                "come back tomorrow. 🌟"
            ),
        )


# ── Background helpers ───────────────────────────────────────────────────────

async def _create_distress_alert(learner_id: str, snippet: str) -> None:
    """Create a parent dashboard alert when distress is detected outside /chat."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO parent_dashboard.alerts
                       (learner_id, alert_type, message)
                   VALUES ($1, 'distress', $2)""",
                learner_id,
                f"Possible distress detected in a puzzle response: {snippet}",
            )
        log.warning("distress_alert_created", learner_id=learner_id)
    except Exception as exc:
        log.warning("distress_alert_failed", error=str(exc))


# ── Request / Response models ─────────────────────────────────────────────────
class Message(BaseModel):
    role: str = Field(..., max_length=20)
    content: str = Field(..., max_length=5000)


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=2000)
    history: list[Message] = Field(default=[], max_length=20)
    subject: str = Field(default="General", max_length=100)
    grade: int = Field(default=6, ge=1, le=12)
    learner_id: str = Field(default="anonymous", max_length=100)
    learner_name: str = Field(default="", max_length=100)
    model: str | None = Field(default=None, max_length=100)
    request_id: str | None = Field(default=None, max_length=100)


class ChatResponse(BaseModel):
    response: str
    model: str
    duration_ms: int
    request_id: str


# ── Consent grant request model ───────────────────────────────────────────────
class ConsentGrantRequest(BaseModel):
    guardian_id: str = Field(..., max_length=100)
    child_id: str = Field(..., max_length=100)
    scopes: list[str] = Field(
        default=["ai_interaction", "learner_data", "progress_report"],
        max_length=10,
    )


# ── Chat endpoint ─────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    _: None = Depends(rate_limit),
):
    _require_uuid(req.learner_id)

    # Consent gate — /learner/register normally creates this row after cold start.
    # Keep pilot auto-registration as a fallback for older clients.
    consent_ok = await check_consent(req.learner_id, SCOPE_AI_INTERACTION)
    if not consent_ok:
        # Try to auto-register and grant consent (pilot / first-run flow)
        try:
            await register_pilot_learner(
                learner_id=req.learner_id,
                name=req.learner_name or "Learner",
                grade=req.grade,
            )
            consent_ok = await check_consent(req.learner_id, SCOPE_AI_INTERACTION)
        except Exception:
            pass
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

    # Per-learner daily cap — cost control
    await _check_daily_cap(req.learner_id)

    # Sanitize subject before it enters the LLM system prompt
    safe_subject = _sanitize(req.subject, max_len=100)

    history = [{"role": m.role, "content": m.content} for m in req.history]
    try:
        result = await _orchestrator.handle(
            learner_id=req.learner_id,
            message=req.message,
            subject=safe_subject,
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

    # ── Agent trace cache (for observer page) ─────────────────────────────
    safe_name = _sanitize(req.learner_name, max_len=100)
    agent_trace = result.get("_agent_trace", {})
    if agent_trace:
        entry = {
            "ts":           datetime.utcnow().isoformat(),
            "learner_id":   req.learner_id,
            "learner_name": safe_name,
            "message":      req.message[:200],
            "response":     result["response"][:300],
            "model":        result["model"],
            "duration_ms":  result["duration_ms"],
            "emotion":      result.get("_emotion", "neutral"),
            "engagement":   result.get("_engagement", 5.0),
            **agent_trace,
        }
        cache = _agent_traces[req.learner_id]
        cache.append(entry)
        if len(cache) > _TRACE_HISTORY:
            _agent_traces[req.learner_id] = cache[-_TRACE_HISTORY:]

    _broadcast({
        "type":         "interaction",
        "ts":           datetime.utcnow().isoformat(),
        "learner_id":   req.learner_id,
        "learner_name": safe_name,
        "subject":      req.subject,
        "grade":        req.grade,
        "model":        result["model"],
        "duration_ms":  result["duration_ms"],
        "emotion":      result.get("_emotion", "neutral"),
        "engagement":   result.get("_engagement", 5.0),
        "misconception": result.get("_misconception", ""),
        "distress":     result.get("distress_detected", False),
        "agent_trace":  agent_trace,
    })

    return ChatResponse(
        response=result["response"],
        model=result["model"],
        duration_ms=result["duration_ms"],
        request_id=result["request_id"],
    )


# ── Consent grant endpoint ───────────────────────────────────────────────────
@app.post("/consent/grant")
async def consent_grant(req: ConsentGrantRequest, _: None = Depends(rate_limit)):
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


# ── Learner registration (pilot — auto-grants consent, no OTP yet) ────────────
class LearnerRegisterRequest(BaseModel):
    learner_id: str = Field(..., max_length=100)
    name: str = Field(..., max_length=100)
    grade: int = Field(..., ge=1, le=12)
    school_id: str | None = Field(None, max_length=100)


@app.post("/learner/register")
async def learner_register(req: LearnerRegisterRequest, _: None = Depends(rate_limit)):
    """
    Register a new learner and auto-grant pilot consent.
    Must be called after cold-start completes and before /chat can be used.
    Idempotent — safe to call multiple times.
    """
    ok = await register_pilot_learner(
        learner_id=req.learner_id,
        name=_sanitize(req.name, max_len=100),
        grade=req.grade,
        school_id=req.school_id,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid learner ID format")
    return {"status": "registered", "learner_id": req.learner_id}


# ── Learner profile endpoint ──────────────────────────────────────────────────
@app.get("/learner/{learner_id}")
async def get_learner(learner_id: str, _: None = Depends(rate_limit)):
    _require_uuid(learner_id)
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


# ── Per-child agent config endpoint ──────────────────────────────────────────
@app.get("/learner/{learner_id}/config")
async def get_learner_config(learner_id: str, _: None = Depends(rate_limit)):
    _require_uuid(learner_id)
    """
    Return the full per-child agent config for a learner:
      - per-agent overrides (from child_agent_config)
      - global settings (from child_global_config)
      - merged view: what each agent will actually see (overrides + schema defaults)
      - onboarding status
    """
    from modules.learner_state.child_config import load as load_config, AGENT_SCHEMA, GLOBAL_SCHEMA
    import json as _j

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Raw overrides
        agent_rows = await conn.fetch(
            "SELECT agent_name, config, set_by, updated_at "
            "FROM learner_state.child_agent_config WHERE learner_id = $1 ORDER BY agent_name",
            learner_id,
        )
        global_row = await conn.fetchrow(
            "SELECT exam_prep_mode, exam_date, max_response_words, session_persona, set_by, updated_at "
            "FROM learner_state.child_global_config WHERE learner_id = $1",
            learner_id,
        )
        onboarding_row = await conn.fetchrow(
            "SELECT status, completed_at FROM learner_state.onboarding WHERE learner_id = $1",
            learner_id,
        )
        # Merged view via ChildConfig
        cfg = await load_config(conn, learner_id)

    raw_agents = {}
    for r in agent_rows:
        raw = r["config"]
        raw_agents[r["agent_name"]] = {
            "overrides":   _j.loads(raw) if isinstance(raw, str) else dict(raw),
            "set_by":      r["set_by"],
            "updated_at":  r["updated_at"].isoformat(),
        }

    # Merged view — what each agent actually receives
    merged = {name: cfg.agent(name) for name in AGENT_SCHEMA}

    return {
        "learner_id":       learner_id,
        "onboarding_status": dict(onboarding_row) if onboarding_row else {"status": "not_started"},
        "global_config":    dict(global_row) if global_row else {},
        "merged_config":    merged,        # full effective config per agent
        "raw_overrides":    raw_agents,    # only what guardian/BMAD explicitly set
    }


# ── Learner psyche endpoint ───────────────────────────────────────────────────
@app.get("/learner/{learner_id}/psyche")
async def get_learner_psyche(learner_id: str, _: None = Depends(rate_limit)):
    _require_uuid(learner_id)
    from modules.learner_state.psyche import get_psyche, interpret_psyche
    pool = await get_pool()
    async with pool.acquire() as conn:
        psyche = await get_psyche(conn, learner_id)
    return interpret_psyche(psyche)


# ── Erase learner (GDPR / DPDP right to erasure) ─────────────────────────────
@app.delete("/learner/{learner_id}")
async def erase_learner(learner_id: str, _: None = Depends(rate_limit)):
    _require_uuid(learner_id)
    await _orchestrator.erase_learner(learner_id)
    return {"erased": True, "learner_id": learner_id}


# ── Puzzle engine endpoints ──────────────────────────────────────────────────

class PuzzleResponseRequest(BaseModel):
    learner_id: str = Field(..., max_length=100)
    puzzle_id: str = Field(..., max_length=100)
    response: str = Field(..., max_length=2000)
    time_seconds: int = Field(default=0, ge=0, le=3600)
    reached_deeper: bool = False
    grade: int = Field(default=6, ge=1, le=12)


@app.get("/puzzle/next/{learner_id}")
async def puzzle_next(
    learner_id: str,
    grade: int = 6,
    subject: str = "General",
    _: None = Depends(rate_limit),
):
    _require_uuid(learner_id)
    grade = max(1, min(12, grade))
    from kernel.context import Event, KernelContext
    pool = await get_pool()
    async with pool.acquire() as conn:
        ctx = KernelContext(
            request_id=str(_uuid_mod.uuid4()),
            trace_id=str(_uuid_mod.uuid4()),
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
async def puzzle_respond(
    req: PuzzleResponseRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(rate_limit),
):
    from kernel.context import Event, KernelContext
    from modules.puzzle_engine import loader
    from modules.moderation_ops.module import moderate_text, _BLOCK_RESPONSE

    _require_uuid(req.learner_id)

    puzzle = loader.get(req.puzzle_id)
    if puzzle is None:
        raise HTTPException(status_code=404, detail="Unknown puzzle")

    # Moderate child's free-text response before persisting
    mod = moderate_text(req.response)
    if mod["harmful_detected"]:
        raise HTTPException(status_code=400, detail=_BLOCK_RESPONSE)
    if mod["distress_detected"]:
        background_tasks.add_task(
            _create_distress_alert, req.learner_id, req.response[:200]
        )

    pool = await get_pool()
    async with pool.acquire() as conn:
        ctx = KernelContext(
            request_id=str(_uuid_mod.uuid4()),
            trace_id=str(_uuid_mod.uuid4()),
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

        result = await _module_registry["puzzle.engine"].handle(event, ctx)

        # Persist the raw response with real puzzle metadata for the portrait path.
        await conn.execute("""
            INSERT INTO puzzle_engine.responses
                (learner_id, puzzle_id, thinker_id, sphere, level,
                 response_text, time_seconds, quality, reached_deeper, misconception)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
        """, req.learner_id, req.puzzle_id,
             puzzle["thinker_id"], puzzle["sphere"], puzzle["level"],
             req.response, req.time_seconds, int(result.data.get("quality", 0)),
             req.reached_deeper, str(result.data.get("misconception", "") or ""))
    return result.data


@app.get("/puzzle/portrait/{learner_id}")
async def puzzle_portrait(learner_id: str, _: None = Depends(rate_limit)):
    _require_uuid(learner_id)
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
async def pilot_metrics(learner_id: str, _: None = Depends(rate_limit)):
    _require_uuid(learner_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        gates = await metrics_mod.compute_pilot_gates(conn, learner_id)
    return {"learner_id": learner_id, "gates": gates}


@app.get("/pilot/funnel")
async def pilot_funnel(school_id: str | None = None, _: None = Depends(rate_limit)):
    """
    Registration → onboarding-complete → portrait-revealed → first-chat
    counts, optionally scoped to one school_id. Read-only rollup — does not
    touch metrics.pilot_gates (that stays per-learner, see /metrics/pilot).

    Learners registered before school_id existed show under "unassigned".
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        where = "WHERE i.type = 'child'"
        args: list = []
        if school_id:
            args.append(school_id)
            where += " AND i.school_id = $1"

        registered = await conn.fetchval(
            f"SELECT count(*) FROM foundation.identities i {where}", *args
        )
        onboarded = await conn.fetchval(
            f"""
            SELECT count(*) FROM foundation.identities i
            JOIN puzzle_engine.learner_state ls ON ls.learner_id = i.id::text
            {where} AND ls.onboarding_done = true
            """,
            *args,
        )
        portrait_revealed = await conn.fetchval(
            f"""
            SELECT count(*) FROM foundation.identities i
            JOIN puzzle_engine.portraits p ON p.learner_id = i.id::text
            {where}
            """,
            *args,
        )
        first_chat = await conn.fetchval(
            f"""
            SELECT count(DISTINCT i.id) FROM foundation.identities i
            JOIN metrics.sessions s ON s.learner_id = i.id::text
            {where}
            """,
            *args,
        )

    return {
        "school_id": school_id or "all",
        "registered": registered,
        "onboarding_complete": onboarded,
        "portrait_revealed": portrait_revealed,
        "first_chat": first_chat,
    }


# ── Parent dashboard endpoints ────────────────────────────────────────────────
@app.get("/parent/{learner_id}/report")
async def parent_report(learner_id: str, _: None = Depends(rate_limit)):
    _require_uuid(learner_id)
    from modules.parent_dashboard.module import build_report
    pool = await get_pool()
    async with pool.acquire() as conn:
        report = await build_report(conn, learner_id)
    return report


@app.get("/parent/{learner_id}/alerts")
async def parent_alerts(learner_id: str, _: None = Depends(rate_limit)):
    _require_uuid(learner_id)
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
    # Tutor backend liveness
    tutor_ok = False
    if Config.use_anthropic_tutor():
        tutor_ok = bool(Config.ANTHROPIC_API_KEY)
    else:
        try:
            async with httpx.AsyncClient(timeout=4) as client:
                await client.get(f"{Config.OLLAMA_URL}/api/tags")
            tutor_ok = True
        except Exception:
            tutor_ok = False

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

    # Minimal public response — no IPs, no internal model names.
    return {
        "status": "ok" if (tutor_ok and pg_ok) else "degraded",
        "version": "4.0.0",
        "tutor_backend": "anthropic" if Config.use_anthropic_tutor() else "ollama",
        "tutor": tutor_ok,
        "postgres": pg_ok,
        "rag_chunks": rag_chunks,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Investor Demo ────────────────────────────────────────────────────────────
@app.get("/demo")
async def demo_ui():
    return FileResponse("static/demo.html")


# ── Magic Mirror Demo (portrait live build) ───────────────────────────────────
@app.get("/mirror")
async def mirror_ui():
    return FileResponse("static/portrait_demo.html")


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
    learner_id: str = Field(..., max_length=100)
    location_id: str = Field(..., max_length=100)


class WorldChatRequest(BaseModel):
    learner_id: str = Field(..., max_length=100)
    location_id: str = Field(..., max_length=100)
    message: str = Field(..., max_length=2000)


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
async def world_chat(req: WorldChatRequest, _: None = Depends(rate_limit)):
    from modules.moderation_ops.module import moderate_text, _BLOCK_RESPONSE, _DISTRESS_RESPONSE

    if req.location_id not in LOCATIONS:
        raise HTTPException(status_code=404, detail="Unknown location")

    # Moderate child's message before storing or processing
    mod = moderate_text(req.message)
    if mod["harmful_detected"]:
        raise HTTPException(status_code=400, detail=_BLOCK_RESPONSE)
    if mod["distress_detected"]:
        # Return the distress response immediately; don't involve the shared world
        return {
            "response": _DISTRESS_RESPONSE,
            "present": [],
            "group_size": 0,
        }

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


@app.get("/observer", include_in_schema=False)
async def observer_ui():
    return FileResponse("static/observer.html")


@app.get("/api/trace/{learner_id}")
async def get_agent_trace(learner_id: str):
    """Return the last N agent dispatch traces for a learner (observer page)."""
    return {
        "learner_id": learner_id,
        "traces": list(reversed(_agent_traces.get(learner_id, []))),
    }


@app.get("/api/trace/{learner_id}/latest")
async def get_latest_trace(learner_id: str):
    """Return only the most recent dispatch trace (for SSE-less polling)."""
    traces = _agent_traces.get(learner_id, [])
    return traces[-1] if traces else {}


# ── Onboarding (BMAD guardian flow) ──────────────────────────────────────────
from modules.learner_state import onboarding as _onboarding  # noqa: E402


@app.get("/onboarding", include_in_schema=False)
async def onboarding_ui():
    return FileResponse("static/onboarding.html")


class OnboardingStartRequest(BaseModel):
    learner_id:    str = Field(..., max_length=100)
    learner_name:  str = Field(..., max_length=100)
    guardian_name: str = Field(..., max_length=100)


class OnboardingAnswerRequest(BaseModel):
    text: str = Field(..., max_length=2000)


@app.post("/api/onboarding/start")
async def onboarding_start(req: OnboardingStartRequest):
    return _onboarding.start(req.learner_id, req.learner_name, req.guardian_name)


@app.post("/api/onboarding/{session_id}/answer")
async def onboarding_answer(session_id: str, req: OnboardingAnswerRequest):
    return await _onboarding.answer(session_id, req.text)


@app.get("/api/onboarding/{session_id}")
async def onboarding_status(session_id: str):
    s = _onboarding.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


@app.post("/api/onboarding/{session_id}/apply")
async def onboarding_apply(session_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await _onboarding.apply(session_id, conn)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── Lens endpoints ────────────────────────────────────────────────────────────
from modules.lens import cognitive as cognitive_lens  # noqa: E402

# Remaining lenses imported lazily so server starts even if files aren't written yet
def _import_lens(name: str):
    try:
        import importlib
        return importlib.import_module(f"modules.lens.{name}")
    except ImportError:
        return None


def _lens_module(name: str):
    modules = {
        "cognitive":     cognitive_lens,
        "affect":        _import_lens("affect"),
        "psychological": _import_lens("psychological"),
        "contextual":    _import_lens("contextual"),
        "relational":    _import_lens("relational"),
    }
    return modules.get(name)


async def _lens_latest(lens_name: str, learner_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # All lenses store in same table — fetch directly without needing the module
        row = await conn.fetchrow(
            """SELECT portrait, narrative, computed_at
               FROM learner_state.lens_portraits
               WHERE learner_id = $1 AND lens = $2
               ORDER BY computed_at DESC LIMIT 1""",
            learner_id, lens_name,
        )
    if not row:
        return {"learner_id": learner_id, "portrait": None}
    raw = row["portrait"]
    import json as _json2
    d = _json2.loads(raw) if isinstance(raw, str) else dict(raw)
    d["narrative"]   = row["narrative"]
    d["computed_at"] = row["computed_at"].isoformat()
    return {"learner_id": learner_id, "portrait": d}


@app.get("/api/lens/{lens_name}/{learner_id}")
async def get_lens_portrait(lens_name: str, learner_id: str):
    """Return latest portrait for any lens without recomputing."""
    valid = {"cognitive", "affect", "psychological", "contextual", "relational"}
    if lens_name not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown lens. Valid: {sorted(valid)}")
    return await _lens_latest(lens_name, learner_id)


@app.post("/api/lens/{lens_name}/{learner_id}/run")
async def run_lens(
    lens_name: str,
    learner_id: str,
    period_days: int = 30,
    _: None = Depends(rate_limit),
):
    """Compute and save a lens portrait for any lens."""
    _require_uuid(learner_id)
    valid = {"cognitive", "affect", "psychological", "contextual", "relational"}
    if lens_name not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown lens. Valid: {sorted(valid)}")
    mod = _lens_module(lens_name)
    if mod is None:
        raise HTTPException(status_code=503, detail=f"Lens '{lens_name}' not yet available.")
    pool = await get_pool()
    portrait = await mod.compute_and_save(pool, learner_id, period_days=period_days)
    from dataclasses import asdict
    return {"learner_id": learner_id, "portrait": asdict(portrait)}


# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "name": "Parth AI Server",
        "version": "4.0.0",
        "health": "/health",
        "docs": "/docs",
    }
