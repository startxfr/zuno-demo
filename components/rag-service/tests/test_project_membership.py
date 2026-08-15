#!/usr/bin/env python3
"""ADR-0209 (WP-28) tests for knowledge.project's fail-closed membership
check (app/search.py:_check_project_membership, hybrid_search) and the
OGX provider's honest refusal to serve that domain at all. No live
database - pools are faked, matching test_multipool.py's style.

Run directly:

    cd components/rag-service && python3 tests/test_project_membership.py
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app import ogx_provider  # noqa: E402
from app.search import ProjectMembershipDenied, hybrid_search  # noqa: E402


class _FakeConn:
    """Supports both fetch() (content rows) and fetchrow() (the
    membership check) - membership_rows maps project_id -> the row
    fetchrow() should return (None means "no membership")."""

    def __init__(self, content_rows, membership_rows, fetch_calls):
        self._content_rows = content_rows
        self._membership_rows = membership_rows
        self._fetch_calls = fetch_calls

    async def fetch(self, query_sql, *args):
        self._fetch_calls.append(query_sql)
        return self._content_rows

    async def fetchrow(self, query_sql, project_id, caller_sub, caller_groups):
        return self._membership_rows.get(project_id)


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        return False


class _FakePool:
    def __init__(self, content_rows=None, membership_rows=None):
        self.fetch_calls: list = []
        self._conn = _FakeConn(content_rows or [], membership_rows or {}, self.fetch_calls)

    def acquire(self):
        return _FakeAcquire(self._conn)


def _row(id_, project_id):
    return {
        "id": id_,
        "source": f"source-{id_}",
        "title": "Project fact",
        "content": "content",
        "metadata": {"domain": "knowledge.project", "project_id": project_id, "indexed_at": "2026-08-15T00:00:00Z"},
    }


async def _async_none():
    return None


def test_project_domain_without_project_id_or_caller_sub_is_rejected() -> None:
    pool = _FakePool()

    async def run():
        with mock.patch("app.search.get_pool", return_value=pool), \
             mock.patch("app.search.embed_query", return_value=_async_none()):
            await hybrid_search("query", top_k=5, domains=["knowledge.project"])

    try:
        asyncio.run(run())
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "project_id/caller_sub" in str(exc)
    assert pool.fetch_calls == [], "no content query should ever run before the malformed-request check"


def test_membership_by_subject_allows_retrieval_and_scopes_by_project_id() -> None:
    pool = _FakePool(
        content_rows=[_row(1, "demo-001")],
        membership_rows={"demo-001": {"exists": 1}},
    )

    async def run():
        with mock.patch("app.search.get_pool", return_value=pool), \
             mock.patch("app.search.embed_query", return_value=_async_none()):
            return await hybrid_search(
                "query", top_k=5, domains=["knowledge.project"],
                project_id="demo-001", caller_sub="alice",
            )

    result = asyncio.run(run())
    assert {r["source"] for r in result["results"]} == {"source-1"}


def test_membership_by_group_also_allows_retrieval() -> None:
    """The membership fail-closed check accepts subject OR group match -
    exercised here via a fake pool that only "has" a row when queried
    (group membership is opaque to this fake, real semantics live in the
    SQL query app/search.py issues; this test only proves the boolean
    row-present/absent outcome is respected end to end)."""
    pool = _FakePool(
        content_rows=[_row(2, "demo-001")],
        membership_rows={"demo-001": {"exists": 1}},
    )

    async def run():
        with mock.patch("app.search.get_pool", return_value=pool), \
             mock.patch("app.search.embed_query", return_value=_async_none()):
            return await hybrid_search(
                "query", top_k=5, domains=["knowledge.project"],
                project_id="demo-001", caller_sub="someone-else", caller_groups=["consultant"],
            )

    result = asyncio.run(run())
    assert {r["source"] for r in result["results"]} == {"source-2"}


def test_no_membership_row_denies_and_never_touches_content() -> None:
    """ADR-0209 fail-closed: no project_memberships row for this
    project_id/caller -> denied before any content query runs (proves
    "no memberships, structured state, or semantic chunks" are ever
    reachable, not just that the response ends up empty)."""
    pool = _FakePool(
        content_rows=[_row(3, "demo-001")],  # would be returned if the check were skipped
        membership_rows={},  # no membership row for anyone
    )

    async def run():
        with mock.patch("app.search.get_pool", return_value=pool), \
             mock.patch("app.search.embed_query", return_value=_async_none()):
            await hybrid_search(
                "query", top_k=5, domains=["knowledge.project"],
                project_id="demo-001", caller_sub="mallory",
            )

    try:
        asyncio.run(run())
        raise AssertionError("expected ProjectMembershipDenied")
    except ProjectMembershipDenied as exc:
        assert "demo-001" in str(exc)
    assert pool.fetch_calls == [], "no content query should ever run once membership is denied"


def test_wrong_project_id_is_denied_even_with_membership_elsewhere() -> None:
    """A caller who IS a member of some project must not be able to read
    a DIFFERENT project's memory just by naming it."""
    pool = _FakePool(
        content_rows=[_row(4, "someone-elses-project")],
        membership_rows={"demo-001": {"exists": 1}},  # member of demo-001, NOT the requested project
    )

    async def run():
        with mock.patch("app.search.get_pool", return_value=pool), \
             mock.patch("app.search.embed_query", return_value=_async_none()):
            await hybrid_search(
                "query", top_k=5, domains=["knowledge.project"],
                project_id="someone-elses-project", caller_sub="alice",
            )

    try:
        asyncio.run(run())
        raise AssertionError("expected ProjectMembershipDenied")
    except ProjectMembershipDenied:
        pass


def test_ogx_provider_refuses_knowledge_project_outright() -> None:
    """The OGX prototype has no project_memberships access - serving
    knowledge.project without the membership check would be a real
    authorization gap, so it refuses the whole call rather than silently
    skipping the check."""
    async def run():
        await ogx_provider.ogx_search(
            "query", top_k=5, domains=["knowledge.project"],
            project_id="demo-001", caller_sub="alice",
        )

    try:
        asyncio.run(run())
        raise AssertionError("expected OgxProviderError")
    except ogx_provider.OgxProviderError as exc:
        assert "knowledge.project" in str(exc)


TESTS = [
    test_project_domain_without_project_id_or_caller_sub_is_rejected,
    test_membership_by_subject_allows_retrieval_and_scopes_by_project_id,
    test_membership_by_group_also_allows_retrieval,
    test_no_membership_row_denies_and_never_touches_content,
    test_wrong_project_id_is_denied_even_with_membership_elsewhere,
    test_ogx_provider_refuses_knowledge_project_outright,
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
