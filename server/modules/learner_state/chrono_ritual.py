"""Chrono-learning ritual confirmation (business plan §8.4).

rhythm_time_steward infers a peak-focus hour per child (learner_state.rhythm_state).
This module turns that inference into a parent-confirmed, fixed session slot
(learner_state.session_appointment) and is the single place that decides
which of the two — confirmed appointment or raw inference — governs a given
read. Downstream readers (rhythm_time_steward._read, the contextual lens's
session pattern) call get_effective_schedule() rather than reading
rhythm_state directly, so both stay in sync once a parent confirms a slot.

Invariant 04 (business plan §9): it is an appointment, not a streak. Nothing
here may reference missed-day counts, streaks, or guilt/urgency language —
this module only ever states a time.
"""
from __future__ import annotations

from typing import Any, Optional

from foundation.observability import get_logger

log = get_logger("learner_state.chrono_ritual")

DEFAULT_HOUR = 15
ALL_DAYS = (0, 1, 2, 3, 4, 5, 6)  # Monday=0 .. Sunday=6


async def get_inferred_window(conn, learner_id: str) -> dict[str, Any]:
    """
    Read-only. rhythm_time_steward's current inferred peak-focus hour for
    this child, defaulting to DEFAULT_HOUR when no signal has been observed
    yet (mirrors rhythm_time_steward._read's own fallback).
    """
    row = await conn.fetchrow(
        "SELECT peak_hour, session_count_today, last_session_quality "
        "FROM learner_state.rhythm_state WHERE learner_id = $1",
        learner_id,
    )
    return {
        "peak_hour": int(row["peak_hour"]) if row and row["peak_hour"] is not None else DEFAULT_HOUR,
        "session_count_today": int(row["session_count_today"]) if row and row["session_count_today"] is not None else 0,
        "last_session_quality": float(row["last_session_quality"]) if row and row["last_session_quality"] is not None else None,
        "has_signal": row is not None,
    }


async def get_confirmed_appointment(conn, learner_id: str) -> Optional[dict[str, Any]]:
    """Read-only. The parent-confirmed appointment for this child, or None if unset."""
    row = await conn.fetchrow(
        """SELECT hour_of_day, days_of_week, source_peak_hour, confirmed_by, confirmed_at, updated_at
           FROM learner_state.session_appointment WHERE learner_id = $1""",
        learner_id,
    )
    if not row:
        return None
    return {
        "hour_of_day": int(row["hour_of_day"]),
        "days_of_week": list(row["days_of_week"]),
        "source_peak_hour": row["source_peak_hour"],
        "confirmed_by": row["confirmed_by"],
        "confirmed_at": row["confirmed_at"],
        "updated_at": row["updated_at"],
    }


async def confirm_appointment(
    conn,
    learner_id: str,
    confirmed_by: str,
    hour_of_day: int,
    days_of_week: Optional[list[int]] = None,
    source_peak_hour: Optional[int] = None,
) -> dict[str, Any]:
    """
    Precondition: hour_of_day is already resolved by the caller (the parent's
    chosen adjustment, or the current inferred peak hour if the parent is
    confirming as-is) and confirmed_by identifies the parent/guardian taking
    this action. This function does one thing — persist that decision — it
    does not itself read rhythm_state; call get_inferred_window() first.

    Effect: upserts exactly one row in learner_state.session_appointment for
    learner_id — a single fixed slot per child, not a history. Idempotent:
    calling again with the same or adjusted values replaces the prior row.

    Postcondition: learner_state.session_appointment holds one row for
    learner_id with this hour_of_day/days_of_week and a fresh confirmed_at.
    """
    if not learner_id:
        raise ValueError("learner_id is required")
    if not confirmed_by or not confirmed_by.strip():
        raise ValueError("confirmed_by is required — an appointment must be attributable to a parent/guardian")
    if not (0 <= hour_of_day <= 23):
        raise ValueError("hour_of_day must be between 0 and 23")
    days = sorted(set(days_of_week)) if days_of_week else list(ALL_DAYS)
    if any(d < 0 or d > 6 for d in days):
        raise ValueError("days_of_week entries must be 0 (Mon) through 6 (Sun)")

    who = confirmed_by.strip()
    await conn.execute(
        """INSERT INTO learner_state.session_appointment
               (learner_id, hour_of_day, days_of_week, source_peak_hour, confirmed_by, confirmed_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, now(), now())
           ON CONFLICT (learner_id) DO UPDATE
               SET hour_of_day = $2,
                   days_of_week = $3,
                   source_peak_hour = $4,
                   confirmed_by = $5,
                   confirmed_at = now(),
                   updated_at = now()""",
        learner_id, hour_of_day, days, source_peak_hour, who,
    )
    log.info(
        "session_appointment_confirmed",
        learner_id=learner_id, hour_of_day=hour_of_day, days_of_week=days, confirmed_by=who,
    )
    return {
        "learner_id": learner_id,
        "hour_of_day": hour_of_day,
        "days_of_week": days,
        "confirmed_by": who,
    }


async def get_effective_schedule(conn, learner_id: str) -> dict[str, Any]:
    """
    Read-only. The single source of truth for "when does this child's
    between-class session happen": the parent-confirmed appointment when one
    exists, else the raw rhythm_time_steward inference. Callers that need a
    schedule (live-session context, guardian reports) should call this
    rather than reading rhythm_state or session_appointment directly, so
    both stay consistent once a parent confirms a slot.
    """
    appointment = await get_confirmed_appointment(conn, learner_id)
    if appointment is not None:
        return {
            "hour": appointment["hour_of_day"],
            "days_of_week": appointment["days_of_week"],
            "source": "confirmed_appointment",
            "confirmed_by": appointment["confirmed_by"],
            "confirmed_at": appointment["confirmed_at"],
        }
    inferred = await get_inferred_window(conn, learner_id)
    return {
        "hour": inferred["peak_hour"],
        "days_of_week": list(ALL_DAYS),
        "source": "inferred",
        "confirmed_by": None,
        "confirmed_at": None,
    }
