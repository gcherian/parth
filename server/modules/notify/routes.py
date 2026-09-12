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
    "parent_weekly_report": {
        "subject": "{student_name}'s week, from {teacher_name}",
        # narrative is written in the teacher's voice and already signs off as
        # them (see modules.parent_dashboard.weekly_report) — no extra
        # signature appended here, to avoid double-signing.
        "body": "Namaste,\n\n{narrative}",
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


async def send_via_template(
    to: str, channel: str, template: str, params: Optional[dict] = None
) -> dict:
    """
    Render `template` from the registry with `params`, send it over `channel`,
    and log the attempt to notify.log.

    Precondition: template must be a key in TEMPLATES; params must supply
    every placeholder the template's subject/body reference.
    Effect: exactly one send attempt via CHANNELS[channel], then exactly one
    row appended to notify.log recording its outcome.
    Postcondition: returns {"status": "sent"|"failed", "channel", "to",
    "subject", "body"} — "body" is the rendered message, useful to callers
    (e.g. the weekly-report generator) that want to show what was actually
    sent. Raises ValueError for an unknown template or a missing param —
    callers map that to their own error handling (the /notify/send route
    below turns it into a 422).
    """
    tmpl = TEMPLATES.get(template)
    if tmpl is None:
        raise ValueError(f"unknown template: {template}")

    params = params or {}
    try:
        subject = tmpl["subject"].format(**params)
        message = tmpl["body"].format(**params)
    except KeyError as exc:
        raise ValueError(f"missing template param: {exc}")

    sender = CHANNELS[channel]
    delivered = await sender(to, subject, message)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO notify.log (recipient, channel, template, status, error)
            VALUES ($1, $2, $3, $4, $5)
            """,
            to, channel, template,
            "sent" if delivered else "failed",
            None if delivered else "delivery_failed",
        )
    log.info(
        "notify_dispatched",
        channel=channel, template=template,
        status="sent" if delivered else "failed",
    )

    return {
        "status": "sent" if delivered else "failed",
        "channel": channel, "to": to,
        "subject": subject, "body": message,
    }


@router.post("/send")
async def send_notification(body: NotifySendRequest):
    try:
        result = await send_via_template(body.to, body.channel, body.template, body.params)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if result["status"] != "sent":
        raise HTTPException(status_code=502, detail="delivery failed — check server logs")

    return {"status": "sent", "channel": body.channel, "to": body.to}
