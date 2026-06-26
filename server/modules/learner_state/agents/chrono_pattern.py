"""Agent 13 — Chrono Pattern: peak engagement hour from interaction history."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals


class ChronoPatternAgent(LearnerAgent):
    name = "chrono_pattern"
    phase = "both"
    memory_window = "week"

    async def observe(self, signals: AgentSignals, conn) -> None:
        pass  # derives from interactions table

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                """
                SELECT EXTRACT(hour FROM created_at)::int as hr,
                       AVG(engagement) as avg_eng,
                       COUNT(*) as n
                FROM learner_state.interactions
                WHERE learner_id=$1 AND created_at > now()-interval'30 days'
                GROUP BY hr HAVING COUNT(*)>=2
                ORDER BY avg_eng DESC LIMIT 1
                """,
                learner_id,
            )
            if not row:
                return ""
            # Require at least 10 total interactions for reliable signal
            total = await conn.fetchval(
                """
                SELECT COUNT(*) FROM learner_state.interactions
                WHERE learner_id=$1 AND created_at > now()-interval'30 days'
                """,
                learner_id,
            )
            if (total or 0) < 10:
                return ""
            hr = row["hr"]
            return f"Peak focus: {hr}:00–{hr+1}:00."
        except Exception:
            return ""
