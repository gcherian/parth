"""Agent 16 — Curiosity Tracker: live curiosity threads for this session."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import curiosity as cur


class CuriosityTrackerAgent(LearnerAgent):
    name = "curiosity_tracker"
    phase = "both"
    memory_window = "session"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            recent_kws = await cur.get_recent_keywords(
                conn, signals.learner_id, signals.session_id
            )
            signal     = cur.detect_signal(signals.message, recent_kws)
            threads    = await cur.load(conn, signals.learner_id, signals.session_id)
            threads    = cur.update_threads(threads, signal, signals.message)
            await cur.save(conn, signals.learner_id, signals.session_id, threads)
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                """
                SELECT threads_json FROM learner_state.curiosity_sessions
                WHERE learner_id=$1
                ORDER BY updated_at DESC LIMIT 1
                """,
                learner_id,
            )
            if not row:
                return ""
            import json
            threads = json.loads(row["threads_json"] or "[]")
            return cur.build_curiosity_context(threads)
        except Exception:
            return ""
