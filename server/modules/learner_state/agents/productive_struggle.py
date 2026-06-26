"""Agent 04 — Productive Struggle: monitors struggle frequency today."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals


class ProductiveStruggleAgent(LearnerAgent):
    name = "productive_struggle"
    phase = "both"
    memory_window = "week"

    async def observe(self, signals: AgentSignals, conn) -> None:
        pass  # episodes table updated by episodic_memory agent

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        # Distress if 3+ struggles this session (tracked via events accumulation)
        # We count from the read path — emit is called after observe, so we rely
        # on the harness calling read() separately for context.
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM learner_state.episodes
                WHERE learner_id=$1
                  AND episode_type='struggle'
                  AND created_at > CURRENT_DATE
                """,
                learner_id,
            )
            count = count or 0
            if count == 0:
                return ""
            suffix = " [Approaching limit.]" if count >= 2 else ""
            return f"Struggle today: {count} session(s).{suffix}"
        except Exception:
            return ""

    def _distress_emit(self, count: int) -> dict[str, Any]:
        return {"distress.detected": True} if count >= 3 else {}
