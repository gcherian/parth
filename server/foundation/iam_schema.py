"""Apply the IAM schema and seed data from iam_schema.sql."""
import os
from pathlib import Path

from foundation.db import get_pool
from foundation.observability import get_logger

log = get_logger("foundation.iam_schema")

_SQL_PATH = Path(__file__).parent / "iam_schema.sql"


async def apply_iam_schema() -> None:
    """
    Idempotent. Reads iam_schema.sql and executes it against the DB.
    All CREATE TABLE / INSERT statements in that file use IF NOT EXISTS
    and ON CONFLICT DO NOTHING so re-running is safe.
    """
    if not _SQL_PATH.exists():
        log.warning("iam_schema_sql_missing", path=str(_SQL_PATH))
        return

    sql = _SQL_PATH.read_text()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(sql)

    log.info("iam_schema_applied", path=str(_SQL_PATH))
