"""
Survey links — tokenized, trackable invitations to the teacher feedback
form, issued from the app instead of being one static URL for everyone.

Uses a plain HS256 JWT (foundation.auth uses Ed25519 for identity-bound
auth tokens — a different problem than a short-lived, unauthenticated
share link, so this deliberately doesn't reuse that machinery).
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt as _jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import Config
from foundation.db import get_pool
from foundation.observability import get_logger

log = get_logger("survey.routes")

router = APIRouter(prefix="/survey", tags=["survey"])

JWT_ALGORITHM = "HS256"


class SurveyLinkRequest(BaseModel):
    school_id: str
    teacher_phone: Optional[str] = None
    expires_in_hours: int = 72


@router.post("/link")
async def create_survey_link(body: SurveyLinkRequest):
    school_id = body.school_id.strip()
    if not school_id:
        raise HTTPException(status_code=422, detail="school_id required")

    token_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours)

    payload = {
        "jti": token_id,
        "school_id": school_id,
        "teacher_phone": body.teacher_phone,
        "exp": expires_at,
    }
    token = _jwt.encode(payload, Config.SURVEY_LINK_SECRET, algorithm=JWT_ALGORITHM)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO teacher.survey_links (id, school_id, teacher_phone, token, expires_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            token_id, school_id, body.teacher_phone, token, expires_at,
        )

    log.info("survey_link_issued", school_id=school_id, token_id=token_id)

    # Relative path only — this server may sit behind an arbitrary reverse
    # proxy or tunnel and has no reliable way to know its own public
    # domain. The caller (CLI) knows the address it was reached at and
    # builds the full shareable URL / wa.me / mailto links from this.
    return {
        "url": f"/teacher/form?token={token}",
        "expires_at": expires_at.isoformat(),
    }


async def verify_survey_token(token: str) -> Optional[dict]:
    """Decode + validate a survey-link token. Returns claims, or None if invalid/expired."""
    try:
        return _jwt.decode(token, Config.SURVEY_LINK_SECRET, algorithms=[JWT_ALGORITHM])
    except _jwt.ExpiredSignatureError:
        log.warning("survey_token_expired")
        return None
    except _jwt.InvalidTokenError as exc:
        log.warning("survey_token_invalid", error=str(exc))
        return None


async def mark_survey_link_opened(token: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE teacher.survey_links SET opened_at = now()
            WHERE token = $1 AND opened_at IS NULL
            """,
            token,
        )
