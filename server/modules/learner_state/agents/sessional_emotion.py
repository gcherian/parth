"""Agent 07 — Sessional Emotion: current emotion + engagement level."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import profile as prof

_NEGATIVE = {"frustrated", "anxious", "distressed", "sad"}


class SessionalEmotionAgent(LearnerAgent):
    name = "sessional_emotion"
    phase = "both"
    memory_window = "session"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            await prof.update_emotion(conn, signals.learner_id, signals.emotion, signals.engagement)
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if signals.engagement > 7.0:
            out["engagement.high"] = True
        if signals.emotion in _NEGATIVE:
            out["distress.detected"] = True
        return out

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                "SELECT last_emotion, engagement_score FROM learner_state.profiles WHERE learner_id=$1",
                learner_id,
            )
            if not row:
                return "Current: neutral (engagement 5/10)."
            emotion    = row["last_emotion"] or "neutral"
            engagement = row["engagement_score"] or 5.0
            return f"Current: {emotion} (engagement {engagement:.0f}/10)."
        except Exception:
            return ""
