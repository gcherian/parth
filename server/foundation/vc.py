"""
foundation.vc — W3C Verifiable Credentials with EdDSA JWS detached proof.

Proof type: Ed25519Signature2020
JWS: compact serialisation with detached payload (b64:false)
"""

import base64
import json
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

from foundation.db import get_pool
from foundation.observability import get_logger

log = get_logger("foundation.vc")

_VC_CONTEXT = [
    "https://www.w3.org/2018/credentials/v1",
    "https://w3id.org/security/suites/ed25519-2020/v1",
    "https://parth.ai/credentials/v1",
]


# ── Base64url helpers ─────────────────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


# ── JWS (detached, b64:false) ─────────────────────────────────────────────────

def _jws_sign(payload_bytes: bytes, private_key: Ed25519PrivateKey) -> str:
    """
    Returns a compact detached JWS: "header_b64..sig_b64"
    The payload is NOT embedded (detached); caller must keep it separately.
    """
    header = json.dumps({"alg": "EdDSA", "b64": False, "crit": ["b64"]},
                        separators=(",", ":")).encode()
    header_b64 = _b64url(header)
    # Signing input: ASCII(base64url(header)) || "." || payload_bytes
    signing_input = header_b64.encode() + b"." + payload_bytes
    signature = private_key.sign(signing_input)
    return f"{header_b64}..{_b64url(signature)}"


def _jws_verify(jws: str, payload_bytes: bytes, public_key: Ed25519PublicKey) -> bool:
    parts = jws.split(".")
    if len(parts) != 3:
        return False
    header_b64, _, sig_b64 = parts
    try:
        signing_input = header_b64.encode() + b"." + payload_bytes
        public_key.verify(_b64url_decode(sig_b64), signing_input)
        return True
    except (InvalidSignature, Exception):
        return False


# ── VC issuance ───────────────────────────────────────────────────────────────

async def issue_vc(
    issuer_did: str,
    issuer_private_key: Ed25519PrivateKey,
    subject_did: str,
    vc_types: list[str],
    credential_subject: dict,
    validity_days: int = 365,
) -> dict:
    """
    Issues a signed W3C Verifiable Credential.
    Stores it in foundation.credentials and returns the full VC dict
    with an additional '_db_id' field (UUID of the stored row).
    """
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=validity_days)
    vc_id = f"urn:parth:vc:{_uuid.uuid4()}"

    full_types = list(dict.fromkeys(["VerifiableCredential"] + vc_types))

    vc = {
        "@context": _VC_CONTEXT,
        "id": vc_id,
        "type": full_types,
        "issuer": issuer_did,
        "issuanceDate": now.isoformat(),
        "expirationDate": expiry.isoformat(),
        "credentialSubject": {
            "id": subject_did,
            **credential_subject,
        },
    }

    # Sign canonical form (no proof field)
    canonical = json.dumps(vc, sort_keys=True, separators=(",", ":")).encode()
    jws = _jws_sign(canonical, issuer_private_key)

    # Verification method = issuer DID fragment
    vm_id = f"{issuer_did}#{issuer_did[8:]}"
    vc["proof"] = {
        "type": "Ed25519Signature2020",
        "created": now.isoformat(),
        "verificationMethod": vm_id,
        "proofPurpose": "assertionMethod",
        "jws": jws,
    }

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO foundation.credentials
                (vc_type, issuer_did, subject_did, credential_json, proof_jws, issued_at, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            full_types,
            issuer_did,
            subject_did,
            json.dumps(vc),
            jws,
            now,
            expiry,
        )
    db_id = str(row["id"])
    vc["_db_id"] = db_id
    log.info("vc_issued", db_id=db_id, types=full_types, subject=subject_did)
    return vc


# ── VC verification ───────────────────────────────────────────────────────────

async def verify_vc(vc_json: dict) -> tuple[bool, str]:
    """
    Verifies a VC's signature and checks it hasn't been revoked or expired.
    Returns (valid, reason).
    """
    # Import here to avoid circular at module level
    from foundation import did as did_module

    # Check expiry
    exp_str = vc_json.get("expirationDate")
    if exp_str:
        try:
            exp = datetime.fromisoformat(exp_str)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                return False, "credential_expired"
        except ValueError:
            return False, "invalid_expiration_date"

    proof = vc_json.get("proof", {})
    jws = proof.get("jws")
    if not jws:
        return False, "missing_proof_jws"

    # Check DB revocation (by VC id)
    vc_id = vc_json.get("id", "")
    db_id = vc_json.get("_db_id")
    pool = await get_pool()
    async with pool.acquire() as conn:
        if db_id:
            row = await conn.fetchrow(
                "SELECT revoked_at FROM foundation.credentials WHERE id = $1::uuid",
                db_id,
            )
        else:
            row = await conn.fetchrow(
                "SELECT revoked_at FROM foundation.credentials WHERE credential_json->>'id' = $1",
                vc_id,
            )
    if row and row["revoked_at"] is not None:
        return False, "credential_revoked"

    # Resolve issuer public key
    issuer_did = vc_json.get("issuer", "")
    resolved = await did_module.resolve_did(issuer_did)
    if resolved is None:
        # Try server DID
        server_did, server_key = await did_module.get_server_did()
        if issuer_did == server_did:
            public_key = server_key.public_key()
        else:
            return False, "unknown_issuer_did"
    else:
        pub_jwk = resolved["public_key_jwk"]
        if isinstance(pub_jwk, str):
            pub_jwk = json.loads(pub_jwk)
        public_key = did_module.public_key_from_jwk(pub_jwk)

    # Reconstruct canonical payload (VC without proof field)
    vc_without_proof = {k: v for k, v in vc_json.items() if k not in ("proof", "_db_id")}
    canonical = json.dumps(vc_without_proof, sort_keys=True, separators=(",", ":")).encode()

    if not _jws_verify(jws, canonical, public_key):
        return False, "invalid_signature"

    return True, "ok"


# ── VC revocation ─────────────────────────────────────────────────────────────

async def revoke_vc(credential_db_id: str, reason: str = "") -> bool:
    """Marks a credential as revoked. Returns True if a row was updated."""
    from datetime import datetime, timezone
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE foundation.credentials
            SET revoked_at = now(), revocation_reason = $2
            WHERE id = $1::uuid AND revoked_at IS NULL
            """,
            credential_db_id,
            reason,
        )
    updated = result != "UPDATE 0"
    if updated:
        log.info("vc_revoked", credential_id=credential_db_id, reason=reason)
    return updated
