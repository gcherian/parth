"""
foundation.otp — OTP generation and verification for SoD-gated operations.

Delivery backends:
  - email (default): SMTP via SMTP_HOST/PORT/USER/PASS/FROM env vars
  - sms: Twilio via TWILIO_SID/TOKEN/FROM env vars

Set OTP_TRANSPORT=email or OTP_TRANSPORT=sms in .env.
"""

import os
import random
import smtplib
import string
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Optional

import bcrypt

from foundation.db import get_pool
from foundation.observability import get_logger

log = get_logger("foundation.otp")

OTP_EXPIRY_MINUTES = 10
OTP_LENGTH = 6

# Demo-mode OTP store: token_id → plaintext OTP (in-memory, never used in prod)
_demo_otp_store: dict = {}


# ── OTP core ──────────────────────────────────────────────────────────────────

def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=OTP_LENGTH))


def _hash_otp(otp: str) -> str:
    return bcrypt.hashpw(otp.encode(), bcrypt.gensalt()).decode()


def _verify_otp_hash(otp: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(otp.encode(), hashed.encode())
    except Exception:
        return False


# ── Email delivery ────────────────────────────────────────────────────────────

async def _send_email(to_address: str, otp: str, purpose: str) -> bool:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")
    from_addr = os.getenv("SMTP_FROM", user)

    if not host or not user:
        log.error("smtp_not_configured", hint="Set SMTP_HOST/USER/PASS/FROM in .env")
        return False

    purpose_label = purpose.replace("_", " ").title()
    body = (
        f"Your Parth {purpose_label} code: {otp}\n\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n\n"
        "If you did not request this, please contact support immediately.\n\n"
        "— The Parth Team"
    )
    msg = MIMEText(body)
    msg["Subject"] = f"Parth — Your verification code: {otp}"
    msg["From"] = from_addr
    msg["To"] = to_address

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(from_addr, [to_address], msg.as_string())
        log.info("otp_email_sent", to=to_address, purpose=purpose)
        return True
    except Exception as exc:
        log.error("otp_email_failed", error=str(exc), to=to_address)
        return False


# ── SMS delivery (Twilio) ─────────────────────────────────────────────────────

async def _send_sms(to_phone: str, otp: str, purpose: str) -> bool:
    sid = os.getenv("TWILIO_SID", "")
    token = os.getenv("TWILIO_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM", "")

    if not sid or not token or not from_number:
        log.error("twilio_not_configured", hint="Set TWILIO_SID/TOKEN/FROM in .env")
        return False

    purpose_label = purpose.replace("_", " ").title()
    body = f"Parth {purpose_label}: {otp}. Expires in {OTP_EXPIRY_MINUTES} min. Do not share."

    try:
        from twilio.rest import Client  # type: ignore
        client = Client(sid, token)
        client.messages.create(body=body, from_=from_number, to=to_phone)
        log.info("otp_sms_sent", to=to_phone, purpose=purpose)
        return True
    except ImportError:
        log.error("twilio_not_installed", hint="pip install twilio")
        return False
    except Exception as exc:
        log.error("otp_sms_failed", error=str(exc), to=to_phone)
        return False


# ── Public API ────────────────────────────────────────────────────────────────

async def send_otp(
    guardian_did: str,
    purpose: str,
    delivery_address: str,
    metadata: Optional[dict] = None,
) -> _uuid.UUID:
    """
    Generates an OTP, stores it hashed, delivers it via OTP_TRANSPORT.
    Returns the token_id UUID for later verification.
    Raises RuntimeError if delivery fails.
    """
    import json
    otp = _generate_otp()
    otp_hash = _hash_otp(otp)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO foundation.otp_tokens
                (guardian_did, purpose, otp_hash, metadata, expires_at)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            guardian_did,
            purpose,
            otp_hash,
            json.dumps(metadata or {}),
            expires_at,
        )
    token_id: _uuid.UUID = row["id"]

    # Demo / dev mode: skip delivery, store OTP in memory, log to console.
    # NEVER enable in production — set DEMO_OTP_FORCE=true in the environment
    # for local/demo use only.
    DEMO_OTP_FORCE = os.getenv("DEMO_OTP_FORCE", "").strip().lower() in ("1", "true", "yes")
    if DEMO_OTP_FORCE or os.getenv("DEMO_OTP_VISIBLE", "").strip().lower() in ("1", "true", "yes"):
        _demo_otp_store[str(token_id)] = otp  # store for routes to read
        log.warning("DEMO_OTP",
                    otp=otp, token_id=str(token_id),
                    purpose=purpose, to=delivery_address)
        return token_id

    transport = os.getenv("OTP_TRANSPORT", "email").lower()
    if transport == "sms":
        delivered = await _send_sms(delivery_address, otp, purpose)
    else:
        delivered = await _send_email(delivery_address, otp, purpose)

    if not delivered:
        # Clean up the token so it can't be used after failed delivery
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM foundation.otp_tokens WHERE id = $1",
                token_id,
            )
        raise RuntimeError(f"OTP delivery failed via {transport} to {delivery_address}")

    log.info("otp_issued", token_id=str(token_id), purpose=purpose, transport=transport)
    return token_id


async def verify_otp(
    guardian_did: str,
    purpose: str,
    token_id: _uuid.UUID,
    submitted_otp: str,
) -> tuple[bool, dict]:
    """
    Verifies the OTP.
    Returns (True, metadata) on success, (False, {}) on failure.
    On success, marks the token as used so it cannot be reused.
    """
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT otp_hash, metadata, expires_at, used_at
            FROM foundation.otp_tokens
            WHERE id = $1 AND guardian_did = $2 AND purpose = $3
            """,
            token_id,
            guardian_did,
            purpose,
        )

    if row is None:
        log.warning("otp_not_found", token_id=str(token_id), purpose=purpose)
        return False, {}

    if row["used_at"] is not None:
        log.warning("otp_already_used", token_id=str(token_id))
        return False, {}

    if datetime.now(timezone.utc) > row["expires_at"]:
        log.warning("otp_expired", token_id=str(token_id))
        return False, {}

    if not _verify_otp_hash(submitted_otp, row["otp_hash"]):
        log.warning("otp_wrong_code", token_id=str(token_id))
        return False, {}

    # Mark as used
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE foundation.otp_tokens SET used_at = now() WHERE id = $1",
            token_id,
        )

    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)

    log.info("otp_verified", token_id=str(token_id), purpose=purpose)
    return True, metadata or {}
