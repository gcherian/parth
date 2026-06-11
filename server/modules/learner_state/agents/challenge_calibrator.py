"""Challenge Calibrator — productive struggle window; faded scaffolding.

Ref: Kapur and Bielaczyc, "Designing for Productive Failure" —
generation before consolidation; challenge-but-not-frustration sweet spot.
Back off when distress rises; no coercive streaks or shame mechanics.
"""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals

_STRUGGLE = {"i can't", "too hard", "give up", "mushkil", "samajh nahi", "makes no sense", "i don't get"}
_PERSIST  = {"wait", "oh i get", "so it's", "oh i see", "aha", "now i understand", "oh that makes"}


class ChallengeCalibratorAgent(LearnerAgent):
    name = "challenge_calibrator"
    phase = "both"
    memory_window = "session"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            msg_lower    = signals.message.lower()
            is_struggle  = any(w in msg_lower for w in _STRUGGLE)
            is_persist   = any(w in msg_lower for w in _PERSIST)
            distress     = signals.events.get("distress.detected", False)

            row = await conn.fetchrow(
                "SELECT consecutive_struggles, frustration_threshold, difficulty_level "
                "FROM learner_state.challenge_state WHERE learner_id=$1",
                signals.learner_id,
            )
            streaks   = (row["consecutive_struggles"] if row else 0) or 0
            threshold = (row["frustration_threshold"] if row else 3.0) or 3.0
            difficulty = (row["difficulty_level"] if row else 0.5) or 0.5

            if is_struggle or (distress and signals.events.get("concept.weak")):
                streaks += 1
            elif is_persist:
                streaks = max(0, streaks - 1)

            if is_persist and streaks == 0:
                threshold = min(5.0, threshold + 0.1)   # child building tolerance
            if distress and streaks >= 2:
                threshold = max(1.5, threshold - 0.2)   # lower bar on repeated distress

            difficulty = max(0.2, min(1.0,
                0.5 + (signals.engagement - 5) * 0.05 - streaks * 0.08))

            await conn.execute(
                """INSERT INTO learner_state.challenge_state
                   (learner_id, consecutive_struggles, frustration_threshold, difficulty_level, updated_at)
                   VALUES ($1,$2,$3,$4,now())
                   ON CONFLICT (learner_id) DO UPDATE
                   SET consecutive_struggles=$2, frustration_threshold=$3,
                       difficulty_level=$4, updated_at=now()""",
                signals.learner_id, streaks, threshold, difficulty,
            )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        if signals.events.get("distress.detected"):
            return {"difficulty.adjust": "down"}
        if signals.events.get("engagement.high"):
            return {"difficulty.adjust": "up"}
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                "SELECT consecutive_struggles, frustration_threshold, difficulty_level "
                "FROM learner_state.challenge_state WHERE learner_id=$1",
                learner_id,
            )
            if not row:
                return ""
            streaks    = row["consecutive_struggles"] or 0
            threshold  = row["frustration_threshold"] or 3.0
            difficulty = row["difficulty_level"] or 0.5
            if streaks >= int(threshold):
                return f"Struggle streak: {streaks} — validate effort, reduce complexity, offer a foothold."
            if difficulty > 0.7:
                return f"Flow state (difficulty={difficulty:.2f}) — raise the bar or open a far-transfer question."
            return f"Scaffolding: medium (streak={streaks}, difficulty={difficulty:.2f})."
        except Exception:
            return ""
