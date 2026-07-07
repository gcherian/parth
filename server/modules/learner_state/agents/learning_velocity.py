"""Learning Velocity — time-to-mastery normalized by ZPD distance.

This is intentionally separate from MasteryTracker. MasteryTracker answers
"what does the learner currently understand?" This agent answers "how quickly
are they moving toward mastery, given how far the current concept is from the
ZPD band?"
"""
from __future__ import annotations

from statistics import mean
from typing import Any

from config import Config
from kernel.agent import AgentSignals, BaseAgent


def _num(row: Any, key: str, default: float = 0.0) -> float:
    if isinstance(row, dict):
        value = row.get(key, default)
    else:
        try:
            value = row[key]
        except Exception:
            value = default
    return float(value if value is not None else default)


def _text(row: Any, key: str, default: str = "") -> str:
    if isinstance(row, dict):
        value = row.get(key, default)
    else:
        try:
            value = row[key]
        except Exception:
            value = default
    return str(value if value is not None else default)


def _zpd_distance(p_mastery: float, weak_threshold: float, strong_threshold: float) -> float:
    """0.0 inside the ZPD band, rising as a concept gets too easy or too hard."""
    if weak_threshold <= p_mastery <= strong_threshold:
        return 0.0
    if p_mastery < weak_threshold:
        return round(weak_threshold - p_mastery, 3)
    return round(p_mastery - strong_threshold, 3)


def calculate_learning_velocity(
    knowledge_rows: list[Any],
    kt_rows: list[Any] | None = None,
    *,
    weak_threshold: float = Config.MASTERY_WEAK_THRESHOLD,
    strong_threshold: float = Config.MASTERY_STRONG_THRESHOLD,
) -> dict[str, Any]:
    """
    Return a normalized learning-velocity estimate.

    The score is not a flat demonstrations/exposures ratio. It estimates turns
    to mastery from observed mastery gain, then normalizes that by how far the
    current concepts are from MasteryTracker's ZPD band.
    """
    if not knowledge_rows:
        return {
            "score": None,
            "confidence": 0.0,
            "zpd_distance": None,
            "time_to_mastery_turns": None,
            "sample_size": 0,
            "zpd_concepts": [],
            "evidence": {"reason": "no_concept_history"},
        }

    concept_estimates: list[dict[str, Any]] = []
    for row in knowledge_rows:
        concept_id = _text(row, "concept_id")
        exposures = max(1.0, _num(row, "exposures", 0.0))
        p_mastery = max(0.05, min(0.98, _num(row, "p_mastery", 0.05)))
        demonstrations = _num(row, "demonstrations", 0.0)
        misconceptions = _num(row, "misconceptions", 0.0)

        observed_gain = max(0.0, p_mastery - 0.05)
        gain_per_turn = max(0.015, observed_gain / exposures)
        remaining = max(0.0, strong_threshold - p_mastery)
        zpd_distance = _zpd_distance(p_mastery, weak_threshold, strong_threshold)

        # Far-outside-ZPD concepts should not look "slow" merely because they
        # are currently too easy or too hard. Normalize expected turns upward
        # by ZPD distance, then compare the learner to that expectation.
        expected_turns = 4.0 + zpd_distance * 14.0
        time_to_mastery = remaining / gain_per_turn if remaining > 0 else 0.0
        velocity = 1.0 if time_to_mastery == 0 else expected_turns / (expected_turns + time_to_mastery)

        # Penalize repeated misconceptions without collapsing a high-growth
        # learner to zero; this remains a velocity estimate, not mastery.
        misconception_penalty = max(0.65, 1.0 - 0.08 * misconceptions)
        success_signal = demonstrations / exposures
        score = max(0.0, min(1.0, (velocity * 0.75 + success_signal * 0.25) * misconception_penalty))

        concept_estimates.append({
            "concept_id": concept_id,
            "score": score,
            "p_mastery": p_mastery,
            "zpd_distance": zpd_distance,
            "time_to_mastery_turns": time_to_mastery,
            "exposures": int(exposures),
        })

    kt_rows = kt_rows or []
    recent_correct = [1.0 if bool(_num(row, "correct", 0.0)) else 0.0 for row in kt_rows]
    recent_rate = mean(recent_correct) if recent_correct else None

    base_score = mean(item["score"] for item in concept_estimates)
    if recent_rate is not None:
        base_score = base_score * 0.7 + recent_rate * 0.3

    avg_zpd_distance = mean(item["zpd_distance"] for item in concept_estimates)
    avg_time = mean(item["time_to_mastery_turns"] for item in concept_estimates)
    zpd_concepts = [
        item["concept_id"]
        for item in sorted(concept_estimates, key=lambda it: (it["zpd_distance"], -it["p_mastery"]))
        if item["zpd_distance"] <= 0.12
    ][:3]

    sample_size = int(sum(item["exposures"] for item in concept_estimates) + len(kt_rows))
    confidence = min(1.0, 0.15 + sample_size / 35.0)

    return {
        "score": round(base_score, 3),
        "confidence": round(confidence, 3),
        "zpd_distance": round(avg_zpd_distance, 3),
        "time_to_mastery_turns": round(avg_time, 1),
        "sample_size": sample_size,
        "zpd_concepts": zpd_concepts,
        "evidence": {
            "concept_count": len(concept_estimates),
            "recent_correct_rate": None if recent_rate is None else round(recent_rate, 3),
            "weak_threshold": weak_threshold,
            "strong_threshold": strong_threshold,
        },
    }


