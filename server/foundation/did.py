"""
foundation.did — Decentralized Identifier management (did:key + Ed25519).

Key custody model: server-held by default (Fernet-encrypted), abstracted
so private keys can be migrated to client wallets later by setting
encrypted_private_key=NULL in did_documents and supplying the key out-of-band.
"""

import base64
import hashlib
import json
import os
import uuid as _uuid
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from foundation.db import get_pool
from foundation.observability import get_logger

log = get_logger("foundation.did")

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_ED25519_MULTICODEC = bytes([0xED, 0x01])


# ── Base58btc ─────────────────────────────────────────────────────────────────

def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    result = []
    while n > 0:
        n, rem = divmod(n, 58)
        result.append(_BASE58_ALPHABET[rem])
    # Leading zero bytes → leading '1's
    for byte in data:
        if byte == 0:
            result.append(_BASE58_ALPHABET[0])
        else:
            break
    return "".join(reversed(result))


def _b58decode(s: str) -> bytes:
    n = 0
    for char in s:
        n = n * 58 + _BASE58_ALPHABET.index(char)
    result = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = bytes([0] * sum(1 for c in s if c == _BASE58_ALPHABET[0]))
    return pad + result


# ── Base64url helpers ─────────────────────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


# ── Key generation ────────────────────────────────────────────────────────────

def generate_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    private_key = Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


# ── DID derivation ────────────────────────────────────────────────────────────

def public_key_to_did(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes_raw()          # 32 bytes
    prefixed = _ED25519_MULTICODEC + raw          # 34 bytes
    encoded = _b58encode(prefixed)
    return f"did:key:z{encoded}"


# ── JWK serialisation ─────────────────────────────────────────────────────────

def private_key_to_jwk(private_key: Ed25519PrivateKey, kid: str) -> dict:
    pub = private_key.public_key()
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "kid": kid,
        "x": _b64url_encode(pub.public_bytes_raw()),
        "d": _b64url_encode(private_key.private_bytes_raw()),
    }


def public_key_to_jwk(public_key: Ed25519PublicKey, kid: str) -> dict:
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "kid": kid,
        "x": _b64url_encode(public_key.public_bytes_raw()),
    }


def private_key_from_jwk(jwk: dict) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_b64url_decode(jwk["d"]))


def public_key_from_jwk(jwk: dict) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(_b64url_decode(jwk["x"]))


# ── DID Document ──────────────────────────────────────────────────────────────

def build_did_document(did: str, public_key_jwk: dict) -> dict:
    # Verification method id is the key fragment: everything after "did:key:"
    vm_id = f"{did}#{did[8:]}"
    return {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/ed25519-2020/v1",
        ],
        "id": did,
        "verificationMethod": [{
            "id": vm_id,
            "type": "Ed25519VerificationKey2020",
            "controller": did,
            "publicKeyJwk": public_key_jwk,
        }],
        "authentication": [vm_id],
        "assertionMethod": [vm_id],
        "capabilityInvocation": [vm_id],
        "capabilityDelegation": [vm_id],
    }


# ── Encryption of private keys (server-custodied) ─────────────────────────────

def _get_encryption_key() -> bytes:
    """
    Returns a 32-byte Fernet-compatible key.
    Prefers PARTH_ENCRYPTION_KEY (base64url-encoded 32 bytes).
    Falls back to deriving from PARTH_API_KEY via SHA-256.
    """
    enc_key = os.getenv("PARTH_ENCRYPTION_KEY", "")
    if enc_key:
        raw = _b64url_decode(enc_key)
        return base64.urlsafe_b64encode(raw[:32].ljust(32, b"\x00"))
    api_key = os.getenv("PARTH_API_KEY", "parth-dev-insecure-key")
    log.warning(
        "encryption_key_derived_from_api_key",
        hint="Set PARTH_ENCRYPTION_KEY in .env for production",
    )
    digest = hashlib.sha256(api_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _encrypt_private_key(private_bytes: bytes) -> str:
    fernet = Fernet(_get_encryption_key())
    return fernet.encrypt(private_bytes).decode()


def _decrypt_private_key(encrypted: str) -> bytes:
    fernet = Fernet(_get_encryption_key())
    return fernet.decrypt(encrypted.encode())


# ── Async DB operations ───────────────────────────────────────────────────────

async def create_did_for_identity(
    identity_id: _uuid.UUID,
    save_private: bool = True,
) -> tuple[str, dict]:
    """
    Generates a new Ed25519 keypair, derives did:key, stores in did_documents.
    Returns (did, public_key_jwk).
    """
    private_key, public_key = generate_keypair()
    did = public_key_to_did(public_key)
    kid = did[8:]  # key fragment (multibase without "did:key:")
    pub_jwk = public_key_to_jwk(public_key, kid)
    did_doc = build_did_document(did, pub_jwk)

    encrypted_priv: Optional[str] = None
    if save_private:
        encrypted_priv = _encrypt_private_key(private_key.private_bytes_raw())

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO foundation.did_documents
                (did, identity_id, did_document, public_key_jwk, encrypted_private_key)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (did) DO NOTHING
            """,
            did,
            identity_id,
            json.dumps(did_doc),
            json.dumps(pub_jwk),
            encrypted_priv,
        )

    log.info("did_created", did=did, identity_id=str(identity_id))
    return did, pub_jwk


async def get_server_did() -> tuple[str, Ed25519PrivateKey]:
    """
    Returns the server's issuer DID and its Ed25519PrivateKey.
    Reads PARTH_SERVER_DID_KEY (base64url-encoded 32-byte seed) from env.
    Falls back to deriving a deterministic key from PARTH_API_KEY (dev only).
    """
    seed_b64 = os.getenv("PARTH_SERVER_DID_KEY", "")
    if seed_b64:
        seed_bytes = _b64url_decode(seed_b64)[:32]
    else:
        api_key = os.getenv("PARTH_API_KEY", "parth-server-did-fallback")
        seed_bytes = hashlib.sha256(f"server-did:{api_key}".encode()).digest()
        log.warning(
            "server_did_derived_from_api_key",
            hint="Set PARTH_SERVER_DID_KEY in .env for production",
        )

    private_key = Ed25519PrivateKey.from_private_bytes(seed_bytes)
    did = public_key_to_did(private_key.public_key())
    return did, private_key


async def resolve_did(did: str) -> Optional[dict]:
    """Look up a DID document from did_documents."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT did_document, public_key_jwk FROM foundation.did_documents WHERE did = $1",
            did,
        )
    if row is None:
        return None
    return {
        "did_document": row["did_document"],
        "public_key_jwk": row["public_key_jwk"],
    }


async def get_private_key_for_did(did: str) -> Optional[Ed25519PrivateKey]:
    """Decrypt and return the stored private key for a DID. Returns None for client-held keys."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT encrypted_private_key FROM foundation.did_documents WHERE did = $1",
            did,
        )
    if row is None or row["encrypted_private_key"] is None:
        return None
    raw = _decrypt_private_key(row["encrypted_private_key"])
    return Ed25519PrivateKey.from_private_bytes(raw)


async def get_did_for_identity(identity_id: _uuid.UUID) -> Optional[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT did FROM foundation.did_documents WHERE identity_id = $1",
            identity_id,
        )
    return row["did"] if row else None
