#!/usr/bin/env python3
"""Tests for app/db.py's lazy reconnect (_retry_failed / ping_any /
retry_failed_domains): a domain whose startup connect failed must be
re-attempted - interval-bounded - and become ready once the database
answers, WITHOUT a pod restart. Motivated by the 2026-08-18 cluster
restart: PostgreSQL came up after rag-service, the connect-once-at-
lifespan posture left every domain dead, and retrieval stayed down until
a manual pod delete. No live database - asyncpg.create_pool is mocked,
matching test_multipool.py's style.

Run directly:

    cd components/rag-service && python3 tests/test_reconnect.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app import db  # noqa: E402
from app.bindings import KnowledgeBinding  # noqa: E402


def _binding(domain="knowledge.tech"):
    return KnowledgeBinding(
        domain=domain,
        database_name="rag-tech",
        schema="ragtech",
        credential_env_prefix="TEST_RECONNECT",
    )


class _FakePingPool:
    """Pool whose acquired connection answers SELECT 1 - enough for
    ping()/ping_any() to consider the domain live."""

    class _Conn:
        async def execute(self, sql):
            return "SELECT 1"

    class _Acquire:
        async def __aenter__(self):
            return _FakePingPool._Conn()

        async def __aexit__(self, *args):
            return False

    def acquire(self):
        return _FakePingPool._Acquire()

    async def close(self):
        return None


def _reset_db_state() -> None:
    db._pools.clear()
    db._pool_errors.clear()
    db._bindings.clear()
    db._last_retry_at = 0.0
    os.environ["TEST_RECONNECT_PGUSER"] = "u"
    os.environ["TEST_RECONNECT_PGPASSWORD"] = "p"


def test_failed_domain_recovers_on_ping_any_retry() -> None:
    """Startup connect fails (database still starting up); the next
    ping_any() retries and the domain becomes ready once create_pool
    succeeds - the exact 2026-08-18 restart sequence."""
    _reset_db_state()
    b = _binding()
    db._bindings[b.domain] = b

    async def scenario():
        boom = mock.AsyncMock(side_effect=Exception("the database system is starting up"))
        with mock.patch.object(db.asyncpg, "create_pool", boom):
            await db._connect_one(b)
        assert b.domain in db._pool_errors and b.domain not in db._pools

        ok = mock.AsyncMock(return_value=_FakePingPool())
        with mock.patch.object(db.asyncpg, "create_pool", ok):
            return await db.ping_any()

    assert asyncio.run(scenario()) is True
    assert db._bindings[_binding().domain].domain not in db._pool_errors
    assert "knowledge.tech" in db._pools


def test_retry_is_interval_bounded() -> None:
    """Two back-to-back retries inside the min interval must attempt the
    reconnect only once - probe traffic must not hammer a down database."""
    _reset_db_state()
    b = _binding()
    db._bindings[b.domain] = b
    db._pool_errors[b.domain] = "seed failure"

    async def scenario():
        boom = mock.AsyncMock(side_effect=Exception("still down"))
        with mock.patch.object(db.asyncpg, "create_pool", boom):
            await db.retry_failed_domains()
            await db.retry_failed_domains()
        return boom.await_count

    assert asyncio.run(scenario()) == 1


def test_ready_domains_are_untouched_by_retry() -> None:
    """A healthy pool must never be reconnected/replaced by the retry
    path - only _pool_errors domains are attempted."""
    _reset_db_state()
    healthy = _FakePingPool()
    db._pools["knowledge.sales"] = healthy

    async def scenario():
        boom = mock.AsyncMock(side_effect=Exception("never called"))
        with mock.patch.object(db.asyncpg, "create_pool", boom):
            result = await db.ping_any()
        return result, boom.await_count

    result, attempts = asyncio.run(scenario())
    assert result is True
    assert attempts == 0
    assert db._pools["knowledge.sales"] is healthy


def test_no_bindings_no_crash() -> None:
    """A failed domain with no remembered binding (registry load error) is
    skipped, never raises."""
    _reset_db_state()
    db._pool_errors["knowledge.ghost"] = "orphan error"

    async def scenario():
        await db.retry_failed_domains()
        return True

    assert asyncio.run(scenario()) is True


TESTS = [
    test_failed_domain_recovers_on_ping_any_retry,
    test_retry_is_interval_bounded,
    test_ready_domains_are_untouched_by_retry,
    test_no_bindings_no_crash,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
