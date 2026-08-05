import asyncio
import uuid
from datetime import datetime
from typing import Any

from foundation.db import get_pool
from foundation.observability import get_logger

log = get_logger("foundation.outbox")

# In-process subscribers: event_type -> list of async callables
_subscribers: dict[str, list] = {}


def subscribe(event_type: str, handler):
    _subscribers.setdefault(event_type, []).append(handler)


async def publish(
    conn,
    event_type: str,
    payload: dict,
    aggregate: str = "",
    aggregate_id: str = "",
    purpose: str | None = None,
) -> str:
    """Write an outbox row inside caller's open transaction.

    purpose is optional and unread by anything today — no call site is
    required to pass it. It exists so callers that already know why an
    event is being published (e.g. a future consent-scoped Action) have
    somewhere to record that now, instead of retrofitting it later.
    """
    row_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO foundation.outbox
            (id, event_type, aggregate, aggregate_id, payload, purpose)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        row_id, event_type, aggregate, aggregate_id, payload, purpose,
    )
    return row_id


async def _deliver_pending(pool):
    """Pick up pending outbox rows and deliver to in-process subscribers."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id, event_type, payload
                FROM foundation.outbox
                WHERE status = 'pending'
                ORDER BY created_at
                LIMIT 50
                FOR UPDATE SKIP LOCKED
                """
            )
            for row in rows:
                handlers = _subscribers.get(row["event_type"], [])
                ok = True
                for h in handlers:
                    try:
                        await h(row["event_type"], dict(row["payload"]))
                    except Exception as e:
                        log.warning("outbox_handler_error", event=row["event_type"], error=str(e))
                        ok = False
                status = "delivered" if ok else "failed"
                await conn.execute(
                    """
                    UPDATE foundation.outbox
                    SET status = $1, delivered_at = now()
                    WHERE id = $2
                    """,
                    status, row["id"],
                )


async def relay_loop(interval_ms: int = 200):
    """Background relay — runs forever until cancelled."""
    pool = await get_pool()
    log.info("outbox_relay_started", interval_ms=interval_ms)
    while True:
        try:
            await _deliver_pending(pool)
        except Exception as e:
            log.error("outbox_relay_error", error=str(e))
        await asyncio.sleep(interval_ms / 1000)


async def cleanup_idempotency(pool, max_age_hours: int = 24):
    """Remove idempotency records older than max_age_hours."""
    async with pool.acquire() as conn:
        deleted = await conn.fetchval(
            """
            DELETE FROM foundation.idempotency
            WHERE created_at < now() - ($1 || ' hours')::interval
            RETURNING count(*)
            """,
            str(max_age_hours),
        )
    if deleted:
        log.info("idempotency_cleanup", deleted=deleted)
