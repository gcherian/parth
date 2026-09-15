"""
attention_coarse — server-side receiving contract for Invariant 03.

Business plan §9: "Never use the camera for monitoring. Commitment: Focus
and fatigue inferred on-device from conversation only. Enforcement:
Federated attention layer — raw signals never leave the phone; only coarse
state is transmitted."

The on-device inference (camera/audio/conversation -> a coarse focus/fatigue
reading) is a mobile-client capability and is NOT implemented here. What
this module owns is the other half of the guarantee: an endpoint that
accepts only a coarse enum state per session, and actively rejects anything
shaped like raw signal (image/video bytes, embeddings, base64 blobs) rather
than merely documenting that such data should never be sent.

Do not confuse this with modules/population_priors (formerly
attention_federated) — that module aggregates concept-difficulty stats
across learners and has nothing to do with per-child attention/fatigue.
"""
import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from foundation.db import get_pool
from foundation.identity import check_consent, SCOPE_LEARNER_DATA
from foundation.observability import get_logger

log = get_logger("attention.coarse")

router = APIRouter(prefix="/attention", tags=["attention"])

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Field names that signal an attempt to smuggle raw signal through the
# payload, checked against the raw JSON body before Pydantic parsing — so a
# client can't dodge detection by giving raw data a field name we didn't
# anticipate declaring in the model (extra="forbid" below is the backstop
# for that case).
_RAW_SIGNAL_KEYS = {
    "image", "images", "image_base64", "frame", "frames", "frame_data",
    "video", "video_base64", "embedding", "embeddings", "raw_signal",
    "base64", "photo", "snapshot", "pixels", "audio", "audio_base64",
}


class CoarseStateRequest(BaseModel):
    """
    Precondition: child_id names an already-registered child identity
    (foundation.identity.register_pilot_learner) with active guardian
    consent covering SCOPE_LEARNER_DATA — checked in post_coarse_state()
    before the write, since this is real per-child behavioral data.
    """
    model_config = ConfigDict(extra="forbid")

    child_id:   str = Field(..., max_length=64)
    session_id: str = Field(..., min_length=1, max_length=128)
    state:      Literal["focused", "distracted", "fatigued"]
    ts:         datetime | None = None


def _reject_raw_signal(raw_body: dict) -> None:
    hit = _RAW_SIGNAL_KEYS & {str(k).lower() for k in raw_body.keys()}
    if hit:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "raw_signal_rejected",
                "message": (
                    "Invariant 03: only a coarse focus/fatigue state may be "
                    "transmitted from the device. Fields resembling raw "
                    "sensor data are not accepted."
                ),
                "rejected_fields": sorted(hit),
            },
        )


@router.post("/coarse-state")
async def post_coarse_state(request: Request):
    """
    Effect: inserts one coarse attention/fatigue state row for
    (child_id, session_id, ts). Idempotent — re-posting the same
    (child_id, session_id, ts) is a no-op (ON CONFLICT DO NOTHING).

    Rejects (422) any payload containing a raw-signal-shaped field, and
    (403) any child_id lacking active guardian consent for
    SCOPE_LEARNER_DATA. Stores only the coarse state — never raw signal.
    """
    try:
        raw_body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(raw_body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    _reject_raw_signal(raw_body)

    try:
        body = CoarseStateRequest(**raw_body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    if not _UUID_RE.match(body.child_id):
        raise HTTPException(status_code=400, detail="Invalid child_id format")

    if not await check_consent(body.child_id, SCOPE_LEARNER_DATA):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "parental_consent_required",
                "message": (
                    "A parent or guardian must give consent before attention "
                    "state can be recorded for this child."
                ),
            },
        )

    ts = body.ts or datetime.now(timezone.utc)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO attention_coarse.states (child_id, session_id, state, ts)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (child_id, session_id, ts) DO NOTHING
            """,
            body.child_id, body.session_id, body.state, ts,
        )

    log.info(
        "attention_coarse_state_received",
        child_id=body.child_id, session_id=body.session_id, state=body.state,
    )

    return {
        "status": "ok",
        "child_id": body.child_id,
        "session_id": body.session_id,
        "state": body.state,
    }
