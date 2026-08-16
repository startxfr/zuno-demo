"""ADR-0204 (WP-21) per-domain asyncpg connection pool registry: one pool
per knowledge domain, resolved through app/bindings.py's
KnowledgeBindingRegistry rather than a single fixed database. Connect is
eager (attempted for every configured domain at startup) but a single
domain's failure is never fatal to the others - the same graceful-
degradation posture the pre-ADR-0204 single pool already had (this service
must not crash-loop just because one domain's database isn't reachable
yet, e.g. before an operator has run that domain's schema-apply).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, Optional

import asyncpg

from app import config
from app.bindings import KnowledgeBinding, KnowledgeBindingRegistry

logger = logging.getLogger("rag_service.db")

_pools: Dict[str, asyncpg.Pool] = {}
_pool_errors: Dict[str, str] = {}


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


async def _connect_one(binding: KnowledgeBinding) -> None:
    user = os.getenv(binding.pguser_env, "")
    password = os.getenv(binding.pgpassword_env, "")
    if not user or not password:
        msg = (
            f"{binding.pguser_env}/{binding.pgpassword_env} not set - "
            f"domain '{binding.domain}' will report not-ready until its "
            "ExternalSecret-populated credentials are present"
        )
        logger.warning(msg)
        _pool_errors[binding.domain] = msg
        return

    try:
        pool = await asyncpg.create_pool(
            host=config.PGHOST,
            port=config.PGPORT,
            database=binding.database_name,
            user=user,
            password=password,
            min_size=config.PG_POOL_MIN_SIZE,
            max_size=config.PG_POOL_MAX_SIZE,
            init=_init_connection,
            # <schema>,public not just <schema> - the vector extension's
            # objects live in public (databaseInitSQL creates it with the
            # default search_path), so a bare per-domain search_path can't
            # resolve the vector type/operators at query time (VERIFIED
            # live 2026-08-15 via the schema-apply Job's identical failure).
            server_settings={"search_path": f"{binding.schema},public"},
            # VERIFIED live (2026-08-15, WP-21): connecting direct to the
            # PGO primary (required because PgBouncer's transaction pooling
            # rejects the search_path startup option above) needs TLS -
            # PGO's pg_hba only has hostssl entries for external clients
            # ("no pg_hba.conf entry ... no encryption" otherwise). asyncpg
            # ignores PGSSLMODE, so this must be explicit.
            ssl="require",
        )
        _pools[binding.domain] = pool
        _pool_errors.pop(binding.domain, None)
        logger.info(
            "connected to PostgreSQL for domain %s at %s:%s/%s (schema=%s)",
            binding.domain, config.PGHOST, config.PGPORT, binding.database_name, binding.schema,
        )
    except Exception as exc:
        msg = f"failed to connect for domain '{binding.domain}': {exc}"
        logger.error(msg)
        _pool_errors[binding.domain] = msg


async def connect_all(registry: KnowledgeBindingRegistry) -> None:
    """Attempts a connection for every domain the registry resolves.
    Never raises - a domain with no live pool is simply absent from
    get_pool()'s results (fail closed at query time, not startup time,
    matching the pre-ADR-0204 "don't crash-loop the pod" posture)."""
    if registry.load_error:
        logger.error("knowledge bindings unavailable, no domain pools can be created: %s", registry.load_error)
        return
    for domain in registry.domains():
        binding = registry.resolve(domain)
        if binding is not None:
            await _connect_one(binding)


async def disconnect_all() -> None:
    for domain, pool in list(_pools.items()):
        await pool.close()
        _pools.pop(domain, None)


def get_pool(domain: str) -> Optional[asyncpg.Pool]:
    return _pools.get(domain)


def ready_domains() -> Dict[str, str]:
    """Domain -> live/error status, for /readyz reporting."""
    status: Dict[str, str] = {domain: "ready" for domain in _pools}
    status.update({domain: f"not-ready: {err}" for domain, err in _pool_errors.items()})
    return status


def any_ready() -> bool:
    return bool(_pools)


async def ping(domain: str) -> bool:
    pool = _pools.get(domain)
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as exc:
        logger.warning("PostgreSQL ping failed for domain %s: %s", domain, exc)
        return False


async def ping_any() -> bool:
    """True as soon as any one domain's pool answers a live query - the
    multi-domain equivalent of the pre-ADR-0204 single ping(), and the
    /readyz semantics this service keeps: ready means "at least one
    configured domain can actually serve a query", not "every domain is
    up" (a domain whose schema-apply hasn't run yet must not take the
    whole pod out of rotation)."""
    for domain in list(_pools.keys()):
        if await ping(domain):
            return True
    return False
