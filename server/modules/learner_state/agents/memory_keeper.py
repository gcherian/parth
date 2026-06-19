"""Memory Keeper — episodic storage + SM-2 spaced-repetition review schedule.

Ref: Dunlosky et al., "Improving Students' Learning With Effective Learning Techniques" —
retrieval practice and distributed practice have among the strongest evidence; treat as primitives.
Uses practice_engine.cards (SM-2) and learner_state.episodes (episodic memory).
"""
from __future__ import annotations
from typing import Any
from kernel.agent import BaseAgent, AgentSignals
from modules.learner_state import episodes as epi

_DEFAULT_EASE = 2.5


def _sm2_interval(reps: int, ease: float, prev: float) -> float:
    if reps <= 1:
        return 1.0
    if reps == 2:
        return 6.0
    return round(prev * ease, 1)


class MemoryKeeperAgent(BaseAgent):
    name = "memory_keeper"
    phase = "both"
    memory_window = "permanent"

    async def _observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        # Episodic memory
        ep_type = epi.detect_type(signals.message)
        if ep_type:
            patterns = await epi.get_patterns_for_message(conn, signals.concepts)
            await epi.store(conn, signals.learner_id, ep_type,
                            signals.message, signals.concepts, patterns)

        # SM-2 review schedule (practice_engine.cards) for demonstrated concepts
        if signals.concepts and not signals.misconception:
            for concept_id in signals.concepts:
                row = await conn.fetchrow(
                    "SELECT repetitions, ease_factor, interval_days FROM practice_engine.cards "
                    "WHERE learner_id=$1 AND concept_id=$2",
                    signals.learner_id, concept_id,
                )
                reps     = ((row["repetitions"] if row else 0) or 0) + 1
                ease     = (row["ease_factor"] if row else _DEFAULT_EASE) or _DEFAULT_EASE
                prev_int = (row["interval_days"] if row else 1.0) or 1.0
                new_int  = _sm2_interval(reps, ease, prev_int)
                await conn.execute(
                    """INSERT INTO practice_engine.cards
                       (learner_id, concept_id, repetitions, ease_factor, interval_days, next_review)
                       VALUES ($1,$2,$3,$4,$5, now() + ($5 || ' days')::interval)
                       ON CONFLICT (learner_id, concept_id) DO UPDATE
                       SET repetitions=$3, ease_factor=$4, interval_days=$5,
                           next_review=now() + ($5 || ' days')::interval""",
                    signals.learner_id, concept_id, reps, ease, new_int,
                )

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def _read(self, conn, learner_id: str) -> str:
        overdue = await conn.fetch(
            """SELECT concept_id FROM practice_engine.cards
               WHERE learner_id=$1 AND next_review < now()
               ORDER BY next_review ASC LIMIT 3""",
            learner_id,
        )
        episodes = await epi.load_for_prompt(conn, learner_id)
        episode_ctx = epi.build_episode_context(episodes)

        parts = []
        if overdue:
            items = ", ".join(r["concept_id"] for r in overdue)
            parts.append(f"Review due: {items}.")
        if episode_ctx:
            parts.append(episode_ctx)
        return " ".join(parts)
