"""Emotion Compass — calibrated P(affect) vector with uncertainty. First in dispatch."""
from __future__ import annotations
from typing import Any
from kernel.agent import BaseAgent, AgentSignals

_NEGATIVE = {"frustrated", "anxious", "distressed", "sad"}

# Emotion Model v2's gear-shift policy (emotion_engine.gear_shift) reads a
# trajectory, not a point value, and can fire while a shift is still in
# motion. "hold_steady" is the common case and adds no prompt line — only
# a real trajectory shift is worth surfacing. See EMOTION_MODEL_V2_DESIGN.md.
_GEAR_SHIFT_HINTS = {
    "frustration_ramp -> simplify_or_hint_now":
        "Trajectory: frustration is ramping up — simplify or offer a hint now, before it consolidates.",
    "boredom_drift -> inject_novelty":
        "Trajectory: engagement is drifting down — inject novelty or raise the stakes.",
    "curiosity_building -> lean_in_deepen":
        "Trajectory: curiosity is building — lean in and go deeper, don't interrupt.",
    "satisfied_winddown -> consolidate_praise":
        "Trajectory: winding down satisfied — consolidate, praise, close the loop.",
    "resolved_from_negative -> reinforce_and_cement":
        "Trajectory: just resolved from a negative state — reinforce this moment.",
}


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


class EmotionCompassAgent(BaseAgent):
    name = "emotion_compass"
    phase = "both"
    memory_window = "session"

    async def _observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
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

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if signals.engagement > 7.0:
            out["engagement.high"] = True
        if signals.emotion in _NEGATIVE:
            out["distress.detected"] = True
        # excited and amazed both signal high engagement and curiosity — treat equivalently
        if signals.emotion in {"curious", "amazed", "excited"}:
            out["curiosity.active"] = True
        return out

    async def _read(self, conn, learner_id: str) -> str:
        row = await conn.fetchrow(
            "SELECT frustration, confusion, boredom, curiosity, delight, uncertainty, "
            "affect_gear_shift FROM learner_state.affect_state WHERE learner_id=$1",
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
        line = (
            f"Affect: {dominant} (p={labels[dominant]:.2f}, uncertainty={row['uncertainty']:.2f}). "
            "Back off if distress; lean in if curious."
        )
        hint = _GEAR_SHIFT_HINTS.get(row["affect_gear_shift"])
        if hint:
            line = f"{line} {hint}"
        return line
