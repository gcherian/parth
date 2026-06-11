"""Emotion Compass — calibrated P(affect) vector with uncertainty. First in dispatch."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals

_NEGATIVE = {"frustrated", "anxious", "distressed", "sad"}


def _build_probs(emotion: str) -> dict[str, float]:
    e = emotion
    return {
        "frustration": 0.8 if e in {"frustrated", "distressed"} else (0.3 if e == "anxious" else 0.1),
        "confusion":   0.7 if e == "confused" else 0.15,
        "boredom":     0.6 if e == "bored" else 0.1,
        "curiosity":   0.8 if e == "curious" else (0.5 if e == "amazed" else 0.2),
        "delight":     0.8 if e in {"excited", "amazed", "delighted"} else 0.1,
    }


def _uncertainty(probs: dict) -> float:
    vals = list(probs.values())
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    return round(min(1.0, variance ** 0.5 * 2), 2)


class EmotionCompassAgent(LearnerAgent):
    name = "emotion_compass"
    phase = "both"
    memory_window = "session"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            await conn.execute(
                "INSERT INTO learner_state.emotion_history (learner_id, emotion, engagement) VALUES ($1,$2,$3)",
                signals.learner_id, signals.emotion, signals.engagement,
            )
            await conn.execute(
                "UPDATE learner_state.profiles SET last_emotion=$2, engagement_score=$3 WHERE learner_id=$1",
                signals.learner_id, signals.emotion, signals.engagement,
            )
            p = _build_probs(signals.emotion)
            await conn.execute(
                """INSERT INTO learner_state.affect_state
                   (learner_id, frustration, confusion, boredom, curiosity, delight, uncertainty, updated_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,now())
                   ON CONFLICT (learner_id) DO UPDATE
                   SET frustration=$2, confusion=$3, boredom=$4, curiosity=$5,
                       delight=$6, uncertainty=$7, updated_at=now()""",
                signals.learner_id,
                p["frustration"], p["confusion"], p["boredom"], p["curiosity"],
                p["delight"], _uncertainty(p),
            )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if signals.engagement > 7.0:
            out["engagement.high"] = True
        if signals.emotion in _NEGATIVE:
            out["distress.detected"] = True
        if signals.emotion in {"curious", "amazed"}:
            out["curiosity.active"] = True
        return out

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                "SELECT frustration, confusion, boredom, curiosity, delight, uncertainty "
                "FROM learner_state.affect_state WHERE learner_id=$1",
                learner_id,
            )
            if not row:
                p = await conn.fetchrow(
                    "SELECT last_emotion, engagement_score FROM learner_state.profiles WHERE learner_id=$1",
                    learner_id,
                )
                if not p:
                    return ""
                return f"Affect: {p['last_emotion']} (engagement {p['engagement_score']:.0f}/10)."
            labels = {"frustrated": row["frustration"], "confused": row["confusion"],
                      "bored": row["boredom"], "curious": row["curiosity"], "delighted": row["delight"]}
            dominant = max(labels, key=labels.get)
            return (
                f"Affect: {dominant} (p={labels[dominant]:.2f}, uncertainty={row['uncertainty']:.2f}). "
                "Back off if distress; lean in if curious."
            )
        except Exception:
            return ""
