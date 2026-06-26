"""
Guardian → teacher delegated access.

Delegation flow:
  1. Guardian calls POST /delegation/grant {teacher_did, child_id, scopes, valid_until}
  2. Server sends OTP to guardian's registered email/phone
  3. Guardian calls POST /delegation/confirm {token_id, otp, delegation_id}
  4. Server verifies OTP → issues DelegatedAccessVC → stores in delegated_access table
  5. Teacher can now call delegated endpoints (ABAC require_delegation=true checks this table)

Revocation: guardian calls DELETE /delegation/{id}
  - Sets revoked_at in delegated_access
  - Revokes the associated DelegatedAccessVC
"""
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from foundation.db import get_pool
from foundation.otp import send_otp, verify_otp
from foundation.vc import issue_vc, revoke_vc
from foundation.did import get_server_did, get_did_for_identity
from foundation.audit import log_access
from foundation.observability import get_logger

log = get_logger("foundation.delegated_access")


async def initiate_delegation(
    *,
    guardian_did: str,
    teacher_did: str,
    child_id: _uuid.UUID,
    scopes: list[str],
    valid_until: Optional[datetime] = None,
) -> dict:
    """
    Begin delegation: verify guardian owns the child, send OTP, store pending delegation.
    Returns {delegation_id, token_id} — client needs both to complete.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Verify guardian→child link
        guardian_row = await conn.fetchrow(
            "SELECT identity_id FROM foundation.did_documents WHERE did = $1",
            guardian_did,
        )
        if not guardian_row:
            raise HTTPException(404, "Guardian DID not found")
        guardian_id = guardian_row["identity_id"]

        link = await conn.fetchrow(
            """
            SELECT 1 FROM foundation.guardian_links
            WHERE guardian_id = $1 AND child_id = $2 AND consent_given = true
            """,
            guardian_id, child_id,
        )
        if not link:
            raise HTTPException(403, "No active consent link for this child")

        # Verify teacher DID is registered
        teacher_row = await conn.fetchrow(
            "SELECT identity_id FROM foundation.did_documents WHERE did = $1",
            teacher_did,
        )
        if not teacher_row:
            raise HTTPException(404, "Teacher DID not found")
        teacher_id = teacher_row["identity_id"]

        # Verify teacher has teacher role
        role_row = await conn.fetchrow(
            "SELECT role FROM foundation.role_assignments WHERE identity_id = $1 LIMIT 1",
            teacher_id,
        )
        if not role_row or role_row["role"] not in ("teacher", "admin"):
            raise HTTPException(400, "Target identity is not a teacher")

        # Store pending delegation
        delegation_id = _uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO foundation.delegated_access
              (id, delegator_did, delegate_did, child_id, scopes, valid_until, confirmed)
            VALUES ($1, $2, $3, $4, $5, $6, false)
            """,
            delegation_id, guardian_did, teacher_did, child_id, scopes, valid_until,
        )

        # Get guardian contact for OTP
        contact_row = await conn.fetchrow(
            "SELECT email, phone FROM foundation.guardian_links WHERE guardian_id = $1 LIMIT 1",
            guardian_id,
        )

    email = contact_row["email"] if contact_row and contact_row.get("email") else None
    phone = contact_row["phone"] if contact_row and contact_row.get("phone") else None

    delivery_address = email or phone
    if not delivery_address:
        raise HTTPException(
            400,
            "Guardian has no registered contact (email/phone) for OTP delivery",
        )

    token_id = await send_otp(
        guardian_did=guardian_did,
        purpose="delegation_grant",
        delivery_address=delivery_address,
        metadata={
            "delegation_id": str(delegation_id),
            "teacher_did": teacher_did,
            "child_id": str(child_id),
        },
    )

    await log_access(
        caller_did=guardian_did,
        caller_role="guardian",
        action="delegation:initiate",
        resource_type="delegation",
        resource_id=str(delegation_id),
        endpoint="/delegation/grant",
        http_method="POST",
        success=True,
    )

    log.info(
        "delegation_initiated",
        delegation_id=delegation_id,
        guardian_did=guardian_did,
        teacher_did=teacher_did,
        child_id=child_id,
    )
    return {"delegation_id": str(delegation_id), "token_id": token_id}


