"""Mastery Tracker — BKT posteriors + SAINT+ event log.

Ref: Shen et al., "A Survey of Knowledge Tracing" — interpretable BKT first,
SAINT+ temporal features as the upgrade path once kt_events accumulates data.
"""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import knowledge as know


class MasteryTrackerAgent(LearnerAgent):
    name = "mastery_tracker"
    phase = "both"
    memory_window = "permanent"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            if signals.concepts:
                await know.record_exposure(conn, signals.learner_id, signals.concepts)
            if signals.misconception and signals.misconception_concept:
                await know.record_misconception(
                    conn, signals.learner_id,
                    [signals.misconception_concept],
                    session_id=signals.session_id,
                )
            if not signals.misconception and signals.concepts:
                await know.record_demonstration(conn, signals.learner_id, signals.concepts)

            # SAINT+ temporal event row
            for concept_id in (signals.concepts or []):
                correct = not (signals.misconception and signals.misconception_concept == concept_id)
                await conn.execute(
                    """INSERT INTO learner_state.kt_events
                       (learner_id, concept_id, correct, elapsed_ms, lag_ms, session_id, created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,now())""",
                    signals.learner_id, concept_id, correct,
                    signals.elapsed_ms, signals.lag_ms, signals.session_id,
                )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        if signals.misconception:
            return {"concept.weak": True}
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            rows = await conn.fetch(
                "SELECT concept_id, p_mastery, exposures FROM learner_state.knowledge "
                "WHERE learner_id=$1 ORDER BY p_mastery DESC",
                learner_id,
            )
            if not rows:
                return ""
            strong = [r for r in rows if r["p_mastery"] > 0.6][:3]
            weak   = [r for r in rows if r["p_mastery"] < 0.35][:3]
            zpd    = next((r["concept_id"] for r in rows if 0.35 <= r["p_mastery"] <= 0.6), None)
            parts  = []
            if strong:
                parts.append("Strong: " + ", ".join(
                    f"{r['concept_id']}({r['p_mastery']:.2f})" for r in strong))
            if weak:
                parts.append("Developing: " + ", ".join(
                    f"{r['concept_id']}({r['p_mastery']:.2f})" for r in weak))
            line = ". ".join(parts)
            if zpd:
                line += f". ZPD target: {zpd}."
            return line
        except Exception:
            return ""
