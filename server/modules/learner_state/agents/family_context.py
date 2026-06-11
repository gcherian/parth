"""Agent 12 — Family Context: stub until parent onboarding is built."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals


class FamilyContextAgent(LearnerAgent):
    name = "family_context"
    phase = "both"
    memory_window = "month"

    async def observe(self, signals: AgentSignals, conn) -> None:
        pass  # stub

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        return ""  # stub until parent onboarding screen is built
