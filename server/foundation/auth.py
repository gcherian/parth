"""
JWT-based DID authentication for Parth.

Design decisions:
  - Subjects in JWTs are W3C DID strings (did:key:...).
  - Tokens are signed with EdDSA (Ed25519) — the same key algorithm used for
    W3C Verifiable Credentials, so one key pair covers both systems.
  - REQUIRE_AUTH=false (default) skips token enforcement; a synthetic observer
    CallerContext is returned instead. This keeps the demo working without
    breaking any existing /chat endpoints.
  - LPA: scopes are minted per-role at issuance; callers cannot self-elevate.
  - JTI (JWT ID) is persisted in auth_tokens so tokens can be individually
    revoked without waiting for expiry.

DID-Auth challenge flow:
  1. Client calls GET /auth/challenge?did=<did:key:...>
  2. Server issues a nonce (stored 5 min in auth_challenges)
  3. Client signs nonce with private key → Ed25519 signature (base64url)
  4. Client calls POST /auth/token with {did, nonce, signature}
  5. Server verifies signature, issues access + refresh JWTs
"""
import base64
import os
import secrets
import uuid as _uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt as _jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import Config
from foundation.db import get_pool
from foundation.did import (
    get_server_did,
    get_private_key_for_did,
    resolve_did,
    get_did_for_identity,
)
from foundation.audit import log_access
from foundation.observability import get_logger

log = get_logger("foundation.auth")

# ── Config ────────────────────────────────────────────────────────────────────
REQUIRE_AUTH: bool = os.getenv("REQUIRE_AUTH", "false").lower() not in ("0", "false", "no")
JWT_ACCESS_TTL_MIN: int = int(os.getenv("JWT_ACCESS_TTL_MIN", "60"))
JWT_REFRESH_TTL_DAYS: int = int(os.getenv("JWT_REFRESH_TTL_DAYS", "30"))
_CHALLENGE_TTL_SEC: int = 300  # 5 minutes

# ── LPA: minimum required scopes per role ─────────────────────────────────────
ROLE_SCOPES: dict[str, list[str]] = {
    "child":    ["ai:interact", "profile:read_own"],
    "guardian": ["ai:interact", "profile:read_own", "consent:manage",
                 "delegation:grant", "audit:read_own"],
    "teacher":  ["ai:interact", "profile:read_own", "audit:read_delegated"],
    "admin":    ["ai:interact", "profile:read_own", "consent:manage",
                 "delegation:grant", "audit:read_own", "audit:read_all",
                 "admin:manage", "erasure:initiate"],
    "observer": ["profile:read_own"],
}


# ── CallerContext ─────────────────────────────────────────────────────────────
class CallerContext:
    """Parsed, verified identity attached to a request."""

    def __init__(
        self,
        did: str,
        identity_id: Optional[_uuid.UUID],
        role: str,
        scopes: list[str],
        children: list[_uuid.UUID],
        jti: Optional[str] = None,
        is_synthetic: bool = False,
    ):
        self.did = did
        self.identity_id = identity_id
        self.role = role
        self.scopes = scopes
        self.children = children
        self.jti = jti
        self.is_synthetic = is_synthetic

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    def owns_child(self, child_id: _uuid.UUID) -> bool:
        if self.role in ("admin",):
            return True
        if self.identity_id == child_id:
            return True
        return child_id in self.children

    def __repr__(self) -> str:
        return (
            f"CallerContext(role={self.role}, did={self.did[:20]}..., "
            f"scopes={self.scopes}, is_synthetic={self.is_synthetic})"
        )


# Observer stub used when REQUIRE_AUTH=false and no token is provided
_SYNTHETIC_OBSERVER = CallerContext(
    did="did:parth:synthetic:observer",
    identity_id=None,
    role="observer",
    scopes=ROLE_SCOPES["observer"],
    children=[],
    is_synthetic=True,
)

# ── HTTP Bearer scheme (optional) ─────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)


