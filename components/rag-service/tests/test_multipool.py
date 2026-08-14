#!/usr/bin/env python3
"""ADR-0204 (WP-21) tests for the per-domain pool registry (app/db.py) and
hybrid_search's domain fan-out (app/search.py). No live database - pools
are faked, matching test_provider_parity.py's _FakeAsyncClient style for
mocking an external dependency's async interface.

Run directly:

    cd components/rag-service && python3 tests/test_multipool.py
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
from app.search import hybrid_search  # noqa: E402


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, query_sql, *args):
        return self._rows


class _FakeAcquire:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return _FakeConn(self._rows)

    async def __aexit__(self, *args):
        return False


class _FakePool:
    """Minimal asyncpg.Pool stand-in: acquire() yields a connection whose
    fetch() always returns the same canned rows, regardless of which query
    (vector or text) is issued - fine here since embed_query is mocked to
    return None, so only the text-query path ever calls fetch()."""

    def __init__(self, rows):
        self._rows = rows

    def acquire(self):
        return _FakeAcquire(self._rows)


def _row(id_, domain, title="t"):
    return {
        "id": id_,
        "source": f"source-{id_}",
        "title": title,
        "content": "content",
        "metadata": {"domain": domain},
    }


# --- app/search.py:hybrid_search domain fan-out -----------------------


def test_cross_domain_isolation_one_domains_connection_never_leaks_another() -> None:
    """Two distinct fake pools, one per domain - querying knowledge.sales
    must never surface knowledge.adv's rows, proving domain A's connection
    cannot read domain B's data."""
    sales_pool = _FakePool([_row(1, "knowledge.sales", "Sales doc")])
    adv_pool = _FakePool([_row(2, "knowledge.adv", "Adv doc")])
    pools = {"knowledge.sales": sales_pool, "knowledge.adv": adv_pool}

    async def run():
        with mock.patch("app.search.get_pool", side_effect=lambda d: pools.get(d)), \
             mock.patch("app.search.embed_query", return_value=_async_none()):
            return await hybrid_search("query", top_k=5, domains=["knowledge.sales"])

    result = asyncio.run(run())
    sources = {r["source"] for r in result["results"]}
    assert sources == {"source-1"}


def test_binding_config_only_backend_move_needs_zero_code_diff() -> None:
    """Repointing a domain to a different physical pool is purely a
    get_pool() resolution change (what app/bindings.py + app/db.py would do
    on a real binding-config edit) - the same hybrid_search call, unchanged,
    must serve whatever pool is currently registered for that domain."""
    pool_v1 = _FakePool([_row(1, "knowledge.tech", "Old backend doc")])
    pool_v2 = _FakePool([_row(2, "knowledge.tech", "New backend doc")])
    current = {"pool": pool_v1}

    async def run(expected_source: str):
        with mock.patch("app.search.get_pool", side_effect=lambda d: current["pool"]), \
             mock.patch("app.search.embed_query", return_value=_async_none()):
            result = await hybrid_search("query", top_k=5, domains=["knowledge.tech"])
        assert result["results"][0]["source"] == expected_source

    asyncio.run(run("source-1"))
    current["pool"] = pool_v2  # the only thing that changes - no hybrid_search edit
    asyncio.run(run("source-2"))


def test_unauthorized_or_unbound_domain_query_is_denied() -> None:
    """A domain with no live pool (never bound, or its binding failed to
    resolve) fails the call outright - defense in depth under Agent
    Runtime's own authorization, never silently served from elsewhere."""
    async def run():
        with mock.patch("app.search.get_pool", return_value=None), \
             mock.patch("app.search.embed_query", return_value=_async_none()):
            await hybrid_search("query", top_k=5, domains=["knowledge.bogus"])

    try:
        asyncio.run(run())
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "knowledge.bogus" in str(exc)


def test_one_down_domain_fails_the_whole_multi_domain_call() -> None:
    """"No silent partial results": if one of several requested domains has
    no live pool, the whole call fails rather than quietly returning only
    the domains that happened to be up."""
    tech_pool = _FakePool([_row(1, "knowledge.tech")])
    pools = {"knowledge.tech": tech_pool}  # knowledge.sales deliberately absent

    async def run():
        with mock.patch("app.search.get_pool", side_effect=lambda d: pools.get(d)), \
             mock.patch("app.search.embed_query", return_value=_async_none()):
            await hybrid_search("query", top_k=5, domains=["knowledge.tech", "knowledge.sales"])

    try:
        asyncio.run(run())
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "knowledge.sales" in str(exc)


def test_absent_domains_defaults_to_knowledge_tech_only() -> None:
    """Additive/backward-compatible: a caller that never sends `domains`
    (every pre-ADR-0204 caller) still gets exactly the tech domain, not
    every domain and not none."""
    tech_pool = _FakePool([_row(1, "knowledge.tech")])
    sales_pool = _FakePool([_row(2, "knowledge.sales")])
    pools = {"knowledge.tech": tech_pool, "knowledge.sales": sales_pool}

    async def run():
        with mock.patch("app.search.get_pool", side_effect=lambda d: pools.get(d)), \
             mock.patch("app.search.embed_query", return_value=_async_none()):
            return await hybrid_search("query", top_k=5)  # no domains argument

    result = asyncio.run(run())
    sources = {r["source"] for r in result["results"]}
    assert sources == {"source-1"}


async def _async_none():
    return None


# --- app/db.py connect_all / per-domain env credentials -----------------


def test_connect_one_skips_domain_when_credentials_missing() -> None:
    binding = KnowledgeBinding(domain="knowledge.tech", database_name="rag-tech", schema="rag", credential_env_prefix="TESTMISSING")
    os.environ.pop("TESTMISSING_PGUSER", None)
    os.environ.pop("TESTMISSING_PGPASSWORD", None)

    async def run():
        await db._connect_one(binding)

    asyncio.run(run())
    assert db.get_pool("knowledge.tech") is None
    assert "knowledge.tech" in db._pool_errors
    db._pool_errors.pop("knowledge.tech", None)


def test_connect_one_creates_a_pool_with_per_domain_credentials_and_search_path() -> None:
    binding = KnowledgeBinding(domain="knowledge.tech", database_name="rag-tech", schema="rag", credential_env_prefix="TESTOK")
    os.environ["TESTOK_PGUSER"] = "ragtech"
    os.environ["TESTOK_PGPASSWORD"] = "secret"

    captured = {}

    async def fake_create_pool(**kwargs):
        captured.update(kwargs)
        return "a-fake-pool-object"

    async def run():
        with mock.patch("asyncpg.create_pool", side_effect=fake_create_pool):
            await db._connect_one(binding)

    try:
        asyncio.run(run())
        assert db.get_pool("knowledge.tech") == "a-fake-pool-object"
        assert captured["database"] == "rag-tech"
        assert captured["user"] == "ragtech"
        assert captured["password"] == "secret"
        assert captured["server_settings"] == {"search_path": "rag"}
    finally:
        db._pools.pop("knowledge.tech", None)
        os.environ.pop("TESTOK_PGUSER", None)
        os.environ.pop("TESTOK_PGPASSWORD", None)


TESTS = [
    test_cross_domain_isolation_one_domains_connection_never_leaks_another,
    test_binding_config_only_backend_move_needs_zero_code_diff,
    test_unauthorized_or_unbound_domain_query_is_denied,
    test_one_down_domain_fails_the_whole_multi_domain_call,
    test_absent_domains_defaults_to_knowledge_tech_only,
    test_connect_one_skips_domain_when_credentials_missing,
    test_connect_one_creates_a_pool_with_per_domain_credentials_and_search_path,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
