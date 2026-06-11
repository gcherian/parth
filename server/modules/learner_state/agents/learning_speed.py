"""Agent 05 — Learning Speed: acquisition rate from knowledge table."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals


class LearningSpeedAgent(LearnerAgent):
    name = "learning_speed"
    phase = "both"
    memory_window = "month"

    async def observe(self, signals: AgentSignals, conn) -> None:
        pass  # no writes

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as n,
                    AVG(demonstrations::float / NULLIF(exposures, 0)) as ratio
                FROM learner_state.knowledge
                WHERE learner_id = $1 AND exposures >= 3
                """,
                learner_id,
            )
            if not row or (row["n"] or 0) < 3 or row["ratio"] is None:
                return ""
            ratio = float(row["ratio"])
            if ratio > 0.5:
                label = "fast"
            elif ratio < 0.2:
                label = "slow"
            else:
                label = "average"
            return f"Acquisition speed: {label} (demo/exp={ratio:.0%})."
        except Exception:
            return ""
