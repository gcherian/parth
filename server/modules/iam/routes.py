"""
IAM REST endpoints for Parth.

All routes are prefixed with /iam when included in main.py.

Endpoint groups:
  /iam/auth/...       DID-Auth challenge → JWT tokens
  /iam/consent/...    DPDP parental consent (Sec. 9)
  /iam/delegation/... Guardian → teacher delegated access
  /iam/audit/...      Append-only audit trail queries
"""
import uuid as _uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from foundation.auth import (
    get_caller,
    get_caller_optional,
    CallerContext,
    issue_challenge,
    verify_challenge,
    issue_tokens,
    decode_and_verify_token,
    revoke_token,
)
from foundation.consent_vc import (
    initiate_consent,
    complete_consent,
    withdraw_consent,
    check_active_consent,
    get_consent_history,
)
from foundation.delegated_access import (
    initiate_delegation,
    complete_delegation,
    revoke_delegation,
    list_delegations,
)
from foundation.did import (
    create_did_for_identity,
    resolve_did,
    get_did_for_identity,
)
from foundation.db import get_pool
from foundation.audit import log_access
from foundation.observability import get_logger

log = get_logger("iam.routes")

router = APIRouter(prefix="/iam", tags=["IAM"])


# ═══════════════════════════════════════════════════════════
# Auth — DID challenge flow
# ═══════════════════════════════════════════════════════════

class ChallengeResponse(BaseModel):
    nonce: str
    did: str
    expires_in: int = 300


class TokenRequest(BaseModel):
    did: str
    nonce: str
    signature: str = Field(..., description="Ed25519 signature of nonce bytes, base64url-encoded")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    role: str
    scopes: list[str]


class RefreshRequest(BaseModel):
    refresh_token: str


class RevokeRequest(BaseModel):
    jti: str


@router.get("/auth/challenge", response_model=ChallengeResponse)
async def auth_challenge(did: str) -> ChallengeResponse:
    """
    Step 1 of DID-Auth: get a one-time nonce to sign.
    The nonce expires in 5 minutes.
    """
    if not did.startswith("did:"):
        raise HTTPException(400, "Invalid DID format")
    nonce = await issue_challenge(did)
    return ChallengeResponse(nonce=nonce, did=did, expires_in=300)


@router.post("/auth/token", response_model=TokenResponse)
async def auth_token(body: TokenRequest) -> TokenResponse:
    """
    Step 2 of DID-Auth: submit signed nonce → receive JWT pair.
    """
    ok = await verify_challenge(body.did, body.nonce, body.signature)
    if not ok:
        raise HTTPException(401, "Challenge verification failed")
    result = await issue_tokens(body.did)
    return TokenResponse(**result)


@router.post("/auth/refresh", response_model=TokenResponse)
async def auth_refresh(body: RefreshRequest) -> TokenResponse:
    """Use a refresh token to obtain a new access token."""
    try:
        payload = await decode_and_verify_token(body.refresh_token)
    except HTTPException as exc:
        raise HTTPException(401, f"Invalid refresh token: {exc.detail}")
    if payload.get("token_type") != "refresh":
        raise HTTPException(400, "Not a refresh token")
    result = await issue_tokens(payload["sub"])
    return TokenResponse(**result)


@router.post("/auth/revoke", status_code=204)
async def auth_revoke(
    body: RevokeRequest,
    caller: CallerContext = Depends(get_caller),
) -> None:
    """Revoke a specific token by JTI."""
    # Callers can only revoke their own tokens unless admin
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT subject_did FROM foundation.auth_tokens WHERE jti = $1",
            _uuid.UUID(body.jti),
        )
    if not row:
        raise HTTPException(404, "Token not found")
    if row["subject_did"] != caller.did and caller.role != "admin":
        raise HTTPException(403, "Cannot revoke another caller's token")
    await revoke_token(body.jti)


# ═══════════════════════════════════════════════════════════
# Identity registration
# ═══════════════════════════════════════════════════════════

class RegisterChildRequest(BaseModel):
    name: str
    grade: int
    birth_year: Optional[int] = None


