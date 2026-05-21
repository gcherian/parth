"""Bayesian knowledge tracing per concept."""
from foundation.observability import get_logger

log = get_logger("learner_state.knowledge")


def _mastery(exposures: int, demonstrations: int, misconceptions: int) -> float:
    exp = max(1, exposures)
    raw = (demonstrations / exp) * (1.0 - 0.4 * misconceptions / exp)
    return round(max(0.05, min(0.98, raw)), 3)


async def record_exposure(conn, learner_id: str, concepts: list[str]):
    for concept_id in concepts:
        await conn.execute(
            """
            INSERT INTO learner_state.knowledge (learner_id, concept_id, exposures)
            VALUES ($1, $2, 1)
            ON CONFLICT (learner_id, concept_id)
            DO UPDATE SET
                exposures = learner_state.knowledge.exposures + 1,
                p_mastery = $3,
                last_updated = now()
            """,
            learner_id, concept_id,
            _mastery(
                *await _counts(conn, learner_id, concept_id, increment_exposures=True)
            ),
        )


async def record_demonstration(conn, learner_id: str, concepts: list[str]):
    for concept_id in concepts:
        row = await _raw_counts(conn, learner_id, concept_id)
        if row:
            new_mastery = _mastery(
                row["exposures"], row["demonstrations"] + 1, row["misconceptions"]
            )
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
    """
    Record a misconception for each concept.

    If the misconception is from the same session as last_misconception_session,
    apply only 0.5× weight to the mastery penalty — frustration in one session
    shouldn't permanently tank mastery.

    If it's a new session, reset session_misconception_count to 1 and apply full weight.
    """
    for concept_id in concepts:
        row = await conn.fetchrow(
            """
            SELECT exposures, demonstrations, misconceptions,
                   last_misconception_session, session_misconception_count
            FROM learner_state.knowledge
            WHERE learner_id = $1 AND concept_id = $2
            """,
            learner_id, concept_id,
        )
        if row:
            same_session = (session_id and session_id == (row["last_misconception_session"] or ""))

            if same_session:
                # Same session — apply 0.5× weight (add 0.5 effective misconception)
                effective_misconceptions = row["misconceptions"] + 0.5
                new_session_count = (row["session_misconception_count"] or 0) + 1
            else:
                # New session — full weight
                effective_misconceptions = row["misconceptions"] + 1
                new_session_count = 1

            new_mastery = _mastery(
                row["exposures"], row["demonstrations"], effective_misconceptions
            )
            await conn.execute(
                """
                UPDATE learner_state.knowledge
                SET misconceptions = misconceptions + 1,
                    p_mastery = $3,
                    last_updated = now(),
                    last_misconception_session = $4,
                    session_misconception_count = $5
                WHERE learner_id = $1 AND concept_id = $2
                """,
                learner_id, concept_id, new_mastery,
                session_id or '', new_session_count,
            )


async def _raw_counts(conn, learner_id: str, concept_id: str):
    return await conn.fetchrow(
        """
        SELECT exposures, demonstrations, misconceptions
        FROM learner_state.knowledge
        WHERE learner_id = $1 AND concept_id = $2
        """,
        learner_id, concept_id,
    )


async def _counts(conn, learner_id: str, concept_id: str, increment_exposures=False):
    row = await _raw_counts(conn, learner_id, concept_id)
    if row is None:
        return (1, 0, 0)
    exp = row["exposures"] + (1 if increment_exposures else 0)
    return (exp, row["demonstrations"], row["misconceptions"])


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
