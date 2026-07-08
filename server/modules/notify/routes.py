"""
Pilot ops comms API — send a templated reminder over email, SMS, or
WhatsApp, and log the attempt so a pilot lead can see why something
didn't land.

Not a general-purpose CMS: templates are a small hardcoded registry
below. Add a template here when a real pilot-comms need shows up.
"""
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from foundation.db import get_pool
from foundation.notify_transport import CHANNELS
from foundation.observability import get_logger

log = get_logger("notify.routes")

router = APIRouter(prefix="/notify", tags=["notify"])


# ── Template registry ──────────────────────────────────────────────────────────

TEMPLATES: dict[str, dict[str, str]] = {
    "pilot_welcome": {
        "subject": "Welcome to the Parth pilot",
        "body": (
            "Namaste {name},\n\n"
            "Thank you for joining the Parth pilot at {school}. "
            "Parth is ready whenever your child is — just open the app.\n\n"
            "— The Parth Team"
        ),
    },
    "teacher_form_reminder": {
        "subject": "A quick favor for {student_name}",
        "body": (
            "Namaste {teacher_name},\n\n"
            "Could you share a few minutes to fill in {student_name}'s learning "
            "portrait? It helps Parth teach them better: {link}\n\n"
            "— The Parth Team"
        ),
    },
}


class NotifySendRequest(BaseModel):
    to: str
    channel: Literal["email", "sms", "whatsapp"]
    template: str
    params: Optional[dict] = None


@router.get("/templates")
async def list_templates():
    return {
        name: {"subject": t["subject"], "body": t["body"]}
        for name, t in TEMPLATES.items()
    }


@router.post("/send")
async def send_notification(body: NotifySendRequest):
    template = TEMPLATES.get(body.template)
    if template is None:
        raise HTTPException(status_code=422, detail=f"unknown template: {body.template}")

    params = body.params or {}
    try:
        subject = template["subject"].format(**params)
        message = template["body"].format(**params)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"missing template param: {exc}")

    sender = CHANNELS[body.channel]
    delivered = await sender(body.to, subject, message)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO notify.log (recipient, channel, template, status, error)
            VALUES ($1, $2, $3, $4, $5)
            """,
            body.to, body.channel, body.template,
            "sent" if delivered else "failed",
            None if delivered else "delivery_failed",
        )

    if not delivered:
        raise HTTPException(status_code=502, detail="delivery failed — check server logs")

    return {"status": "sent", "channel": body.channel, "to": body.to}