async def complete_delegation(
    *,
    token_id: str,
    otp: str,
    delegation_id: _uuid.UUID,
    guardian_did: str,
) -> dict:
    """
    Verify OTP → issue DelegatedAccessVC → activate delegation.
    """
    try:
        token_uuid = _uuid.UUID(token_id)
    except ValueError:
        raise HTTPException(400, "Invalid token_id format")

    ok, ctx = await verify_otp(
        guardian_did=guardian_did,
        purpose="delegation_grant",
        token_id=token_uuid,
        submitted_otp=otp,
    )
    if not ok:
        raise HTTPException(400, "Invalid or expired OTP")

    if ctx.get("delegation_id") != str(delegation_id):
        raise HTTPException(400, "OTP context does not match delegation")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT delegator_did, delegate_did, child_id, scopes, valid_until, confirmed
            FROM foundation.delegated_access
            WHERE id = $1
            """,
            delegation_id,
        )
        if not row:
            raise HTTPException(404, "Delegation not found")
        if row["delegator_did"] != guardian_did:
            raise HTTPException(403, "Delegation belongs to a different guardian")
        if row["confirmed"]:
            raise HTTPException(409, "Delegation already confirmed")

    # Issue DelegatedAccessVC
    server_did = await get_server_did()
    vc = await issue_vc(
        issuer_did=server_did,
        subject_did=row["delegate_did"],
        vc_type="DelegatedAccessCredential",
        claims={
            "delegatedBy": row["guardian_did"],
            "forChild": str(row["child_id"]),
            "scopes": row["scopes"],
            "validUntil": row["valid_until"].isoformat() if row["valid_until"] else None,
        },
        expiry_days=(
            (row["valid_until"] - datetime.now(timezone.utc)).days
            if row["valid_until"]
            else 365
        ),
    )

    async with pool.acquire() as conn:
        vc_uuid = None
        if vc.get("id"):
            try:
                vc_uuid = _uuid.UUID(vc["id"].split(":")[-1])
            except (ValueError, AttributeError):
                pass
        await conn.execute(
            """
            UPDATE foundation.delegated_access
            SET confirmed = true, credential_id = $2
            WHERE id = $1
            """,
            delegation_id, vc_uuid,
        )

    await log_access(
        caller_did=guardian_did,
        caller_role="guardian",
        action="delegation:confirm",
        resource_type="delegation",
        resource_id=str(delegation_id),
        endpoint="/delegation/confirm",
        http_method="POST",
        success=True,
    )

    log.info(
        "delegation_confirmed",
        delegation_id=delegation_id,
        delegate_did=row["delegate_did"],
    )
    return {
        "delegation_id": str(delegation_id),
        "vc_id": vc.get("id"),
        "status": "active",
        "scopes": row["scopes"],
        "delegate_did": row["delegate_did"],
    }


async def revoke_delegation(
    *,
    delegation_id: _uuid.UUID,
    guardian_did: str,
) -> None:
    """Revoke delegation and the associated VC."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT delegator_did, credential_id FROM foundation.delegated_access WHERE id = $1",
            delegation_id,
        )
        if not row:
            raise HTTPException(404, "Delegation not found")
        if row["delegator_did"] != guardian_did:
            raise HTTPException(403, "Not your delegation")

        await conn.execute(
            "UPDATE foundation.delegated_access SET revoked_at = now() WHERE id = $1",
            delegation_id,
        )

        # Revoke associated VC if present
        if row.get("credential_id"):
            await revoke_vc(row["credential_id"])

    await log_access(
        caller_did=guardian_did,
        caller_role="guardian",
        action="delegation:revoke",
        resource_type="delegation",
        resource_id=str(delegation_id),
        endpoint="/delegation/revoke",
        http_method="DELETE",
        success=True,
    )
    log.info("delegation_revoked", delegation_id=delegation_id)


async def list_delegations(guardian_did: str) -> list[dict]:
    """Return all delegations granted by this guardian."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, delegate_did, child_id, scopes, valid_until,
                   confirmed, revoked_at, valid_from AS created_at
            FROM foundation.delegated_access
            WHERE delegator_did = $1
            ORDER BY valid_from DESC
            """,
            guardian_did,
        )
    return [dict(r) for r in rows]