class RegisterGuardianRequest(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    child_id: _uuid.UUID


class IdentityResponse(BaseModel):
    identity_id: str
    did: str
    role: str


@router.post("/auth/register", response_model=IdentityResponse)
async def register_child(body: RegisterChildRequest) -> IdentityResponse:
    """
    Register a new child identity and create their DID.
    Returns identity_id and DID for use in auth flows.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        identity_id = _uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO foundation.identities (id, type, name, grade, birth_year)
            VALUES ($1, 'child', $2, $3, $4)
            """,
            identity_id, body.name, body.grade, body.birth_year,
        )
        # Assign child role
        await conn.execute(
            """
            INSERT INTO foundation.role_assignments (identity_id, role)
            VALUES ($1, 'child')
            ON CONFLICT DO NOTHING
            """,
            identity_id,
        )

    did, _ = await create_did_for_identity(identity_id, save_private=True)
    return IdentityResponse(identity_id=str(identity_id), did=did, role="child")


@router.post("/auth/register/guardian", response_model=IdentityResponse)
async def register_guardian(body: RegisterGuardianRequest) -> IdentityResponse:
    """
    Register a guardian identity, link them to a child, and create their DID.
    Consent is NOT granted here — use /consent/request after registration.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check child exists
        child_row = await conn.fetchrow(
            "SELECT id FROM foundation.identities WHERE id = $1 AND type = 'child'",
            body.child_id,
        )
        if not child_row:
            raise HTTPException(404, "Child identity not found")

        identity_id = _uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO foundation.identities (id, type, name)
            VALUES ($1, 'guardian', $2)
            """,
            identity_id, body.name,
        )
        # Assign guardian role
        await conn.execute(
            """
            INSERT INTO foundation.role_assignments (identity_id, role)
            VALUES ($1, 'guardian')
            ON CONFLICT DO NOTHING
            """,
            identity_id,
        )

        # Create guardian_links row (no consent yet)
        await conn.execute(
            """
            INSERT INTO foundation.guardian_links
              (guardian_id, child_id, consent_given, email, phone)
            VALUES ($1, $2, false, $3, $4)
            ON CONFLICT (guardian_id, child_id) DO UPDATE
              SET email = EXCLUDED.email, phone = EXCLUDED.phone
            """,
            identity_id, body.child_id, body.email, body.phone,
        )

    did, _ = await create_did_for_identity(identity_id, save_private=True)
    return IdentityResponse(identity_id=str(identity_id), did=did, role="guardian")


# ═══════════════════════════════════════════════════════════
# Consent (DPDP Sec. 9 — parental consent for children)
# ═══════════════════════════════════════════════════════════

class ConsentRequestBody(BaseModel):
    guardian_did: str
    child_id: _uuid.UUID
    guardian_email: str = Field(..., description="Guardian email for OTP delivery")
    scope: list[str] = Field(default_factory=lambda: ["ai_interaction"])


class ConsentVerifyBody(BaseModel):
    token_id: str
    otp: str
    child_id: _uuid.UUID
    guardian_did: str
    scope: list[str] = Field(default_factory=lambda: ["ai_interaction"])


class ConsentResponse(BaseModel):
    status: str
    token_id: Optional[str] = None
    vc_id: Optional[str] = None
    detail: Optional[str] = None


@router.post("/consent/request", response_model=ConsentResponse)
async def consent_request(request: Request, body: ConsentRequestBody) -> ConsentResponse:
    """
    DPDP Sec. 9: initiate parental consent.
    Sends an OTP to the guardian's email. Returns token_id needed for /consent/verify.
    """
    import os as _os, json as _json
    from foundation.db import get_pool as _get_pool
    token_id = await initiate_consent(
        guardian_did=body.guardian_did,
        child_id=body.child_id,
        scope=body.scope,
        guardian_email=body.guardian_email,
        guardian_ip=request.headers.get("x-forwarded-for") or (request.client.host if request.client else None),
    )
    resp = ConsentResponse(status="otp_sent", token_id=str(token_id))
    # In demo mode, surface the OTP so the investor can see the full flow live
    from foundation.otp import _demo_otp_store
    demo_otp = _demo_otp_store.get(str(token_id))
    if demo_otp:
        resp.detail = f"[DEMO] OTP={demo_otp} (would be emailed to {body.guardian_email} in production)"
    return resp


