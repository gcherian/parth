"""Agent 10 — Linguistic Register: Hindi/English mix from language_ratio."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import profile as prof


class LinguisticRegisterAgent(LearnerAgent):
    name = "linguistic_register"
    phase = "both"
    memory_window = "permanent"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            await prof.update_language(conn, signals.learner_id, signals.language_ratio)
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                "SELECT language_ratio FROM learner_state.profiles WHERE learner_id=$1",
                learner_id,
            )
            if not row:
                return ""
            ratio = row["language_ratio"] or 1.0
            if ratio > 0.75:
                return f"Language: English-dominant (ratio={ratio:.2f})."
            elif ratio < 0.35:
                return f"Language: Hindi-dominant (ratio={ratio:.2f})."
            else:
                return f"Language: Bilingual (ratio={ratio:.2f})."
        except Exception:
            return ""
