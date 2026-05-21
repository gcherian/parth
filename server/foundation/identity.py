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

    Currently permissive (returns True) when identity rows don't exist yet —
    the consent system is wired but UI enforcement comes in Sprint 4.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT type FROM foundation.identities WHERE id::text = $1",
            learner_id,
        )
        if row is None:
            # Anonymous / not yet registered — allow (Sprint 4 tightens this)
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
