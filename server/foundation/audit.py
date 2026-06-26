"""
foundation.audit — Append-only audit log with SHA-256 hash chain.

Every data access (read or write) is logged here for DPDP Art. 4 compliance.
The hash chain makes tampering detectable: each row hashes the previous row's hash.
UPDATE and DELETE are blocked at the Postgres level (see iam_schema.sql).

This module never raises — all errors are swallowed and logged via structlog.
"""

import hashlib
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from foundation.db import get_pool
from foundation.observability import get_logger

log = get_logger("foundation.audit")

_GENESIS_HASH = hashlib.sha256(b"parth-audit-genesis").hexdigest()


# ── Hash chain ────────────────────────────────────────────────────────────────

def _compute_row_hash(
    prev_hash: str,
    event_time: str,
    caller_did: Optional[str],
    action: str,
    resource_id: Optional[str],
) -> str:
    payload = "|".join([
        prev_hash,
        event_time,
        caller_did or "",
        action,
        resource_id or "",
    ])
    return hashlib.sha256(payload.encode()).hexdigest()


# ── Public API ────────────────────────────────────────────────────────────────

async def log_access(
    *,
    caller_did: Optional[str],
    caller_role: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    http_method: Optional[str] = None,
    success: bool,
    denial_reason: Optional[str] = None,
    request_id: Optional[_uuid.UUID] = None,
    caller_ip: Optional[str] = None,
) -> None:
    """
    Appends one row to foundation.audit_log. Never raises.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Get the previous row's hash for the chain
            prev_row = await conn.fetchrow(
                "SELECT row_hash FROM foundation.audit_log ORDER BY id DESC LIMIT 1"
            )
            prev_hash = prev_row["row_hash"] if prev_row and prev_row["row_hash"] else _GENESIS_HASH

            now = datetime.now(timezone.utc)
            event_time_str = now.isoformat()
            row_hash = _compute_row_hash(prev_hash, event_time_str, caller_did, action, resource_id)

            await conn.execute(
                """
                INSERT INTO foundation.audit_log (
                    event_time, caller_did, caller_role, action, resource_type,
                    resource_id, endpoint, http_method, success, denial_reason,
                    request_id, caller_ip, row_hash, prev_hash
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9, $10,
                    $11, $12::inet, $13, $14
                )
                """,
                now,
                caller_did,
                caller_role,
                action,
                resource_type,
                resource_id,
                endpoint,
                http_method,
                success,
                denial_reason,
                request_id,
                caller_ip,
                row_hash,
                prev_hash,
            )
    except Exception as exc:
        # Audit must never break the main request path
        log.error("audit_log_write_failed", error=str(exc), action=action, resource_type=resource_type)
