"""
Chrono-learning ritual confirmation API (business plan §8.4).

rhythm_time_steward infers a peak-focus hour per child. This API lets a
parent see that inferred window and turn it into a fixed, confirmed session
appointment — "a fixed, parent-set session time for between-class work" per
the plan. Reads and writes go through modules.learner_state.chrono_ritual,
which is also what rhythm_time_steward and the contextual lens consult, so
confirming a slot here immediately changes what those readers report.

Invariant 04 (business plan §9) applies to every string in this file: no
streak counts, no missed-day language, no urgency or guilt framing. This is
an appointment, not a streak — it only ever states a time.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from foundation.db import get_pool
from foundation.observability import get_logger
from modules.learner_state.chrono_ritual import (
    confirm_appointment,
    get_confirmed_appointment,
    get_inferred_window,
)

log = get_logger("chrono_ritual.routes")

router = APIRouter(prefix="/chrono-ritual", tags=["chrono-ritual"])


class ConfirmRitualRequest(BaseModel):
    confirmed_by: str = Field(..., max_length=100, description="Parent/guardian identifier confirming this slot.")
    hour_of_day: Optional[int] = Field(
        default=None, ge=0, le=23,
        description="Hour (24h) to fix as the session slot. Omit to confirm the current inferred peak hour as-is.",
    )
    days_of_week: Optional[list[int]] = Field(
        default=None,
        description="Days the slot applies, 0=Mon..6=Sun. Omit for every day.",
    )


def _require_learner_id(learner_id: str) -> str:
    if not learner_id or not learner_id.strip():
        raise HTTPException(status_code=400, detail="learner_id is required")
    return learner_id


@router.get("/{learner_id}/window")
async def get_window(learner_id: str):
    """
    Show a parent the system's currently inferred peak-focus window for
    their child, alongside any appointment already confirmed. Read-only —
    does not write anything.
    """
    _require_learner_id(learner_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        inferred = await get_inferred_window(conn, learner_id)
        appointment = await get_confirmed_appointment(conn, learner_id)

    return {
        "learner_id": learner_id,
        "inferred_peak_hour": inferred["peak_hour"],
        "has_inference_signal": inferred["has_signal"],
        "confirmed_appointment": appointment,
    }


@router.post("/{learner_id}/confirm")
async def confirm_ritual(learner_id: str, body: ConfirmRitualRequest):
    """
    A parent confirms (or adjusts) the fixed session slot for their child.
    If hour_of_day is omitted, confirms the current inferred peak hour
    as-is. Idempotent — confirming again replaces the prior slot.
    """
    _require_learner_id(learner_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        inferred = await get_inferred_window(conn, learner_id)
        hour = body.hour_of_day if body.hour_of_day is not None else inferred["peak_hour"]
        try:
            result = await confirm_appointment(
                conn,
                learner_id=learner_id,
                confirmed_by=body.confirmed_by,
                hour_of_day=hour,
                days_of_week=body.days_of_week,
                source_peak_hour=inferred["peak_hour"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        appointment = await get_confirmed_appointment(conn, learner_id)

    return {
        "learner_id": learner_id,
        "confirmed": result,
        "appointment": appointment,
    }
