import asyncpg
import json
import os
from pathlib import Path

_pool: asyncpg.Pool | None = None

_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://parth:parth_dev@localhost:5432/parth",
)


async def _init_connection(conn):
    """Register JSON/JSONB codecs so Python dicts round-trip transparently."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=_DSN,
            min_size=2,
            max_size=10,
            command_timeout=30,
            init=_init_connection,
        )
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def apply_schema():
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Foundation schema
        schema_path = Path(__file__).parent / "schema.sql"
        await conn.execute(schema_path.read_text())
        # Module schemas
        module_schemas = [
            Path(__file__).parents[1] / "modules" / "puzzle_engine" / "schema.sql",
        ]
        for p in module_schemas:
            if p.exists():
                await conn.execute(p.read_text())
