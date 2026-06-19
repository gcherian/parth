"""Pattern & Creation Guide — wonder questions; cross-scale pattern encounters.

Ref: NGSS Appendix G Crosscutting Concepts — patterns, scale, proportion,
and systems thinking should cut across domains, not sit inside one subject silo.
Separate science from metaphor; avoid pseudoscience and false equivalence.
"""
from __future__ import annotations
from typing import Any
from kernel.agent import BaseAgent, AgentSignals
from modules.learner_state import open_loops as opl
from modules.learner_state import episodes as epi
from foundation.observability import get_logger

log = get_logger("learner.state.agents.pattern_creation")

_AWE_MARKERS = {"same", "pattern", "everywhere", "both", "it's like", "galaxy", "atom",
                "wave", "cycle", "branch", "scale", "fractal"}


class PatternCreationGuideAgent(BaseAgent):
    name = "pattern_creation_guide"
    phase = "both"
    memory_window = "week"

    async def _observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        await opl.expire_old(conn, signals.learner_id)
        ep_type = epi.detect_type(signals.message)
        total_q = signals.total_questions + 1

        if opl.should_generate(total_q, ep_type):
            recent_episodes = await epi.load_for_prompt(conn, signals.learner_id)
            threads = signals.events.get("curiosity.threads", [])
            q_text, q_concepts = opl.generate(
                concepts=signals.concepts,
                episodes=recent_episodes,
                threads=threads,
            )
            if q_text:
                await opl.store(conn, signals.learner_id, q_text,
                                q_concepts or signals.concepts)
                log.debug("wonder_planted", learner_id=signals.learner_id, question=q_text[:60])

        # Cross-scale pattern encounter tracking
        msg_lower = signals.message.lower()
        if any(w in msg_lower for w in _AWE_MARKERS) and signals.concepts:
            await conn.execute(
                """INSERT INTO learner_state.pattern_state
                   (learner_id, latest_pattern_message, updated_at)
                   VALUES ($1,$2,now())
                   ON CONFLICT (learner_id) DO UPDATE
                   SET latest_pattern_message=$2, updated_at=now()""",
                signals.learner_id, signals.message[:200],
            )

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def _read(self, conn, learner_id: str) -> str:
        await opl.expire_old(conn, learner_id)
        loops = await opl.load_open(conn, learner_id)
        ctx   = opl.build_context(loops)

        row = await conn.fetchrow(
            "SELECT latest_pattern_message FROM learner_state.pattern_state WHERE learner_id=$1",
            learner_id,
        )
        parts = []
        if ctx:
            parts.append(ctx)
        if row and row["latest_pattern_message"]:
            snippet = row["latest_pattern_message"][:80]
            parts.append(f"Cross-scale wonder: '{snippet}…'")
        return " ".join(parts)
