"""Agent 17 — Episodic Memory: stores and recalls meaningful learning moments."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import episodes as epi


class EpisodicMemoryAgent(LearnerAgent):
    name = "episodic_memory"
    phase = "both"
    memory_window = "permanent"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            ep_type = epi.detect_type(signals.message)
            if ep_type:
                patterns = await epi.get_patterns_for_message(conn, signals.concepts)
                await epi.store(
                    conn, signals.learner_id, ep_type,
                    signals.message, signals.concepts, patterns,
                )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            episodes = await epi.load_for_prompt(conn, learner_id)
            return epi.build_episode_context(episodes)
        except Exception:
            return ""