# ── Challenge / nonce flow ────────────────────────────────────────────────────
async def issue_challenge(did: str) -> str:
    """Store a one-time nonce for DID-Auth. Returns the nonce."""
    nonce = secrets.token_urlsafe(32)
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Delete any existing unused challenge for this DID before inserting
        await conn.execute(
            "DELETE FROM foundation.auth_challenges WHERE did = $1 AND used = false",
            did,
        )
        await conn.execute(
            """
            INSERT INTO foundation.auth_challenges (id, did, nonce, expires_at)
            VALUES ($1, $2, $3, now() + interval '5 minutes')
            """,
            _uuid.uuid4(), did, nonce,
        )
    return nonce


async def verify_challenge(did: str, nonce: str, signature_b64: str) -> bool:
    """
    Verify a signed DID-Auth challenge.
    The client signs the raw nonce bytes with their Ed25519 private key.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT nonce FROM foundation.auth_challenges
            WHERE did = $1 AND nonce = $2 AND expires_at > now()
            """,
            did, nonce,
        )
        if not row:
            return False
        # Mark nonce used immediately (one-time use)
        await conn.execute(
            "UPDATE foundation.auth_challenges SET used = true WHERE did = $1 AND nonce = $2",
            did, nonce,
        )

    # Resolve DID document and extract public key
    resolved = await resolve_did(did)
    if not resolved:
        return False

    from foundation.did import public_key_from_jwk
    import json as _json

    did_doc = resolved.get("did_document")
    if isinstance(did_doc, str):
        did_doc = _json.loads(did_doc)
    pub_jwk = resolved.get("public_key_jwk")
    if isinstance(pub_jwk, str):
        pub_jwk = _json.loads(pub_jwk)

    if not pub_jwk:
        # Fall back to extracting from DID document
        vms = (did_doc or {}).get("verificationMethod", [])
        pub_jwk = vms[0].get("publicKeyJwk") if vms else None

    if not pub_jwk:
        return False

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        pub_key = public_key_from_jwk(pub_jwk)
        sig_bytes = base64.urlsafe_b64decode(signature_b64 + "==")
        pub_key.verify(sig_bytes, nonce.encode())
        return True
    except Exception:
        return False


# ── Token issuance ────────────────────────────────────────────────────────────
async def _get_caller_role_and_children(
    identity_id: _uuid.UUID, conn
) -> tuple[str, list[_uuid.UUID]]:
    """Look up role from DB role_assignments; fall back to identity type."""
    role_row = await conn.fetchrow(
        """
        SELECT role FROM foundation.role_assignments
        WHERE identity_id = $1
        LIMIT 1
        """,
        identity_id,
    )
    role: str = role_row["role"] if role_row else "observer"

    # Resolve identity type as fallback (child/guardian/teacher)
    if role == "observer":
        id_row = await conn.fetchrow(
            "SELECT type FROM foundation.identities WHERE id = $1", identity_id
        )
        if id_row:
            role = id_row["type"]  # child | guardian | teacher

    # Resolve child_ids for guardian callers (needed for owns_child checks)
    children: list[_uuid.UUID] = []
    if role == "guardian":
        rows = await conn.fetch(
            "SELECT child_id FROM foundation.guardian_links WHERE guardian_id = $1",
            identity_id,
        )
        children = [r["child_id"] for r in rows]

    return role, children