@router.post("/consent/verify", response_model=ConsentResponse)
async def consent_verify(request: Request, body: ConsentVerifyBody) -> ConsentResponse:
    """
    DPDP Sec. 9: complete consent after OTP verification.
    Issues a W3C ParentalConsentVC and activates the guardian_link.
    """
    try:
        token_uuid = _uuid.UUID(body.token_id)
    except ValueError:
        raise HTTPException(400, "Invalid token_id format")

    result = await complete_consent(
        guardian_did=body.guardian_did,
        child_id=body.child_id,
        scope=body.scope,
        otp_token_id=token_uuid,
        submitted_otp=body.otp,
        guardian_ip=request.headers.get("x-forwarded-for") or (request.client.host if request.client else None),
    )
    vc_id = result.get("id") or str(result.get("vc_id", ""))
    return ConsentResponse(status="consent_granted", vc_id=vc_id)


@router.delete("/consent/{child_id}", status_code=200)
async def consent_withdraw(
    child_id: _uuid.UUID,
    caller: CallerContext = Depends(get_caller),
) -> dict:
    """
    DPDP Sec. 6(4): withdraw consent.
    Only the guardian who granted consent can withdraw it.
    """
    if caller.role not in ("guardian", "admin"):
        raise HTTPException(403, "Only guardians can withdraw consent")
    if caller.role == "guardian" and not caller.owns_child(child_id):
        raise HTTPException(403, "Not your child")
    await withdraw_consent(guardian_did=caller.did, child_id=child_id)
    return {"status": "consent_withdrawn", "child_id": str(child_id)}


@router.get("/consent/{child_id}/history")
async def consent_history(
    child_id: _uuid.UUID,
    caller: CallerContext = Depends(get_caller),
) -> dict:
    """
    DPDP Sec. 6(7) + data portability: full consent history for a child.
    Accessible by the guardian or admin.
    """
    if caller.role not in ("guardian", "admin"):
        raise HTTPException(403, "Consent history restricted to guardians and admins")
    if caller.role == "guardian" and not caller.owns_child(child_id):
        raise HTTPException(403, "Not your child")
    history = await get_consent_history(str(child_id))
    return {"child_id": str(child_id), "history": history}


@router.get("/consent/{child_id}/status")
async def consent_status(
    child_id: _uuid.UUID,
    caller: CallerContext = Depends(get_caller_optional),
) -> dict:
    """Check current consent status for a child (used by server-internal calls)."""
    ok, reason = await check_active_consent(
        child_id_str=str(child_id), required_scope="ai_interaction"
    )
    return {"child_id": str(child_id), "active": ok, "reason": reason}


# ═══════════════════════════════════════════════════════════
# Delegation — guardian grants teacher scoped access
# ═══════════════════════════════════════════════════════════

class DelegationGrantBody(BaseModel):
    teacher_did: str
    child_id: _uuid.UUID
    scopes: list[str]
    valid_until: Optional[datetime] = None


class DelegationConfirmBody(BaseModel):
    token_id: str
    otp: str
    delegation_id: _uuid.UUID


class DelegationResponse(BaseModel):
    delegation_id: str
    token_id: Optional[str] = None
    status: str
    scopes: Optional[list[str]] = None
    delegate_did: Optional[str] = None
    vc_id: Optional[str] = None


@router.post("/delegation/grant", response_model=DelegationResponse)
async def delegation_grant(
    body: DelegationGrantBody,
    caller: CallerContext = Depends(get_caller),
) -> DelegationResponse:
    """
    Guardian initiates delegation of scoped access to a teacher.
    Sends OTP to guardian for SoD confirmation.
    """
    if caller.role not in ("guardian", "admin"):
        raise HTTPException(403, "Only guardians can grant delegation")
    if caller.role == "guardian" and not caller.owns_child(body.child_id):
        raise HTTPException(403, "Not your child")

    result = await initiate_delegation(
        guardian_did=caller.did,
        teacher_did=body.teacher_did,
        child_id=body.child_id,
        scopes=body.scopes,
        valid_until=body.valid_until,
    )
    return DelegationResponse(
        delegation_id=result["delegation_id"],
        token_id=result["token_id"],
        status="otp_sent",
    )


