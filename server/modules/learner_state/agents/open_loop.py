"""Agent 18 — Open Loop: plants and surfaces unresolved wonder questions."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import open_loops as opl
from modules.learner_state import episodes as epi
from foundation.observability import get_logger

log = get_logger("learner.state.agents.open_loop")


class OpenLoopAgent(LearnerAgent):
    name = "open_loop"
    phase = "both"
    memory_window = "week"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            await opl.expire_old(conn, signals.learner_id)
            ep_type    = epi.detect_type(signals.message)
            total_q    = signals.total_questions + 1
            if opl.should_generate(total_q, ep_type):
                recent_episodes = await epi.load_for_prompt(conn, signals.learner_id)
                # threads from curiosity_tracker events (best-effort)
                threads = signals.events.get("curiosity.threads", [])
                q_text, q_concepts = opl.generate(
                    concepts=signals.concepts,
                    episodes=recent_episodes,
                    threads=threads,
                )
                if q_text:
                    await opl.store(
                        conn, signals.learner_id, q_text,
                        q_concepts or signals.concepts,
                    )
                    log.debug("open_loop_generated", learner_id=signals.learner_id,
                              question=q_text[:60])
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            await opl.expire_old(conn, learner_id)
            loops = await opl.load_open(conn, learner_id)
            return opl.build_context(loops)
        except Exception:
            return ""
