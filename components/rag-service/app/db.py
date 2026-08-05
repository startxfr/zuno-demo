"""asyncpg connection pool lifecycle."""

from __future__ import annotations

import json
import logging
from typing import Optional

import asyncpg

from app import config

logger = logging.getLogger("rag_service.db")

_pool: Optional[asyncpg.Pool] = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    # asyncpg does not decode jsonb to a Python dict/list by default - it
    # comes back as a raw JSON string unless a codec is registered, which
    # app/search.py's _row_to_doc (dict(row["metadata"])) and every
    # metadata->>'...' consumer assume has already happened. Found by
    # actually running hybrid_search against a real PostgreSQL instance in
    # this phase's development environment (ADR-0046) - every previous
    # phase's own docs note this service had never been exercised against
    # a live database before.
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def connect() -> None:
    global _pool
    if _pool is not None:
        return
    try:
        _pool = await asyncpg.create_pool(
            host=config.PGHOST,
            port=config.PGPORT,
            database=config.PGDATABASE,
            user=config.PGUSER,
            password=config.PGPASSWORD,
            min_size=config.PG_POOL_MIN_SIZE,
            max_size=config.PG_POOL_MAX_SIZE,
            init=_init_connection,
        )
        logger.info("connected to PostgreSQL at %s:%s/%s", config.PGHOST, config.PGPORT, config.PGDATABASE)
    except Exception as exc:
        logger.error("failed to connect to PostgreSQL: %s", exc)
        _pool = None
        raise


async def disconnect() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> Optional[asyncpg.Pool]:
    return _pool


async def ping() -> bool:
    if _pool is None:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as exc:
        logger.warning("PostgreSQL ping failed: %s", exc)
        return False