class LearningVelocityAgent(BaseAgent):
    name = "learning_velocity"
    phase = "both"
    memory_window = "month"

    async def _observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        cfg = await self.get_config(conn, signals.learner_id)
        weak_t = cfg.get("weak_threshold", Config.MASTERY_WEAK_THRESHOLD)
        strong_t = cfg.get("strong_threshold", Config.MASTERY_STRONG_THRESHOLD)

        knowledge_rows = await conn.fetch(
            """SELECT concept_id, exposures, demonstrations, misconceptions, p_mastery
               FROM learner_state.knowledge
               WHERE learner_id=$1
               ORDER BY last_updated DESC
               LIMIT 24""",
            signals.learner_id,
        )
        kt_rows = await conn.fetch(
            """SELECT correct
               FROM learner_state.kt_events
               WHERE learner_id=$1
               ORDER BY created_at DESC
               LIMIT 40""",
            signals.learner_id,
        )
        velocity = calculate_learning_velocity(
            list(knowledge_rows),
            list(kt_rows),
            weak_threshold=weak_t,
            strong_threshold=strong_t,
        )
        if velocity["score"] is None:
            return

        await conn.execute(
            """INSERT INTO learner_state.learning_velocity_state
               (learner_id, velocity_score, confidence, zpd_distance,
                time_to_mastery_turns, sample_size, evidence_json, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,now())
               ON CONFLICT (learner_id) DO UPDATE
               SET velocity_score=$2, confidence=$3, zpd_distance=$4,
                   time_to_mastery_turns=$5, sample_size=$6,
                   evidence_json=$7, updated_at=now()""",
            signals.learner_id,
            velocity["score"],
            velocity["confidence"],
            velocity["zpd_distance"],
            velocity["time_to_mastery_turns"],
            velocity["sample_size"],
            velocity["evidence"],
        )

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def _read(self, conn, learner_id: str) -> str:
        row = await conn.fetchrow(
            """SELECT velocity_score, confidence, zpd_distance, time_to_mastery_turns
               FROM learner_state.learning_velocity_state
               WHERE learner_id=$1""",
            learner_id,
        )
        if not row or (row["confidence"] or 0.0) < 0.25:
            return ""
        return (
            f"Learning velocity: {row['velocity_score']:.2f} "
            f"(ZPD distance={row['zpd_distance']:.2f}, "
            f"~{row['time_to_mastery_turns']:.1f} turns to mastery)."
        )
