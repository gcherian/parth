"""Misconception Hunter — stable wrong models; requires repeated evidence before surfacing."""
from __future__ import annotations
from typing import Any
from kernel.agent import BaseAgent, AgentSignals
from modules.learner_state import profile as prof
from config import Config


class MisconceptionHunterAgent(BaseAgent):
    name = "misconception_hunter"
    phase = "both"
    memory_window = "permanent"

    async def _observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        if signals.misconception and signals.misconception_concept:
            await prof.update_misconception_map(
                conn, signals.learner_id,
                signals.misconception_concept,
                signals.misconception,
            )

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        if signals.misconception and signals.misconception_concept:
            return {"misconception.active": signals.misconception_concept}
        return {}

    async def _read(self, conn, learner_id: str) -> str:
        cfg        = await self.get_config(conn, learner_id)
        evidence_t = cfg.get("evidence_required", Config.MISCONCEPTION_EVIDENCE)
        rows = await conn.fetch(
            """SELECT concept_id, misconception, count
               FROM learner_state.misconception_map
               WHERE learner_id=$1 AND count >= $2
               ORDER BY count DESC LIMIT 2""",
            learner_id, evidence_t,
        )
        if not rows:
            return ""
        parts = [
            f"'{r['misconception'][:60]}' on {r['concept_id']} (seen ×{r['count']})"
            for r in rows
        ]
        return "Confirmed misconceptions: " + "; ".join(parts) + ". Use counterexamples, not correction."
