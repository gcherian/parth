"""Agent 02 — Misconception Map: tracks recurring misconceptions."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import profile as prof


class MisconceptionMapAgent(LearnerAgent):
    name = "misconception_map"
    phase = "both"
    memory_window = "permanent"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            if signals.misconception and signals.misconception_concept:
                await prof.update_misconception_map(
                    conn, signals.learner_id,
                    signals.misconception_concept,
                    signals.misconception,
                )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            rows = await conn.fetch(
                """
                SELECT concept_id, misconception, count
                FROM learner_state.misconception_map
                WHERE learner_id = $1
                ORDER BY count DESC
                LIMIT 2
                """,
                learner_id,
            )
            if not rows:
                return ""
            parts = [
                f"'{r['misconception'][:60]}' about {r['concept_id']} (×{r['count']})"
                for r in rows
            ]
            return "Watch for: " + "; ".join(parts) + "."
        except Exception:
            return ""
