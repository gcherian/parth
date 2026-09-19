"""
Bayesian Knowledge Tracing per concept.

Update math lives in bkt.py; this module owns the per-concept parameter
lookup and the DB read/write glue, and keeps the exact three-function call
interface mastery_tracker.py already uses (record_exposure /
record_demonstration / record_misconception) so nothing downstream changes.

This replaces a ratio heuristic that used to live here and call itself BKT
without implementing it — see docs/model_of_the_child_2026_09_18.md §3.3 for
the audit that found the gap, and §5 item 2 for this fix. Semantics changes
from that heuristic:

  - record_exposure no longer touches p_mastery. In BKT terms, "exposure"
    without a correctness verdict isn't an observation — there's nothing to
    update on. It still bumps the `exposures` diagnostic counter other
    consumers (mastery_tracker._read, dimensions.py) display, and seeds a
    brand-new concept's row at that concept's fitted BKT prior (p_init)
    instead of a flat 0.05 regardless of concept.
  - record_demonstration / record_misconception ARE the BKT observations
    (correct / incorrect respectively) — each does exactly one Bayes update
    + learning-transition step via bkt.update().
  - The old same-session misconception half-weighting hack is gone: it
    existed to stop the ratio heuristic's linear penalty from permanently
    tanking mastery after one bad session. BKT's update is bounded and
    self-correcting (p_transit pulls it back up on the next success), so
    the hack no longer has anything to compensate for.
"""
from foundation.observability import get_logger
from modules.learner_state import bkt

log = get_logger("learner_state.knowledge")

# Below this many of a concept's own kt_events, prefer the pooled '_global_'
# fit over trying to fit that one concept in isolation — see get_params().
_MIN_EVENTS_FOR_PER_CONCEPT_FIT = 50


async def get_params(conn, concept_id: str) -> bkt.BKTParams:
    """Concept-specific fitted params once there's enough of that concept's
    own data (server/fit_bkt_params.py writes these rows); otherwise the
    pooled global fit; otherwise literature defaults if that script has
    never run on this deployment at all."""
    row = await conn.fetchrow(
        "SELECT p_init, p_transit, p_slip, p_guess, n_fit "
        "FROM learner_state.bkt_params WHERE concept_id = $1",
        concept_id,
    )
    if row and row["n_fit"] >= _MIN_EVENTS_FOR_PER_CONCEPT_FIT:
        return bkt.BKTParams(row["p_init"], row["p_transit"], row["p_slip"], row["p_guess"])

    global_row = await conn.fetchrow(
        "SELECT p_init, p_transit, p_slip, p_guess "
        "FROM learner_state.bkt_params WHERE concept_id = '_global_'",
    )
    if global_row:
        return bkt.BKTParams(
            global_row["p_init"], global_row["p_transit"],
            global_row["p_slip"], global_row["p_guess"],
        )
    return bkt.LITERATURE_DEFAULTS


async def _current_mastery(conn, learner_id: str, concept_id: str) -> float | None:
    return await conn.fetchval(
        "SELECT p_mastery FROM learner_state.knowledge WHERE learner_id=$1 AND concept_id=$2",
        learner_id, concept_id,
    )


async def record_exposure(conn, learner_id: str, concepts: list[str]):
    for concept_id in concepts:
        params = await get_params(conn, concept_id)
        await conn.execute(
            """
            INSERT INTO learner_state.knowledge (learner_id, concept_id, exposures, p_mastery)
            VALUES ($1, $2, 1, $3)
            ON CONFLICT (learner_id, concept_id)
            DO UPDATE SET
                exposures = learner_state.knowledge.exposures + 1,
                last_updated = now()
            """,
            learner_id, concept_id, bkt.initial(params),
        )


async def record_demonstration(conn, learner_id: str, concepts: list[str]):
    """BKT observation: correct."""
    for concept_id in concepts:
        params = await get_params(conn, concept_id)
        prior = await _current_mastery(conn, learner_id, concept_id)
        if prior is None:
            prior = bkt.initial(params)
        new_mastery = bkt.update(prior, True, params)
        await conn.execute(
            """
            UPDATE learner_state.knowledge
            SET demonstrations = demonstrations + 1,
                p_mastery = $3,
                last_updated = now()
            WHERE learner_id = $1 AND concept_id = $2
            """,
            learner_id, concept_id, new_mastery,
        )


async def record_misconception(conn, learner_id: str, concepts: list[str], session_id: str = ''):
    """BKT observation: incorrect."""
    for concept_id in concepts:
        params = await get_params(conn, concept_id)
        prior = await _current_mastery(conn, learner_id, concept_id)
        if prior is None:
            prior = bkt.initial(params)
        new_mastery = bkt.update(prior, False, params)
        await conn.execute(
            """
            UPDATE learner_state.knowledge
            SET misconceptions = misconceptions + 1,
                p_mastery = $3,
                last_updated = now(),
                last_misconception_session = $4
            WHERE learner_id = $1 AND concept_id = $2
            """,
            learner_id, concept_id, new_mastery, session_id or '',
        )


async def weak_concepts(conn, learner_id: str, threshold: float = 0.5, n: int = 3) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT concept_id FROM learner_state.knowledge
        WHERE learner_id = $1 AND p_mastery < $2
        ORDER BY p_mastery ASC
        LIMIT $3
        """,
        learner_id, threshold, n,
    )
    return [r["concept_id"] for r in rows]


async def strong_concepts(conn, learner_id: str, threshold: float = 0.75, n: int = 3) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT concept_id FROM learner_state.knowledge
        WHERE learner_id = $1 AND p_mastery >= $2
        ORDER BY p_mastery DESC
        LIMIT $3
        """,
        learner_id, threshold, n,
    )
    return [r["concept_id"] for r in rows]