@router.post("/delegation/confirm", response_model=DelegationResponse)
async def delegation_confirm(
    body: DelegationConfirmBody,
    caller: CallerContext = Depends(get_caller),
) -> DelegationResponse:
    """Guardian confirms delegation via OTP → activates DelegatedAccessVC."""
    if caller.role not in ("guardian", "admin"):
        raise HTTPException(403, "Only guardians can confirm delegation")

    result = await complete_delegation(
        token_id=body.token_id,
        otp=body.otp,
        delegation_id=body.delegation_id,
        guardian_did=caller.did,
    )
    return DelegationResponse(
        delegation_id=result["delegation_id"],
        status=result["status"],
        scopes=result.get("scopes"),
        delegate_did=result.get("delegate_did"),
        vc_id=result.get("vc_id"),
    )


@router.delete("/delegation/{delegation_id}", status_code=200)
async def delegation_revoke(
    delegation_id: _uuid.UUID,
    caller: CallerContext = Depends(get_caller),
) -> dict:
    """Guardian revokes a previously granted delegation."""
    if caller.role not in ("guardian", "admin"):
        raise HTTPException(403, "Only guardians can revoke delegation")
    await revoke_delegation(delegation_id=delegation_id, guardian_did=caller.did)
    return {"status": "revoked", "delegation_id": str(delegation_id)}


@router.get("/delegation")
async def delegation_list(
    caller: CallerContext = Depends(get_caller),
) -> dict:
    """List all delegations granted by this guardian."""
    if caller.role not in ("guardian", "admin"):
        raise HTTPException(403, "Delegations are per-guardian")
    delegations = await list_delegations(caller.did)
    return {"delegations": [dict(d) for d in delegations]}


# ═══════════════════════════════════════════════════════════
# Audit trail — DPDP Sec. 6(7) data transparency
# ═══════════════════════════════════════════════════════════

@router.get("/audit/my")
async def audit_my(
    caller: CallerContext = Depends(get_caller),
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return the audit log for the calling identity (data portability)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, action, resource_type, resource_id,
                   success, denial_reason, endpoint, http_method, ts
            FROM foundation.audit_log
            WHERE caller_did = $1
            ORDER BY ts DESC
            LIMIT $2 OFFSET $3
            """,
            caller.did, limit, offset,
        )
    return {"entries": [dict(r) for r in rows], "count": len(rows)}


@router.get("/audit/child/{child_id}")
async def audit_child(
    child_id: _uuid.UUID,
    caller: CallerContext = Depends(get_caller),
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """
    Return audit entries related to a child (for guardian transparency).
    Only the child's guardian or admin can access this.
    """
    if caller.role not in ("guardian", "admin"):
        raise HTTPException(403, "Restricted to guardians and admins")
    if caller.role == "guardian" and not caller.owns_child(child_id):
        raise HTTPException(403, "Not your child")

    # Get child DID for audit lookup
    child_did = await get_did_for_identity(child_id)
    if not child_did:
        raise HTTPException(404, "Child identity not found")

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, caller_did, action, resource_type, resource_id,
                   success, denial_reason, endpoint, http_method, ts
            FROM foundation.audit_log
            WHERE caller_did = $1 OR resource_id = $2
            ORDER BY ts DESC
            LIMIT $3 OFFSET $4
            """,
            child_did, str(child_id), limit, offset,
        )
    return {"child_id": str(child_id), "entries": [dict(r) for r in rows], "count": len(rows)}


# ═══════════════════════════════════════════════════════════
# DID resolution (public)
# ═══════════════════════════════════════════════════════════

@router.get("/did/{did_url:path}")
async def did_resolve(did_url: str) -> dict:
    """
    Resolve a DID to its DID Document (public endpoint — no auth needed).
    Follows did:key spec for documents registered with Parth.
    """
    did_doc = await resolve_did(did_url)
    if not did_doc:
        raise HTTPException(404, f"DID not found: {did_url}")
    return did_doc
