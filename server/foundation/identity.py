import uuid as _uuid

from foundation.db import get_pool
from foundation.observability import get_logger

log = get_logger("foundation.identity")

# Scopes required for different operations
SCOPE_AI_INTERACTION = "ai_interaction"
SCOPE_LEARNER_DATA = "learner_data"
SCOPE_PROGRESS_REPORT = "progress_report"


async def check_consent(learner_id: str, scope: str) -> bool:
    """
    Returns True if the learner either:
    - is not a child (no guardian link required), OR
    - has an active guardian consent record covering the requested scope.

    Unknown learners and child learners without guardian consent are blocked.
    """
    try:
        child_uuid = _uuid.UUID(learner_id)
    except (AttributeError, TypeError, ValueError):
        return False

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT type FROM foundation.identities WHERE id = $1",
            child_uuid,
        )
        if row is None:
            # Unknown learner — deny access until they complete registration.
            # (The old code auto-inserted an orphan row each time, which was
            # both a security hole and a DB leak — every request created a new
            # random-UUID row that was never found on subsequent calls.)
            log.warning(
                "unregistered_learner_blocked",
                learner_id=learner_id,
                scope=scope,
            )
            return False

        if row["type"] != "child":
            return True

        link = await conn.fetchrow(
            """
            SELECT consent_given, scope
            FROM foundation.guardian_links
            WHERE child_id = $1 AND consent_given = true
            """,
            child_uuid,
        )
        if link is None:
            log.warning("consent_missing", learner_id=learner_id, scope=scope)
            return False

        return scope in (link["scope"] or [])


async def is_child_without_consent(learner_id: str) -> bool:
    """
    Returns True if the learner has a 'child' identity row but NO
    guardian_links row with consent_given=true.
    Returns False for non-child identities, anonymous learners, or
    children who already have consent.
    """
    try:
        child_uuid = _uuid.UUID(learner_id)
    except (AttributeError, TypeError, ValueError):
        return False

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT type FROM foundation.identities WHERE id = $1",
            child_uuid,
        )
        if row is None or row["type"] != "child":
            return False

        link = await conn.fetchrow(
            """
            SELECT 1 FROM foundation.guardian_links
            WHERE child_id = $1 AND consent_given = true
            """,
            child_uuid,
        )
        return link is None


async def register_pilot_learner(
    learner_id: str, name: str, grade: int, school_id: str | None = None
) -> bool:
    """
    Create or update a learner's child identity + profile row. Idempotent —
    safe to call again if the learner already exists.

    Does NOT grant consent. Call grant_pilot_consent() separately, as its own
    deliberate action, before any puzzle probe or chat data is collected for
    this learner — consent must never be a silent side effect of registering
    a profile. Returns True on success, False if learner_id is not a valid UUID.
    """
    try:
        child_uuid = _uuid.UUID(learner_id)
    except (AttributeError, TypeError, ValueError):
        return False
    child_name = (name or "Student")[:100]

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Child identity
            await conn.execute(
                """INSERT INTO foundation.identities (id, type, name, grade, school_id)
                   VALUES ($1, 'child', $2, $3, $4)
                   ON CONFLICT (id) DO UPDATE
                       SET name=$2, grade=$3,
                           school_id=COALESCE($4, foundation.identities.school_id)""",
                child_uuid, child_name, grade, school_id,
            )
            # Ensure a profile row exists in learner_state
            await conn.execute(
                """INSERT INTO learner_state.profiles (learner_id, name, grade)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (learner_id) DO UPDATE SET name=$2, grade=$3""",
                str(child_uuid), child_name, grade,
            )

    # Create DID for the child if not already present (non-fatal — IAM may not
    # be initialised yet when this is called during server startup seeding)
    try:
        from foundation.did import create_did_for_identity
        await create_did_for_identity(child_uuid, save_private=True)
    except Exception as _did_exc:
        log.warning("did_creation_skipped", learner_id=str(child_uuid), reason=str(_did_exc))

    log.info("pilot_learner_registered", learner_id=str(child_uuid), name=child_name, grade=grade)
    return True


async def grant_pilot_consent(learner_id: str) -> bool:
    """
    Explicit pilot consent grant (synthetic guardian, no OTP/DigiLocker yet —
    see modules/iam/routes.py's /consent/request + /consent/verify for the
    real OTP-verified guardian flow this should graduate to before a
    non-pilot launch).

    Must be called as its own deliberate action, triggered by a real UI
    consent step, BEFORE any puzzle probe or chat data is collected for this
    learner — never automatically as a side effect of registration or of
    cold-start completing. Idempotent.

    Returns False if learner_id is not a valid UUID, or if the child identity
    doesn't exist yet (call register_pilot_learner first).
    """
    try:
        child_uuid = _uuid.UUID(learner_id)
    except (AttributeError, TypeError, ValueError):
        return False

    # Deterministic guardian UUID derived from the child's UUID.
    # Each child gets their own synthetic guardian record.
    guardian_uuid = _uuid.uuid5(_uuid.NAMESPACE_DNS, f"pilot-guardian:{child_uuid}")

    pool = await get_pool()
    async with pool.acquire() as conn:
        child_row = await conn.fetchrow(
            "SELECT 1 FROM foundation.identities WHERE id = $1 AND type = 'child'",
            child_uuid,
        )
        if child_row is None:
            log.warning("consent_grant_missing_identity", learner_id=str(child_uuid))
            return False

        async with conn.transaction():
            # Synthetic pilot guardian
            await conn.execute(
                """INSERT INTO foundation.identities (id, type, name)
                   VALUES ($1, 'guardian', 'Pilot Guardian')
                   ON CONFLICT (id) DO NOTHING""",
                guardian_uuid,
            )
            # Consent grant
            await conn.execute(
                """INSERT INTO foundation.guardian_links
                       (guardian_id, child_id, consent_given, consent_ts, scope)
                   VALUES ($1, $2, true, now(), $3)
                   ON CONFLICT (guardian_id, child_id) DO UPDATE
                       SET consent_given=true, consent_ts=now(), scope=$3""",
                guardian_uuid, child_uuid,
                ["ai_interaction", "learner_data", "progress_report"],
            )

    log.info("pilot_consent_granted", learner_id=str(child_uuid))
    return True


async def erase(learner_id: str, conn=None):
    """
    Right-to-erasure: removes all PII for this learner.
    Each module must also register an on_erase hook with the kernel.
    This function handles the foundation tables only.
    """
    pool = await get_pool()
    _conn = conn or await pool.acquire()
    try:
        await _conn.execute(
            "DELETE FROM foundation.identities WHERE id::text = $1",
            learner_id,
        )
        log.info("identity_erased", learner_id=learner_id)
    finally:
        if conn is None:
            await pool.release(_conn)
