"""
foundation.notify_transport — generic outbound message delivery.

Sibling to foundation.otp (which is OTP-specific and stays untouched).
This module sends arbitrary subject/body messages over email, SMS, or
WhatsApp, reusing the same SMTP_* / TWILIO_* credentials already
configured for OTP delivery.

Set TWILIO_WHATSAPP_FROM in .env to enable the whatsapp channel — a
Twilio WhatsApp-enabled sender number, e.g. "whatsapp:+14155238886"
(Twilio's sandbox number for pilot testing before a Meta-approved
production sender is provisioned).
"""

import os
import smtplib
from email.mime.text import MIMEText
from typing import Callable, Awaitable

from foundation.observability import get_logger

log = get_logger("foundation.notify_transport")


async def send_email(to: str, subject: str, body: str) -> bool:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")
    from_addr = os.getenv("SMTP_FROM", user)

    if not host or not user:
        log.error("smtp_not_configured", hint="Set SMTP_HOST/USER/PASS/FROM in .env")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(from_addr, [to], msg.as_string())
        log.info("notify_email_sent", to=to)
        return True
    except Exception as exc:
        log.error("notify_email_failed", error=str(exc), to=to)
        return False


async def send_sms(to: str, body: str) -> bool:
    sid = os.getenv("TWILIO_SID", "")
    token = os.getenv("TWILIO_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM", "")

    if not sid or not token or not from_number:
        log.error("twilio_not_configured", hint="Set TWILIO_SID/TOKEN/FROM in .env")
        return False

    try:
        from twilio.rest import Client  # type: ignore
        client = Client(sid, token)
        client.messages.create(body=body, from_=from_number, to=to)
        log.info("notify_sms_sent", to=to)
        return True
    except ImportError:
        log.error("twilio_not_installed", hint="pip install twilio")
        return False
    except Exception as exc:
        log.error("notify_sms_failed", error=str(exc), to=to)
        return False


async def send_whatsapp(to: str, body: str) -> bool:
    sid = os.getenv("TWILIO_SID", "")
    token = os.getenv("TWILIO_TOKEN", "")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "")

    if not sid or not token or not from_number:
        log.error("twilio_whatsapp_not_configured",
                   hint="Set TWILIO_SID/TOKEN/TWILIO_WHATSAPP_FROM in .env "
                        "(sandbox number works for pilot testing; production "
                        "needs a Meta-approved WhatsApp sender)")
        return False

    to_wa = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
    from_wa = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"

    try:
        from twilio.rest import Client  # type: ignore
        client = Client(sid, token)
        client.messages.create(body=body, from_=from_wa, to=to_wa)
        log.info("notify_whatsapp_sent", to=to_wa)
        return True
    except ImportError:
        log.error("twilio_not_installed", hint="pip install twilio")
        return False
    except Exception as exc:
        log.error("notify_whatsapp_failed", error=str(exc), to=to_wa)
        return False


ChannelSender = Callable[[str, str, str], Awaitable[bool]]

# email/sms take (to, subject, body); whatsapp/sms drop subject — the
# adapters below normalize to a single (to, subject, body) call shape so
# the /notify/send route doesn't need channel-specific branching.

async def _send_sms_adapter(to: str, subject: str, body: str) -> bool:
    return await send_sms(to, body)


async def _send_whatsapp_adapter(to: str, subject: str, body: str) -> bool:
    return await send_whatsapp(to, body)


CHANNELS: dict[str, ChannelSender] = {
    "email": send_email,
    "sms": _send_sms_adapter,
    "whatsapp": _send_whatsapp_adapter,
}
