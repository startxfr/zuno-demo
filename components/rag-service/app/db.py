"""asyncpg connection pool lifecycle."""

from __future__ import annotations

import logging
from typing import Optional

import asyncpg

from app import config

logger = logging.getLogger("rag_service.db")

_pool: Optional[asyncpg.Pool] = None


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