async def issue_tokens(did: str) -> dict:
    """
    Issue access + refresh JWT pair for a verified DID.
    Scopes are minted from ROLE_SCOPES (LPA).
    JTI is persisted in auth_tokens for revocation support.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        did_row = await conn.fetchrow(
            "SELECT identity_id FROM foundation.did_documents WHERE did = $1", did
        )
        if not did_row:
            raise HTTPException(404, "DID not registered")
        identity_id: _uuid.UUID = did_row["identity_id"]
        role, children = await _get_caller_role_and_children(identity_id, conn)

    scopes = ROLE_SCOPES.get(role, ROLE_SCOPES["observer"])
    now = datetime.now(timezone.utc)
    access_jti = str(_uuid.uuid4())
    refresh_jti = str(_uuid.uuid4())

    server_did, priv_key = await get_server_did()

    access_payload = {
        "iss": server_did,
        "sub": did,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_ACCESS_TTL_MIN)).timestamp()),
        "jti": access_jti,
        "role": role,
        "scopes": scopes,
        "identity_id": str(identity_id),
        "children": [str(c) for c in children],
    }
    refresh_payload = {
        "iss": server_did,
        "sub": did,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=JWT_REFRESH_TTL_DAYS)).timestamp()),
        "jti": refresh_jti,
        "token_type": "refresh",
    }

    access_token = _jwt.encode(access_payload, priv_key, algorithm="EdDSA")
    refresh_token = _jwt.encode(refresh_payload, priv_key, algorithm="EdDSA")

    # Persist JTIs for revocation
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO foundation.auth_tokens
              (jti, subject_did, role, scopes, child_ids, issued_at, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (jti) DO NOTHING
            """,
            [
                (
                    _uuid.UUID(access_jti), did, role, scopes,
                    [str(c) for c in children],
                    now, now + timedelta(minutes=JWT_ACCESS_TTL_MIN),
                ),
                (
                    _uuid.UUID(refresh_jti), did, "refresh", [],
                    [],
                    now, now + timedelta(days=JWT_REFRESH_TTL_DAYS),
                ),
            ],
        )

    log.info("tokens_issued", did=did, role=role, scopes=scopes)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": JWT_ACCESS_TTL_MIN * 60,
        "role": role,
        "scopes": scopes,
    }


# ── Token verification ────────────────────────────────────────────────────────
async def decode_and_verify_token(token: str) -> dict:
    """
    Decode and verify a Parth JWT.
    Checks: signature, expiry, JTI not revoked.
    """
    server_did, server_priv = await get_server_did()
    pub_key = server_priv.public_key()

    try:
        payload = _jwt.decode(
            token,
            pub_key,
            algorithms=["EdDSA"],
            options={"verify_aud": False},
        )
    except _jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except _jwt.InvalidTokenError as exc:
        raise HTTPException(401, f"Invalid token: {exc}")

    # Check revocation
    jti = payload.get("jti")
    if jti:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT revoked_at FROM foundation.auth_tokens WHERE jti = $1",
                _uuid.UUID(jti),
            )
            if not row:
                raise HTTPException(401, "Token not found (may have been pruned)")
            if row["revoked_at"] is not None:
                raise HTTPException(401, "Token has been revoked")

    return payload


async def revoke_token(jti: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE foundation.auth_tokens SET revoked_at = now() WHERE jti = $1",
            _uuid.UUID(jti),
        )


# ── FastAPI dependencies ──────────────────────────────────────────────────────
async def get_caller(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CallerContext:
    """
    Mandatory auth dependency.
    When REQUIRE_AUTH=false and no token is supplied, returns synthetic observer.
    """
    if not credentials:
        if not REQUIRE_AUTH:
            return _SYNTHETIC_OBSERVER
        raise HTTPException(401, "Authorization header required")

    payload = await decode_and_verify_token(credentials.credentials)
    if payload.get("token_type") == "refresh":
        raise HTTPException(401, "Refresh token cannot be used as access token")

    return CallerContext(
        did=payload["sub"],
        identity_id=_uuid.UUID(payload["identity_id"]) if payload.get("identity_id") else None,
        role=payload.get("role", "observer"),
        scopes=payload.get("scopes", []),
        children=[_uuid.UUID(c) for c in payload.get("children", [])],
        jti=payload.get("jti"),
    )


async def get_caller_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CallerContext:
    """
    Optional auth dependency — always returns a CallerContext.
    Used by endpoints that adapt their response based on auth level.
    """
    try:
        return await get_caller(request, credentials)
    except HTTPException:
        return _SYNTHETIC_OBSERVER
