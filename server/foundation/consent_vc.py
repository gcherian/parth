"""
foundation.consent_vc — DPDP-compliant parental consent lifecycle.

Consent under DPDP (Digital Personal Data Protection Act, India) requires:
  - Explicit, informed, specific, and freely given consent (Sec. 6)
  - Verifiable parental consent for children (Sec. 9)
  - Purpose limitation and data minimisation
  - Withdrawal mechanism
  - Audit trail

Flow:
  1. Guardian calls initiate_consent() → OTP sent to their email/phone
  2. Guardian submits OTP to complete_consent() → ParentalConsentVC issued
  3. Every sensitive endpoint calls check_active_consent() → fast DB query
  4. Guardian may call withdraw_consent() → VC revoked, guardian_links updated
"""

import json
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from foundation.audit import log_access
from foundation.db import get_pool
from foundation.observability import get_logger
from foundation.otp import send_otp, verify_otp

log = get_logger("foundation.consent_vc")

# ── DPDP constants ────────────────────────────────────────────────────────────

CONSENT_VERSION = "1.0"
CONSENT_PURPOSE = "AI-powered personalised tutoring for children under DPDP Sec. 6 & 9"
LAWFUL_BASIS = "explicit_consent"
DATA_CATEGORIES = [
    "interaction_history",
    "learning_profile",
    "emotional_indicators",
]
RETENTION_DAYS = 365


# ── Step 1: Initiate (OTP dispatch) ──────────────────────────────────────────

async def initiate_consent(
    guardian_did: str,
    child_id: _uuid.UUID,
    scope: list[str],
    guardian_email: str,
    guardian_ip: Optional[str] = None,
) -> _uuid.UUID:
    """
    Begins the consent flow by dispatching an OTP to the guardian's email.
    Returns the otp_token_id UUID needed for complete_consent().
    """
    metadata = {
        "child_id": str(child_id),
        "scope": scope,
    }
    token_id = await send_otp(
        guardian_did=guardian_did,
        purpose="consent_grant",
        delivery_address=guardian_email,
        metadata=metadata,
    )
    await log_access(
        caller_did=guardian_did,
        caller_role="guardian",
        action="consent_initiate",
        resource_type="consent",
        resource_id=str(child_id),
        success=True,
        caller_ip=guardian_ip,
    )
    log.info("consent_initiated", guardian_did=guardian_did, child_id=str(child_id))
    return token_id


# ── Step 2: Complete (OTP verification → VC issuance) ───────────────────────

