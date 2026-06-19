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

    For anonymous learners (no identity row): logs a warning, inserts a
    placeholder identity row so the learner is now tracked, and returns True.
    For child learners without guardian consent: blocks (returns False).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT type FROM foundation.identities WHERE id::text = $1",
            learner_id,
        )
        if row is None:
            # Anonymous learner — track them via a placeholder row and allow
            log.warning(
                "anonymous_learner_tracked",
                learner_id=learner_id,
                scope=scope,
                msg="No identity row found; inserting placeholder so learner is tracked.",
            )
            try:
                await conn.execute(
                    """
                    INSERT INTO foundation.identities (type, name)
                    VALUES ('teacher', $1)
                    ON CONFLICT DO NOTHING
                    """,
                    f"anon:{learner_id}",
                )
            except Exception as exc:
                log.warning("placeholder_identity_insert_failed", error=str(exc))
            return True

        if row["type"] != "child":
            return True

        link = await conn.fetchrow(
            """
            SELECT consent_given, scope
            FROM foundation.guardian_links
            WHERE child_id::text = $1 AND consent_given = true
            """,
            learner_id,
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
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT type FROM foundation.identities WHERE id::text = $1",
            learner_id,
        )
        if row is None or row["type"] != "child":
            return False

        link = await conn.fetchrow(
            """
            SELECT 1 FROM foundation.guardian_links
            WHERE child_id::text = $1 AND consent_given = true
            """,
            learner_id,
        )
        return link is None


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
