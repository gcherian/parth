"""Agent 11 — Confidence Calibration: detects overconfidence vs actual mastery."""
from __future__ import annotations
import re
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals

_HIGH_CONF = re.compile(
    r"\b(I know|easy|obviously|I'?m sure|definitely|for sure|pata hai|aata hai)\b",
    re.IGNORECASE,
)


class ConfidenceCalibrationAgent(LearnerAgent):
    name = "confidence_calibration"
    phase = "both"
    memory_window = "week"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            if not _HIGH_CONF.search(signals.message):
                return
            if not signals.concepts:
                return
            for concept in signals.concepts:
                mastery_row = await conn.fetchrow(
                    "SELECT p_mastery FROM learner_state.knowledge WHERE learner_id=$1 AND concept_id=$2",
                    signals.learner_id, concept,
                )
                actual = float(mastery_row["p_mastery"]) if mastery_row else 0.0
                gap = max(0.0, 0.45 - actual)  # gap only meaningful if overconfident
                await conn.execute(
                    """
                    INSERT INTO learner_state.confidence_calibration
                        (learner_id, concept_id, stated_high, actual_mastery, gap, updated_at)
                    VALUES ($1, $2, true, $3, $4, now())
                    ON CONFLICT (learner_id, concept_id) DO UPDATE
                        SET stated_high    = true,
                            actual_mastery = $3,
                            gap            = $4,
                            updated_at     = now()
                    """,
                    signals.learner_id, concept, actual, gap,
                )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            rows = await conn.fetch(
                """
                SELECT concept_id, actual_mastery
                FROM learner_state.confidence_calibration
                WHERE learner_id=$1 AND stated_high=true AND actual_mastery < 0.45
                ORDER BY actual_mastery ASC
                LIMIT 3
                """,
                learner_id,
            )
            if not rows:
                return ""
            parts = [f"{r['concept_id']} (p_mastery={r['actual_mastery']:.2f})" for r in rows]
            return "Overconfident in: " + ", ".join(parts) + "."
        except Exception:
            return ""
