"""Agent 01 — Knowledge State: tracks concept mastery and ZPD target."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import knowledge as know


class KnowledgeStateAgent(LearnerAgent):
    name = "knowledge_state"
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
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        if signals.misconception:
            return {"concept.weak": True}
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            rows = await conn.fetch(
                """
                SELECT concept_id, p_mastery, exposures
                FROM learner_state.knowledge
                WHERE learner_id = $1
                ORDER BY p_mastery DESC
                """,
                learner_id,
            )
            if not rows:
                return ""
            strong = [r for r in rows if r["p_mastery"] > 0.6][:3]
            weak   = [r for r in rows if r["p_mastery"] < 0.35][:3]
            # ZPD: exposed but not yet mastered (p_mastery between 0.35 and 0.6)
            zpd_rows = [r for r in rows if 0.35 <= r["p_mastery"] <= 0.6]
            zpd = zpd_rows[0]["concept_id"] if zpd_rows else None

            parts = []
            if strong:
                s = ", ".join(f"{r['concept_id']} ({r['p_mastery']:.2f})" for r in strong)
                parts.append(f"strong in {s}")
            if weak:
                w = ", ".join(f"{r['concept_id']} ({r['p_mastery']:.2f})" for r in weak)
                parts.append(f"Developing: {w}")
            line = "Knowledge: " + ". ".join(parts) if parts else ""
            if zpd:
                line += f". ZPD target: {zpd}."
            return line
        except Exception:
            return ""
