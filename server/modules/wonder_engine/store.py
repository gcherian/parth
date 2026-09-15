"""wonder.engine — Postgres access for offer cadence gating and history."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


async def too_soon_for_another_offer(conn, learner_id: str, min_minutes: int) -> bool:
    last = await conn.fetchval(
        "SELECT offered_at FROM wonder_engine.offers WHERE learner_id = $1 "
        "ORDER BY offered_at DESC LIMIT 1",
        learner_id,
    )
    if last is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=min_minutes)
    last = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
    return last > cutoff


async def recently_offered_puzzle_ids(conn, learner_id: str, limit: int = 20) -> set[str]:
    rows = await conn.fetch(
        "SELECT puzzle_id FROM wonder_engine.offers WHERE learner_id = $1 "
        "ORDER BY offered_at DESC LIMIT $2",
        learner_id, limit,
    )
    return {r["puzzle_id"] for r in rows}


async def record_offer(conn, learner_id: str, puzzle_id: str, sphere: str) -> None:
    await conn.execute(
        "INSERT INTO wonder_engine.offers (learner_id, puzzle_id, sphere) VALUES ($1, $2, $3)",
        learner_id, puzzle_id, sphere,
    )
