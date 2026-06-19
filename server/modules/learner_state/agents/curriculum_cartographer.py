"""Curriculum Cartographer — concept-graph coverage, prerequisite paths, next targets."""
from __future__ import annotations
from typing import Any
from kernel.agent import BaseAgent, AgentSignals


class CurriculumCartographerAgent(BaseAgent):
    name = "curriculum_cartographer"
    phase = "both"
    memory_window = "permanent"

    async def _observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post" or not signals.concepts:
            return
        for concept_id in signals.concepts:
            await conn.execute(
                """INSERT INTO learner_state.curriculum_map
                   (learner_id, concept_id, subject, grade, first_seen, last_seen, seen_count)
                   VALUES ($1,$2,$3,$4,now(),now(),1)
                   ON CONFLICT (learner_id, concept_id) DO UPDATE
                   SET last_seen=now(), seen_count=curriculum_map.seen_count+1""",
                signals.learner_id, concept_id, signals.subject, signals.grade,
            )

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def _read(self, conn, learner_id: str) -> str:
        seen = await conn.fetchval(
            "SELECT COUNT(*) FROM learner_state.curriculum_map WHERE learner_id=$1",
            learner_id,
        )
        if not seen:
            return ""
        gaps = await conn.fetch(
            """SELECT DISTINCT e.to_id AS target
               FROM curriculum_graph.concept_edges e
               JOIN learner_state.curriculum_map cm
                 ON cm.concept_id = e.from_id AND cm.learner_id = $1
               LEFT JOIN learner_state.curriculum_map cm2
                 ON cm2.concept_id = e.to_id AND cm2.learner_id = $1
               WHERE e.type = 'leads-to' AND cm2.concept_id IS NULL
               LIMIT 3""",
            learner_id,
        )
        parts = [f"Concepts seen: {seen}."]
        if gaps:
            parts.append("Unexplored next: " + ", ".join(r["target"] for r in gaps) + ".")
        return " ".join(parts)
