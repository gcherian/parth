"""
RBAC + ABAC policy engine.

Layer 1 — RBAC: is this role allowed to touch this resource/action?
  Loaded from foundation.permissions into an in-memory cache at startup.
  Cache key: _rbac_cache[role][resource][action] → abac_policy dict

Layer 2 — ABAC: does this specific request satisfy contextual conditions?
  Conditions evaluated from abac_policy:
    owner_only: bool         — caller's DID must match the resource owner's DID
    guardian_of: bool        — caller must be in guardian_links for this child
    require_scope: str       — token must carry this scope
    require_delegation: bool — teacher must have valid delegated_access row
    delegation_scope: str    — specific scope required in the delegation
    sensitivity: str         — "HIGH" triggers extra audit detail
    sod_required: bool       — marks SoD-gated operations (flagged in audit;
                               full two-party approval implemented in Phase 2)

LPA: enforced at token issuance (each role gets minimum scopes only).
     The require_scope ABAC condition provides a second runtime check.

SoD: sod_required=true operations are allowed for admin callers but flagged
     prominently in the audit log. Full SoD approval token flow is Phase 2.
"""
import json
import uuid as _uuid
from typing import Optional

from fastapi import HTTPException, Request

from foundation.db import get_pool
from foundation.audit import log_access
from foundation.observability import get_logger

log = get_logger("foundation.policy")

_rbac_cache: dict[str, dict[str, dict[str, dict]]] = {}


async def load_rbac_cache() -> None:
    """Load RBAC permission matrix from DB into in-memory cache. Call at startup."""
    global _rbac_cache
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, resource, action, abac_policy FROM foundation.permissions"
        )
    cache: dict = {}
    for row in rows:
        policy: dict = {}
        if row["abac_policy"]:
            try:
                raw = row["abac_policy"]
                policy = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except Exception:
                policy = {}
        cache.setdefault(row["role"], {}).setdefault(row["resource"], {})[row["action"]] = policy
    _rbac_cache = cache
    total = sum(len(acts) for role in cache.values() for acts in role.values())
    log.info("rbac_cache_loaded", roles=list(cache.keys()), total_permissions=total)


def _rbac_check(role: str, resource: str, action: str) -> Optional[dict]:
    """Return ABAC policy dict if RBAC allows, None if role lacks permission."""
    return _rbac_cache.get(role, {}).get(resource, {}).get(action)


async def _abac_check(
    policy: dict,
    caller_did: str,
    caller_role: str,
    resource_owner_id: Optional[str],
    token_scopes: list[str],
    conn,
) -> tuple[bool, str]:
    """Evaluate all ABAC conditions. Returns (allowed, denial_reason)."""

    # owner_only: caller's DID must belong to the resource owner identity
    if policy.get("owner_only") and resource_owner_id:
        did_row = await conn.fetchrow(
            "SELECT did FROM foundation.did_documents WHERE identity_id::text = $1",
            resource_owner_id,
        )
        if not did_row or did_row["did"] != caller_did:
            return False, "owner_only_violation"

    # guardian_of: caller must have an active guardian_link with consent for this child
    if policy.get("guardian_of"):
        if not resource_owner_id:
            return False, "no_resource_owner"
        caller_identity = await conn.fetchrow(
            "SELECT identity_id FROM foundation.did_documents WHERE did = $1",
            caller_did,
        )
        if not caller_identity:
            return False, "caller_identity_not_found"
        link = await conn.fetchrow(
            """
            SELECT 1 FROM foundation.guardian_links
            WHERE guardian_id = $1
              AND child_id::text = $2
              AND consent_given = true
            """,
            caller_identity["identity_id"], resource_owner_id,
        )
        if not link:
            return False, "not_guardian_of_child"

    # require_scope: token must explicitly carry this scope (LPA second-check)
    required_scope = policy.get("require_scope")
    if required_scope and required_scope not in token_scopes:
        return False, f"missing_scope:{required_scope}"

    # require_delegation: teacher must have a valid unexpired delegated_access row
    if policy.get("require_delegation"):
        delegation_scope = policy.get("delegation_scope", "")
        if not resource_owner_id:
            return False, "no_resource_owner_for_delegation"
        delegation = await conn.fetchrow(
            """
            SELECT 1 FROM foundation.delegated_access
            WHERE delegate_did = $1
              AND child_id::text = $2
              AND $3 = ANY(scopes)
              AND revoked_at IS NULL
              AND (valid_until IS NULL OR valid_until > now())
            """,
            caller_did, resource_owner_id, delegation_scope,
        )
        if not delegation:
            return False, "no_valid_delegation"

    # sod_required: allowed for admin but flagged; full SoD approval token is Phase 2
    if policy.get("sod_required") and caller_role != "admin":
        return False, "sod_required_admin_only"

    return True, "ok"


async def enforce(
    *,
    request: Request,
    caller_did: str,
    caller_role: str,
    resource: str,
    action: str,
    resource_owner_id: Optional[str] = None,
    token_scopes: Optional[list[str]] = None,
    request_id: Optional[_uuid.UUID] = None,
) -> None:
    """
    Main policy enforcement point. Call from every protected endpoint.
    Raises HTTPException(403) on denial.
    Every decision (allow and deny) is written to the audit log.
    """
    caller_ip = (
        request.headers.get("x-forwarded-for")
        or (request.client.host if request.client else None)
    )
    endpoint = str(request.url.path)
    http_method = request.method

    # ── Layer 1: RBAC ────────────────────────────────────────────────────────
    abac_policy = _rbac_check(caller_role, resource, action)
    if abac_policy is None:
        await log_access(
            caller_did=caller_did, caller_role=caller_role,
            action=f"{resource}:{action}", resource_type=resource,
            resource_id=resource_owner_id, endpoint=endpoint,
            http_method=http_method, success=False,
            denial_reason="rbac_denied", request_id=request_id,
            caller_ip=caller_ip,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "access_denied",
                "reason": "rbac_denied",
                "role": caller_role,
                "resource": resource,
                "action": action,
            },
        )

    # ── Layer 2: ABAC ────────────────────────────────────────────────────────
    pool = await get_pool()
    async with pool.acquire() as conn:
        abac_ok, abac_reason = await _abac_check(
            abac_policy, caller_did, caller_role,
            resource_owner_id, token_scopes or [], conn,
        )

    if not abac_ok:
        await log_access(
            caller_did=caller_did, caller_role=caller_role,
            action=f"{resource}:{action}", resource_type=resource,
            resource_id=resource_owner_id, endpoint=endpoint,
            http_method=http_method, success=False,
            denial_reason=abac_reason, request_id=request_id,
            caller_ip=caller_ip,
        )
        raise HTTPException(
            status_code=403,
            detail={"error": "access_denied", "reason": abac_reason},
        )

    # ── Access granted — log it ───────────────────────────────────────────────
    # Log sod_required grants with elevated visibility
    sod_flag = "sod_admin_approved" if abac_policy.get("sod_required") else None
    await log_access(
        caller_did=caller_did, caller_role=caller_role,
        action=f"{resource}:{action}", resource_type=resource,
        resource_id=resource_owner_id, endpoint=endpoint,
        http_method=http_method, success=True,
        denial_reason=sod_flag,  # reused field to flag SoD ops
        request_id=request_id, caller_ip=caller_ip,
    )
