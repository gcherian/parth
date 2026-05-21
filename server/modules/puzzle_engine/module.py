"""
puzzle.engine — Kernel module: portrait-aware puzzle delivery.

Handles two event types:
  puzzle.next_requested    → return next puzzle for learner (ZPD + register + portrait)
  puzzle.response_recorded → evaluate response, update portrait + register state

This module does NOT run in the main chat pipeline — it runs on dedicated
puzzle endpoints (see main.py) and communicates via the outbox.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger
from foundation.outbox import publish

from modules.puzzle_engine import loader
from modules.puzzle_engine.selector import next_puzzle
from modules.puzzle_engine.portrait import (
    default_portrait, update_sphere_affinity,
    infer_telos, infer_error_response, confidence_level,
    adaptive_alpha, build_portrait_context,
)
from modules.puzzle_engine.register import (
    RegisterState, update as update_register,
    best_bridge_for_concept, register_visualisation,
)
from modules.puzzle_engine.cold_start import get_probe
from modules.puzzle_engine.evaluator import evaluate_response
from modules.puzzle_engine.error_response import classify_error_response

log = get_logger("puzzle.engine")


class PuzzleEngineModule(Module):
    name = "puzzle.engine"
    handles = ["puzzle.next_requested", "puzzle.response_recorded"]

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        if event.type == "puzzle.next_requested":
            return await self._next_puzzle(event, ctx)
        if event.type == "puzzle.response_recorded":
            return await self._record_response(event, ctx)
        return ModuleResult(data={})

    async def _next_puzzle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        conn = ctx.db
        learner_id = ctx.learner_id
        grade = ctx.grade

        # Load state from DB
        state = await _load_learner_state(conn, learner_id)
        portrait = await _load_portrait(conn, learner_id, grade)
        seen_ids = await _load_seen_puzzle_ids(conn, learner_id)

        total = state.get("total_puzzles", 0)

        # Cold start protocol for first 5 puzzles
        if total < 5:
            primary_sphere = portrait.get("primary_sphere") or None
            probe = get_probe(total, seen_ids, primary_sphere, grade)
            return ModuleResult(data={
                "mode": "cold_start",
                "probe_number": total,
                "probe": probe,
            })

        # Normal: portrait-guided selection
        sphere_affinity = portrait.get("sphere_affinity", {})
        zpd_levels = portrait.get("zpd_levels", {})
        telos = portrait.get("provisional_telos", "")
        last_sphere = state.get("last_sphere", "")
        consecutive = state.get("consecutive_sphere", 0)

        sphere_mastery = {
            sphere: (0.0 if zpd_levels.get(sphere, "beginner") == "beginner"
                     else 0.5 if zpd_levels.get(sphere) == "intermediate"
                     else 0.8)
            for sphere in loader.SPHERES
        }

        puzzle = next_puzzle(
            seen_ids=seen_ids,
            sphere_affinity=sphere_affinity,
            sphere_mastery=sphere_mastery,
            total_puzzles=total,
            last_sphere=last_sphere,
            consecutive_sphere=consecutive,
            telos=telos,
            grade=grade,
        )

        if puzzle is None:
            return ModuleResult(data={"error": "all_puzzles_seen"})

        return ModuleResult(data={"mode": "normal", "puzzle": puzzle})

    async def _record_response(self, event: Event, ctx: KernelContext) -> ModuleResult:
        conn = ctx.db
        learner_id = ctx.learner_id
        payload = event.payload

        puzzle_id    = payload.get("puzzle_id", "")
        response_text = payload.get("response", "")
        time_seconds  = int(payload.get("time_seconds", 0))
        reached_deeper = bool(payload.get("reached_deeper", False))

        puzzle = loader.get(puzzle_id)
        if not puzzle:
            return ModuleResult(data={"error": f"unknown puzzle {puzzle_id}"})

        # Evaluate response (async, non-blocking)
        eval_result = await evaluate_response(puzzle, response_text, time_seconds)
        quality = eval_result["quality"]
        error_type = eval_result["error_response_type"]

        # Load current state
        portrait = await _load_portrait(conn, learner_id, ctx.grade)
        register_raw = await _load_register_state(conn, learner_id)
        state = await _load_learner_state(conn, learner_id)
        n = int(state.get("total_puzzles", 0))

        # Update register from response text
        reg = RegisterState(
            learner_id=learner_id,
            probs=register_raw.get("probs", {d: 1/8 for d in ["cricket","cooking","music","gaming","nature","story","technology","mathematics"]}),
            n_messages=register_raw.get("n_messages", 0),
        )
        reg = update_register(reg, response_text)

        # Update sphere affinity
        sphere = puzzle["sphere"]
        affinity = portrait.get("sphere_affinity", {})
        affinity = update_sphere_affinity(affinity, sphere, quality, n)

        # Update ZPD level
        zpd = portrait.get("zpd_levels", {})
        current_level = zpd.get(sphere, "beginner")
        # Promote if quality = 3 (go_deeper); demote if quality = 0
        if quality >= 3 and current_level == "beginner":
            zpd[sphere] = "intermediate"
        elif quality >= 3 and current_level == "intermediate":
            zpd[sphere] = "advanced"
        elif quality == 0 and current_level == "advanced":
            zpd[sphere] = "intermediate"
        elif quality == 0 and current_level == "intermediate":
            zpd[sphere] = "beginner"

        # Update primary sphere
        primary = portrait.get("primary_sphere", "")
        if affinity.get(sphere, 5.0) > affinity.get(primary, 0.0):
            primary = sphere

        # Update portrait error response
        error_response = portrait.get("error_response", "unknown")
        if error_type != "unknown":
            # EMA over error responses
            error_response = error_type  # simplified: take most recent clear signal

        # Infer telos from updated signals (every 5 interactions)
        telos = portrait.get("provisional_telos", "explorer")
        if n % 5 == 0:
            from modules.learner_state.psyche import get_psyche
            psyche = await get_psyche(conn, learner_id)
            go_deeper_rate = float(n > 0 and reached_deeper)
            telos = infer_telos(
                sphere_affinity=affinity,
                psyche=psyche,
                probe_4_engaged=(n == 3),
                go_deeper_rate=go_deeper_rate,
            )

        new_portrait = {
            **portrait,
            "primary_sphere":         primary,
            "sphere_affinity":        affinity,
            "zpd_levels":             zpd,
            "error_response":         error_response,
            "provisional_telos":      telos,
            "interactions_used":      n + 1,
            "confidence":             confidence_level(n + 1),
        }

        # Persist
        await _save_portrait(conn, learner_id, new_portrait)
        await _save_register_state(conn, learner_id, reg)
        await _update_learner_state(conn, learner_id, puzzle, state)

        # Publish misconception to parent outbox if detected
        if eval_result.get("misconception"):
            await publish(conn, "puzzle.misconception_detected", {
                "learner_id":   learner_id,
                "puzzle_id":    puzzle_id,
                "misconception": eval_result["misconception"],
            })

        log.info("puzzle_response_recorded",
                 learner_id=learner_id, puzzle_id=puzzle_id,
                 quality=quality, telos=telos, sphere=sphere)

        return ModuleResult(data={
            "quality":          quality,
            "telos":            telos,
            "primary_sphere":   primary,
            "portrait_confidence": new_portrait["confidence"],
            "register_dominant": max(reg.probs, key=reg.probs.__getitem__),
        })

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        conn = ctx.db
        await conn.execute(
            "DELETE FROM puzzle_engine.responses WHERE learner_id=$1", learner_id)
        await conn.execute(
            "DELETE FROM puzzle_engine.sphere_affinity WHERE learner_id=$1", learner_id)
        await conn.execute(
            "DELETE FROM puzzle_engine.learner_state WHERE learner_id=$1", learner_id)
        await conn.execute(
            "DELETE FROM puzzle_engine.portraits WHERE learner_id=$1", learner_id)
        await conn.execute(
            "DELETE FROM puzzle_engine.register_states WHERE learner_id=$1", learner_id)


# ── DB helpers ───────────────────────────────────────────────────────────────

async def _load_learner_state(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM puzzle_engine.learner_state WHERE learner_id=$1", learner_id)
    return dict(row) if row else {}


async def _update_learner_state(conn, learner_id: str, puzzle: dict, state: dict):
    last_sphere = puzzle["sphere"]
    consecutive = (
        state.get("consecutive_sphere", 0) + 1
        if state.get("last_sphere") == last_sphere else 1
    )
    await conn.execute("""
        INSERT INTO puzzle_engine.learner_state
            (learner_id, last_puzzle_id, last_sphere, consecutive_sphere, total_puzzles, updated_at)
        VALUES ($1,$2,$3,$4, COALESCE((SELECT total_puzzles FROM puzzle_engine.learner_state WHERE learner_id=$1), 0)+1, now())
        ON CONFLICT (learner_id) DO UPDATE
        SET last_puzzle_id     = $2,
            last_sphere        = $3,
            consecutive_sphere = $4,
            total_puzzles      = puzzle_engine.learner_state.total_puzzles + 1,
            updated_at         = now()
    """, learner_id, puzzle["id"], last_sphere, consecutive)


async def _load_seen_puzzle_ids(conn, learner_id: str) -> set[str]:
    rows = await conn.fetch(
        "SELECT puzzle_id FROM puzzle_engine.responses WHERE learner_id=$1", learner_id)
    return {r["puzzle_id"] for r in rows}


async def _load_portrait(conn, learner_id: str, grade: int = 6) -> dict:
    row = await conn.fetchrow(
        "SELECT portrait_json FROM puzzle_engine.portraits WHERE learner_id=$1", learner_id)
    if row:
        return json.loads(row["portrait_json"])
    return default_portrait(learner_id, grade)


async def _save_portrait(conn, learner_id: str, portrait: dict):
    await conn.execute("""
        INSERT INTO puzzle_engine.portraits (learner_id, portrait_json, updated_at)
        VALUES ($1, $2, now())
        ON CONFLICT (learner_id) DO UPDATE
        SET portrait_json=$2, updated_at=now()
    """, learner_id, json.dumps(portrait))


async def _load_register_state(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        "SELECT state_json FROM puzzle_engine.register_states WHERE learner_id=$1", learner_id)
    return json.loads(row["state_json"]) if row else {}


async def _save_register_state(conn, learner_id: str, reg: RegisterState):
    state = {
        "probs": reg.probs,
        "n_messages": reg.n_messages,
        "dominant_question_type": reg.dominant_question_type,
        "avg_sentence_length": reg.avg_sentence_length,
    }
    await conn.execute("""
        INSERT INTO puzzle_engine.register_states (learner_id, state_json, updated_at)
        VALUES ($1, $2, now())
        ON CONFLICT (learner_id) DO UPDATE
        SET state_json=$2, updated_at=now()
    """, learner_id, json.dumps(state))