async def complete_consent(
    guardian_did: str,
    child_id: _uuid.UUID,
    scope: list[str],
    otp_token_id: _uuid.UUID,
    submitted_otp: str,
    channel: str = "app_otp",
    guardian_ip: Optional[str] = None,
) -> dict:
    """
    Verifies the OTP, issues a ParentalConsentVC, and persists the consent
    record. Also updates the legacy guardian_links table for backward compat.
    Returns the signed VC dict.
    Raises ValueError on OTP failure.
    """
    # Import here to avoid circular at module load time
    from foundation import did as did_module, vc as vc_module

    # Verify OTP
    ok, meta = await verify_otp(
        guardian_did=guardian_did,
        purpose="consent_grant",
        token_id=otp_token_id,
        submitted_otp=submitted_otp,
    )
    if not ok:
        await log_access(
            caller_did=guardian_did,
            caller_role="guardian",
            action="consent_otp_failed",
            resource_type="consent",
            resource_id=str(child_id),
            success=False,
            denial_reason="invalid_or_expired_otp",
            caller_ip=guardian_ip,
        )
        raise ValueError("OTP verification failed — invalid or expired code")

    # Get server issuer DID + key
    server_did, server_key = await did_module.get_server_did()

    # Resolve subject DID (guardian's DID)
    expires_at = datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)

    credential_subject = {
        "guardianDid": guardian_did,
        "childId": str(child_id),
        "purpose": CONSENT_PURPOSE,
        "lawfulBasis": LAWFUL_BASIS,
        "dataCategories": DATA_CATEGORIES,
        "scope": scope,
        "consentVersion": CONSENT_VERSION,
        "channel": channel,
        "otpVerified": True,
        "retentionDays": RETENTION_DAYS,
        "grantedAt": datetime.now(timezone.utc).isoformat(),
    }

    vc = await vc_module.issue_vc(
        issuer_did=server_did,
        issuer_private_key=server_key,
        subject_did=guardian_did,
        vc_types=["ParentalConsentCredential"],
        credential_subject=credential_subject,
        validity_days=RETENTION_DAYS,
    )

    credential_db_id = _uuid.UUID(vc["_db_id"])

    # Persist consent record
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO foundation.consent_records (
                credential_id, guardian_did, child_id, purpose, lawful_basis,
                data_categories, scope, consent_version, channel,
                retention_days, otp_verified, guardian_ip, expires_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9,
                $10, true, $11::inet, $12
            )
            """,
            credential_db_id,
            guardian_did,
            child_id,
            CONSENT_PURPOSE,
            LAWFUL_BASIS,
            DATA_CATEGORIES,
            scope,
            CONSENT_VERSION,
            channel,
            RETENTION_DAYS,
            guardian_ip,
            expires_at,
        )

        # Backward compat: update guardian_links
        guardian_row = await conn.fetchrow(
            "SELECT identity_id FROM foundation.did_documents WHERE did = $1",
            guardian_did,
        )
        if guardian_row:
            guardian_identity_id = guardian_row["identity_id"]
            await conn.execute(
                """
                INSERT INTO foundation.guardian_links
                    (guardian_id, child_id, consent_given, consent_ts, scope)
                VALUES ($1, $2, true, now(), $3)
                ON CONFLICT (guardian_id, child_id) DO UPDATE
                    SET consent_given = true, consent_ts = now(), scope = $3
                """,
                guardian_identity_id,
                child_id,
                scope,
            )

    await log_access(
        caller_did=guardian_did,
        caller_role="guardian",
        action="consent_granted",
        resource_type="consent",
        resource_id=str(child_id),
        success=True,
        caller_ip=guardian_ip,
    )
    log.info("consent_granted", guardian_did=guardian_did, child_id=str(child_id), scope=scope)
    return vc


# ── Withdrawal ────────────────────────────────────────────────────────────────

async def withdraw_consent(
    guardian_did: str,
    child_id: _uuid.UUID,
    reason: str = "",
    guardian_ip: Optional[str] = None,
) -> bool:
    """
    Withdraws active consent for a guardian/child pair.
    Revokes the VC, updates consent_records and guardian_links.
    Returns True if consent was found and withdrawn.
    """
    from foundation import vc as vc_module

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, credential_id FROM foundation.consent_records
            WHERE guardian_did = $1 AND child_id = $2
              AND withdrawn_at IS NULL
            ORDER BY granted_at DESC
            LIMIT 1
            """,
            guardian_did,
            child_id,
        )
        if row is None:
            log.warning("consent_not_found_for_withdrawal",
                        guardian_did=guardian_did, child_id=str(child_id))
            return False

        consent_record_id = row["id"]
        credential_id = row["credential_id"]

        await conn.execute(
            """
            UPDATE foundation.consent_records
            SET withdrawn_at = now(), withdrawal_reason = $3
            WHERE id = $1 AND guardian_did = $2
            """,
            consent_record_id,
            guardian_did,
            reason,
        )

        # Update legacy guardian_links
        guardian_row = await conn.fetchrow(
            "SELECT identity_id FROM foundation.did_documents WHERE did = $1",
            guardian_did,
        )
        if guardian_row:
            await conn.execute(
                """
                UPDATE foundation.guardian_links
                SET consent_given = false
                WHERE guardian_id = $1 AND child_id = $2
                """,
                guardian_row["identity_id"],
                child_id,
            )

    # Revoke the VC
    if credential_id:
        await vc_module.revoke_vc(str(credential_id), reason=reason or "guardian_withdrawal")

    await log_access(
        caller_did=guardian_did,
        caller_role="guardian",
        action="consent_withdrawn",
        resource_type="consent",
        resource_id=str(child_id),
        success=True,
        caller_ip=guardian_ip,
    )
    log.info("consent_withdrawn", guardian_did=guardian_did, child_id=str(child_id))
    return True


# ── Hot-path consent check ────────────────────────────────────────────────────

async def check_active_consent(
    child_id_str: str,
    required_scope: str,
) -> tuple[bool, str]:
    """
    Fast DB-only check: does this child have active, non-expired, non-withdrawn
    consent covering required_scope?
    Returns (True, "ok") or (False, reason).
    """
    try:
        child_uuid = _uuid.UUID(child_id_str)
    except ValueError:
        return False, "invalid_child_id"

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id FROM foundation.consent_records
            WHERE child_id = $1
              AND withdrawn_at IS NULL
              AND (expires_at IS NULL OR expires_at > now())
              AND $2 = ANY(scope)
            ORDER BY granted_at DESC
            LIMIT 1
            """,
            child_uuid,
            required_scope,
        )

    if row is None:
        return False, "no_active_consent"
    return True, "ok"


# ── Consent history (DPDP data portability) ───────────────────────────────────

async def get_consent_history(child_id_str: str) -> list[dict]:
    """
    Returns all consent records for a child (active and withdrawn).
    Used for DPDP data portability / right to information requests.
    """
    try:
        child_uuid = _uuid.UUID(child_id_str)
    except ValueError:
        return []

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                id, guardian_did, purpose, lawful_basis, data_categories,
                scope, consent_version, channel, otp_verified,
                granted_at, expires_at, withdrawn_at, withdrawal_reason,
                retention_days
            FROM foundation.consent_records
            WHERE child_id = $1
            ORDER BY granted_at DESC
            """,
            child_uuid,
        )

    return [
        {
            "id": str(r["id"]),
            "guardian_did": r["guardian_did"],
            "purpose": r["purpose"],
            "lawful_basis": r["lawful_basis"],
            "data_categories": list(r["data_categories"] or []),
            "scope": list(r["scope"] or []),
            "consent_version": r["consent_version"],
            "channel": r["channel"],
            "otp_verified": r["otp_verified"],
            "granted_at": r["granted_at"].isoformat() if r["granted_at"] else None,
            "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
            "withdrawn_at": r["withdrawn_at"].isoformat() if r["withdrawn_at"] else None,
            "withdrawal_reason": r["withdrawal_reason"],
            "retention_days": r["retention_days"],
            "status": "withdrawn" if r["withdrawn_at"] else "active",
        }
        for r in rows
    ]
