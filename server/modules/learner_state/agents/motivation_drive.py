"""Motivation & Drive — voluntary return cadence under difficulty.

This avoids treating "high engagement in one turn" as motivation. The useful
MVP signal is whether the child comes back after friction: confusion,
misconception, low engagement, or frustration.
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, median
from typing import Any

from kernel.agent import AgentSignals, BaseAgent

_DIFFICULT_EMOTIONS = {"frustrated", "confused", "anxious", "distressed", "sad"}


def _field(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _is_difficult(row: Any) -> bool:
    emotion = str(_field(row, "emotion", "") or "").lower()
    engagement = float(_field(row, "engagement", 5.0) or 5.0)
    misconception = str(_field(row, "misconception", "") or "").strip()
    return bool(misconception) or emotion in _DIFFICULT_EMOTIONS or engagement < 4.5


def calculate_motivation_drive(interaction_rows: list[Any]) -> dict[str, Any]:
    """Estimate drive from active-day cadence and returns after hard turns."""
    dated_rows: list[dict[str, Any]] = []
    for row in interaction_rows:
        ts = _as_datetime(_field(row, "created_at"))
        if ts is None:
            continue
        dated_rows.append({
            "created_at": ts,
            "engagement": float(_field(row, "engagement", 5.0) or 5.0),
            "emotion": str(_field(row, "emotion", "") or ""),
            "misconception": str(_field(row, "misconception", "") or ""),
        })

    if not dated_rows:
        return {
            "score": None,
            "confidence": 0.0,
            "return_after_difficulty": None,
            "active_days_14": 0,
            "avg_gap_hours": None,
            "hard_return_count": 0,
            "evidence": {"reason": "no_interaction_history"},
        }

    rows = sorted(dated_rows, key=lambda r: r["created_at"])
    active_days = {r["created_at"].date().isoformat() for r in rows}

    hard_indices = [i for i, row in enumerate(rows[:-1]) if _is_difficult(row)]
    hard_returns = 0
    return_gaps: list[float] = []
    for i in hard_indices:
        start = rows[i]["created_at"]
        returned = next(
            (
                later["created_at"]
                for later in rows[i + 1:]
                if 2.0 <= (later["created_at"] - start).total_seconds() / 3600.0 <= 24 * 7
            ),
            None,
        )
        if returned is not None:
            hard_returns += 1
            return_gaps.append((returned - start).total_seconds() / 3600.0)

    if hard_indices:
        return_after_difficulty = hard_returns / len(hard_indices)
    else:
        return_after_difficulty = None

    day_gaps: list[float] = []
    days_sorted = sorted({r["created_at"].date() for r in rows})
    for prev, cur in zip(days_sorted, days_sorted[1:]):
        day_gaps.append(float((cur - prev).days))
    cadence_score = 1.0 if len(active_days) >= 5 else min(1.0, len(active_days) / 5.0)
    if day_gaps:
        cadence_score = max(0.0, min(1.0, cadence_score * (1.0 if median(day_gaps) <= 3 else 0.75)))

    engagement_score = max(0.0, min(1.0, mean(r["engagement"] for r in rows[-10:]) / 10.0))
    difficulty_score = return_after_difficulty if return_after_difficulty is not None else 0.55
    score = difficulty_score * 0.5 + cadence_score * 0.3 + engagement_score * 0.2

    confidence = min(1.0, 0.12 + len(rows) / 28.0 + (len(hard_indices) / 12.0))
    avg_gap_hours = mean(return_gaps) if return_gaps else None

    return {
        "score": round(score, 3),
        "confidence": round(confidence, 3),
        "return_after_difficulty": None if return_after_difficulty is None else round(return_after_difficulty, 3),
        "active_days_14": len(active_days),
        "avg_gap_hours": None if avg_gap_hours is None else round(avg_gap_hours, 1),
        "hard_return_count": hard_returns,
        "evidence": {
            "interaction_count": len(rows),
            "hard_turns": len(hard_indices),
            "engagement_recent": round(engagement_score, 3),
        },
    }


class MotivationDriveAgent(BaseAgent):
    name = "motivation_drive"
    phase = "both"
    memory_window = "month"

    async def _observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        rows = await conn.fetch(
            """SELECT created_at, engagement, emotion, misconception
               FROM learner_state.interactions
               WHERE learner_id=$1
               ORDER BY created_at DESC
               LIMIT 80""",
            signals.learner_id,
        )
        now_row = {
            "created_at": datetime.now(timezone.utc),
            "engagement": signals.engagement,
            "emotion": signals.emotion,
            "misconception": signals.misconception,
        }
        drive = calculate_motivation_drive([*list(rows), now_row])
        if drive["score"] is None:
            return

        await conn.execute(
            """INSERT INTO learner_state.motivation_drive_state
               (learner_id, drive_score, confidence, return_after_difficulty,
                active_days_14, avg_gap_hours, hard_return_count, evidence_json, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,now())
               ON CONFLICT (learner_id) DO UPDATE
               SET drive_score=$2, confidence=$3, return_after_difficulty=$4,
                   active_days_14=$5, avg_gap_hours=$6, hard_return_count=$7,
                   evidence_json=$8, updated_at=now()""",
            signals.learner_id,
            drive["score"],
            drive["confidence"],
            drive["return_after_difficulty"],
            drive["active_days_14"],
            drive["avg_gap_hours"],
            drive["hard_return_count"],
            drive["evidence"],
        )

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def _read(self, conn, learner_id: str) -> str:
        row = await conn.fetchrow(
            """SELECT drive_score, confidence, return_after_difficulty, active_days_14
               FROM learner_state.motivation_drive_state
               WHERE learner_id=$1""",
            learner_id,
        )
        if not row or (row["confidence"] or 0.0) < 0.25:
            return ""
        ret = row["return_after_difficulty"]
        if ret is None:
            return f"Drive: active on {row['active_days_14']} recent day(s); difficulty-return signal still emerging."
        return (
            f"Drive: {row['drive_score']:.2f}; returns after hard turns "
            f"{ret:.0%} of the time. Keep agency visible."
        )
