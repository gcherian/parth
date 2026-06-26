"""Agent 14 — Social Preference: extroversion-based learning style."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import psyche as psy


class SocialPreferenceAgent(LearnerAgent):
    name = "social_preference"
    phase = "both"
    memory_window = "month"

    async def observe(self, signals: AgentSignals, conn) -> None:
        pass  # psyche.extroversion updated by cognitive_profile agent

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            psyche = await psy.get_psyche(conn, learner_id)
            if psyche.get("sample_count", 0) < 5:
                return ""
            ext = psyche.get("extroversion", 0.5)
            if ext >= 0.6:
                return f"Learns by: teaching back (extroversion={ext:.2f})."
            elif ext <= 0.4:
                return f"Learns by: absorbing quietly (extroversion={ext:.2f})."
            return ""
        except Exception:
            return ""
