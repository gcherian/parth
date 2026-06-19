"""Agent 06 — Motivational Profile: per-subject engagement EMA."""
from __future__ import annotations
import json
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import profile as prof


class MotivationalProfileAgent(LearnerAgent):
    name = "motivational_profile"
    phase = "both"
    memory_window = "month"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            await prof.update_motivational_profile(
                conn, signals.learner_id, signals.subject, signals.engagement
            )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                "SELECT motivational_profile FROM learner_state.profiles WHERE learner_id=$1",
                learner_id,
            )
            if not row:
                return ""
            motiv: dict = row["motivational_profile"] or {}
            if isinstance(motiv, str):
                motiv = json.loads(motiv)
            if len(motiv) < 2:
                return ""
            sorted_s = sorted(motiv.items(), key=lambda x: -x[1])
            top_subject, top_score = sorted_s[0]
            low_subject, low_score = sorted_s[-1]
            return (
                f"Genuine engagement: {top_subject} ({top_score:.1f}). "
                f"Watch for performed: {low_subject}."
            )
        except Exception:
            return ""
