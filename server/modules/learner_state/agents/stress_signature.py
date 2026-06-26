"""Agent 08 — Stress Signature: recent emotional pattern from history."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals

_NEGATIVE = {"confused", "frustrated", "anxious", "sad", "distressed"}


class StressSignatureAgent(LearnerAgent):
    name = "stress_signature"
    phase = "both"
    memory_window = "week"

    async def observe(self, signals: AgentSignals, conn) -> None:
        pass  # emotion_history updated by sessional_emotion agent

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            rows = await conn.fetch(
                """
                SELECT emotion FROM learner_state.emotion_history
                WHERE learner_id = $1
                ORDER BY recorded_at DESC
                LIMIT 5
                """,
                learner_id,
            )
            if not rows:
                return ""
            n_neg = sum(1 for r in rows if r["emotion"] in _NEGATIVE)
            if n_neg == 0:
                return ""
            if n_neg >= 4:
                level = "high"
            elif n_neg >= 2:
                level = "medium"
            else:
                level = "low"
            return f"Stress: {level} ({n_neg}/5 recent negative)."
        except Exception:
            return ""
