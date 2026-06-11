"""Inquiry Alchemist — curiosity threads + SEL reappraisal during distress.

SEL support only; not therapy. Avoid moralizing or forced confessions.
Ref: CASEL Framework (self-awareness, responsible decision-making).
"""
from __future__ import annotations
import json
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import curiosity as cur


class InquiryAlchemistAgent(LearnerAgent):
    name = "inquiry_alchemist"
    phase = "both"
    memory_window = "session"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            recent_kws = await cur.get_recent_keywords(conn, signals.learner_id, signals.session_id)
            signal     = cur.detect_signal(signals.message, recent_kws)
            threads    = await cur.load(conn, signals.learner_id, signals.session_id)
            threads    = cur.update_threads(threads, signal, signals.message)
            await cur.save(conn, signals.learner_id, signals.session_id, threads)

            if signals.events.get("distress.detected"):
                await conn.execute(
                    """INSERT INTO learner_state.inquiry_state
                       (learner_id, repair_count, last_repair_at, updated_at)
                       VALUES ($1,1,now(),now())
                       ON CONFLICT (learner_id) DO UPDATE
                       SET repair_count = inquiry_state.repair_count + 1,
                           last_repair_at = now(), updated_at = now()""",
                    signals.learner_id,
                )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                "SELECT threads_json FROM learner_state.curiosity_sessions "
                "WHERE learner_id=$1 ORDER BY updated_at DESC LIMIT 1",
                learner_id,
            )
            threads = json.loads(row["threads_json"] or "[]") if row else []
            ctx     = cur.build_curiosity_context(threads)

            repair = await conn.fetchrow(
                "SELECT repair_count FROM learner_state.inquiry_state WHERE learner_id=$1",
                learner_id,
            )
            parts = []
            if ctx:
                parts.append(ctx)
            if repair and (repair["repair_count"] or 0) > 0:
                parts.append(
                    f"SEL: {repair['repair_count']} distress episodes this week. "
                    "Offer reappraisal before pushing forward."
                )
            return " ".join(parts)
        except Exception:
            return ""
