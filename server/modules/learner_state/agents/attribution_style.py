"""Agent 09 — Attribution Style: effort vs ability attribution from growth_mindset."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import psyche as psy


class AttributionStyleAgent(LearnerAgent):
    name = "attribution_style"
    phase = "both"
    memory_window = "month"

    async def observe(self, signals: AgentSignals, conn) -> None:
        pass  # psyche updated by cognitive_profile agent

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            psyche = await psy.get_psyche(conn, learner_id)
            if psyche.get("sample_count", 0) < 5:
                return ""
            gm = psyche.get("growth_mindset", 0.5)
            if gm >= 0.5:
                return f"Attribution: effort-based (growth={gm:.2f})."
            else:
                return f"Attribution: ability-based (growth={gm:.2f})."
        except Exception:
            return ""
