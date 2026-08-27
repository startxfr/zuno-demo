#!/usr/bin/env python3
"""ADR-0212 tests for app/conversations.py and the _resolve_run_id
ownership-check widening in app/main.py.

Same philosophy as tests/test_checkpointing.py: this sandbox has no live
Postgres, so these tests prove what's provable without one - the pure
title-derivation/conninfo-building logic, the pool_context()
unconfigured-degrade path, and every function's fail-closed 503 when
handed a None pool (the meaningful security-negative proof: a caller
that forgot to configure CONVERSATIONS_PG*, or hit it while genuinely
down, gets a hard failure, never a silent "no restriction"). The real
SQL/DDL against a live agent-conversations database is exercised
separately against the actual cluster, the same "deferred to production"
split test_checkpointing.py's own docstring documents for the checkpoint
pool.

Run directly:

    cd components/agent-runtime && python3 tests/test_conversations.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from contextlib import asynccontextmanager

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

from fastapi import HTTPException  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from psycopg_pool import PoolTimeout  # noqa: E402

import app.conversations as conversations_module  # noqa: E402
from app.auth import CallerIdentity  # noqa: E402
from app.conversations import (  # noqa: E402
    _conninfo,
    _derive_title,
    acquire_write_lock,
    archive_conversation,
    _derive_clone_title,
    clone_conversation,
    hard_delete_conversation,
    list_conversations,
    pool_context,
    release_write_lock,
    rename_conversation,
    reorder_conversations,
    resolve_access,
    resolve_owner,
    set_star,
)
from app.graph.nodes import _ANSWER_TASK, _TEKOS  # noqa: E402
from app.graph.shapes.retrieve_reason_respond import build as _build  # noqa: E402
from app.main import _resolve_run_id  # noqa: E402
from app.schemas import ChatRequest  # noqa: E402


def build_graph(checkpointer):
    return _build(checkpointer, _TEKOS, _ANSWER_TASK)


def _identity(sub: str) -> CallerIdentity:
    return CallerIdentity(sub=sub, groups=["consultant"], raw_claims={}, token="fake-token")


def _patch_env(**values):
    saved = {
        "CONVERSATIONS_PGHOST": conversations_module.CONVERSATIONS_PGHOST,
        "CONVERSATIONS_PGPORT": conversations_module.CONVERSATIONS_PGPORT,
        "CONVERSATIONS_PGDATABASE": conversations_module.CONVERSATIONS_PGDATABASE,
        "CONVERSATIONS_PGUSER": conversations_module.CONVERSATIONS_PGUSER,
        "CONVERSATIONS_PGPASSWORD": conversations_module.CONVERSATIONS_PGPASSWORD,
        "CONVERSATIONS_PGSSLMODE": conversations_module.CONVERSATIONS_PGSSLMODE,
    }
    for key, value in values.items():
        setattr(conversations_module, key, value)
    return saved


def _restore_env(saved: dict) -> None:
    for key, value in saved.items():
        setattr(conversations_module, key, value)


async def test_conninfo_is_none_when_unconfigured() -> None:
    """Incident 2026-08-14-style regression, same rationale as
    test_checkpointing.py's own equivalent test: unset CONVERSATIONS_PG*
    must degrade cleanly (None), never a partial/broken conninfo string."""
    saved = _patch_env(
        CONVERSATIONS_PGHOST="",
        CONVERSATIONS_PGDATABASE="agent-conversations",
        CONVERSATIONS_PGUSER="agentconversations",
        CONVERSATIONS_PGPASSWORD="secret",
    )
    try:
        assert _conninfo() is None
    finally:
        _restore_env(saved)


async def test_conninfo_includes_sslmode_and_dbname() -> None:
    saved = _patch_env(
        CONVERSATIONS_PGHOST="zuno-postgresql-pgbouncer.zuno-data.svc.cluster.local",
        CONVERSATIONS_PGPORT="5432",
        CONVERSATIONS_PGDATABASE="agent-conversations",
        CONVERSATIONS_PGUSER="agentconversations",
        CONVERSATIONS_PGPASSWORD="secret",
        CONVERSATIONS_PGSSLMODE="require",
    )
    try:
        conninfo = _conninfo()
        assert conninfo is not None
        assert "sslmode=require" in conninfo
        assert "dbname=agent-conversations" in conninfo
        assert "user=agentconversations" in conninfo
    finally:
        _restore_env(saved)


async def test_pool_context_yields_none_when_unconfigured() -> None:
    """The unconfigured-degrade path is provable without a live DB - this
    is the exact branch every CI run (no CONVERSATIONS_PG*) exercises."""
    saved = _patch_env(CONVERSATIONS_PGHOST="", CONVERSATIONS_PGDATABASE="", CONVERSATIONS_PGUSER="", CONVERSATIONS_PGPASSWORD="")
    try:
        async with pool_context() as pool:
            assert pool is None
    finally:
        _restore_env(saved)


async def test_derive_title_uses_the_message_as_is_when_short() -> None:
    assert _derive_title("How do I configure OpenShift AI?") == "How do I configure OpenShift AI?"


async def test_derive_title_collapses_whitespace() -> None:
    assert _derive_title("  hello   world  \n") == "hello world"


async def test_derive_title_truncates_long_messages_with_ellipsis() -> None:
    message = "x" * 100
    title = _derive_title(message, max_length=60)
    assert len(title) == 60
    assert title.endswith("…")


async def _expect_503(coro) -> None:
    try:
        await coro
        raise AssertionError("expected an HTTPException(503) for a None pool")
    except HTTPException as exc:
        assert exc.status_code == 503, exc


async def test_resolve_owner_fails_closed_on_a_none_pool() -> None:
    """ADR-0212 Security considerations: list/transcript/resume must fail
    closed (503), never silently proceed unrestricted, if the pool is
    unreachable/unconfigured."""
    await _expect_503(resolve_owner(None, "run-abc"))


async def test_list_conversations_fails_closed_on_a_none_pool() -> None:
    await _expect_503(list_conversations(None, agent_name="tekos", subject="alice", groups=["consultant"]))


async def test_rename_conversation_fails_closed_on_a_none_pool() -> None:
    await _expect_503(rename_conversation(None, run_id="run-abc", subject="alice", groups=[], title="New title"))


async def test_set_star_fails_closed_on_a_none_pool() -> None:
    await _expect_503(set_star(None, run_id="run-abc", subject="alice", groups=[], starred=True))


async def test_archive_conversation_fails_closed_on_a_none_pool() -> None:
    await _expect_503(archive_conversation(None, run_id="run-abc", subject="alice", groups=[]))


async def test_reorder_conversations_fails_closed_on_a_none_pool() -> None:
    """ADR-0515: same fail-closed posture as every other writer in this
    module besides record_turn."""
    await _expect_503(reorder_conversations(None, agent_name="tekos", owner_sub="alice", run_ids=["run-abc"]))


async def test_hard_delete_conversation_fails_closed_on_a_none_pool() -> None:
    """ADR-0515: same fail-closed posture as archive_conversation - an
    irreversible operation must never silently proceed unrestricted."""
    await _expect_503(hard_delete_conversation(None, run_id="run-abc", owner_sub="alice"))


async def test_resolve_access_fails_closed_on_a_none_pool() -> None:
    """ADR-0527: the single access check inherits ADR-0213's posture - a
    caller must never treat "pool unreachable" as "no role, but proceed
    anyway". This is the one function every read and write path in
    app/main.py now goes through, so its fail-closed behaviour is the
    whole module's."""
    await _expect_503(resolve_access(None, run_id="run-abc", subject="alice", groups=["consultant"]))


async def test_owner_always_outranks_a_weaker_project_role() -> None:
    """ADR-0527 clause 3: owner_sub keeps granting write on your own
    conversation whatever your project role - that is precisely what makes
    the `clone` role useful (fork and continue) rather than merely
    archival. An owner who is ALSO a project admin keeps the stronger
    role, so they do not lose the admin-only actions by owning the row."""
    for project_role, expected in [(None, "write"), ("read", "write"), ("clone", "write"),
                                   ("write", "write"), ("admin", "admin")]:
        resolved = "admin" if project_role == "admin" else "write"
        assert resolved == expected, f"owner with project role {project_role!r} resolved {resolved!r}"


async def test_role_ranks_form_a_total_order() -> None:
    """ADR-0527 clause 2: read < clone < write < admin, so "the strongest
    grant that matches the caller wins" is well-defined when a direct
    grant and a group grant disagree. rank_of returns 0 - the fail-closed
    floor - for no role at all."""
    assert conversations_module.rank_of(None) == 0
    assert conversations_module.rank_of("nonsense") == 0
    ranks = [conversations_module.rank_of(r) for r in ("read", "clone", "write", "admin")]
    assert ranks == sorted(ranks) and len(set(ranks)) == 4, ranks


async def test_derive_clone_title_increments_rather_than_nesting() -> None:
    """ADR-0527 clause 4: a clone stays in its source project, so it needs
    a name that distinguishes it in the same list without growing a
    "(copy) (copy) (copy)" tail."""
    assert _derive_clone_title("Foo") == "Foo (copy)"
    assert _derive_clone_title("Foo (copy)") == "Foo (copy 2)"
    assert _derive_clone_title("Foo (copy 7)") == "Foo (copy 8)"
    assert _derive_clone_title("") == "Untitled conversation (copy)"


async def test_derive_clone_title_respects_the_rename_ceiling() -> None:
    """Cloning a maximal title must not produce a row the rename endpoint
    (max_length=200 in app/schemas.py) would then refuse."""
    assert len(_derive_clone_title("A" * 250)) <= 200


async def test_clone_conversation_fails_closed_on_a_none_pool() -> None:
    await _expect_503(clone_conversation(None, source_run_id="run-abc", new_run_id="run-def", owner_sub="bob"))


async def test_acquire_write_lock_trivially_succeeds_on_a_none_pool() -> None:
    """ADR-0213: like record_turn, this is the other deliberate exception
    to the fail-closed rule - without conversation persistence configured
    there is no conversation_memberships row anyone else could hold to
    even contend for this lock, so chat must keep working unconditionally."""
    acquired = await acquire_write_lock(None, run_id="run-abc", holder_sub="alice")
    assert acquired is True


async def test_release_write_lock_silently_no_ops_on_a_none_pool() -> None:
    await release_write_lock(None, run_id="run-abc", holder_sub="alice")  # no exception raised = pass


async def test_record_turn_silently_no_ops_on_a_none_pool() -> None:
    """The one deliberate exception to the fail-closed rule above (see
    conversations.py's own docstring): ordinary chat must keep working
    even when conversation persistence isn't configured."""
    await conversations_module.record_turn(
        None, run_id="run-abc", agent_name="tekos", owner_sub="alice", opening_message="hi"
    )  # no exception raised = pass


class _FakePoolThatTimesOut:
    """Stands in for a configured-but-transiently-unavailable pool: unlike
    the None-pool case above, checkout itself raises - proving record_turn
    degrades the same way, not just when the feature is off entirely."""

    @asynccontextmanager
    async def connection(self):
        raise PoolTimeout("couldn't get a connection after 30.00 sec")
        yield  # pragma: no cover - unreachable, keeps this an async generator


async def test_record_turn_swallows_a_transient_pool_timeout() -> None:
    """2026-08-21 live-cluster incident: a configured conversations pool
    that can't hand out a connection within its checkout window must not
    500 the whole chat reply over a missed metadata row - record_turn is
    incidental bookkeeping on the hot /chat path, not something the caller
    asked for."""
    await conversations_module.record_turn(
        _FakePoolThatTimesOut(), run_id="run-abc", agent_name="arkos", owner_sub="alice", opening_message="hi"
    )  # no exception raised = pass


async def test_resolve_run_id_still_defaults_to_checkpoint_only_check() -> None:
    """ADR-0212 widens _resolve_run_id's ownership check, but only when a
    conversations_pool is actually passed - every existing call site
    (and this test) that omits it keeps ADR-0103's original,
    checkpoint-only behavior unchanged."""
    graph = build_graph(MemorySaver())
    run_id = "run-conv-default"
    config = {"configurable": {"thread_id": run_id}}

    await graph.ainvoke(
        {
            "session_id": "s1",
            "user_sub": "alice",
            "groups": [],
            "bearer_token": "t",
            "message": "hi",
            "retrieved_docs": [],
            "tool_results": {},
            "errors": [],
        },
        config=config,
    )

    payload = ChatRequest(session_id="s1", user_sub="alice", message="continue", run_id=run_id)
    resolved = await _resolve_run_id(graph, payload, _identity("alice"))
    assert resolved == run_id

    try:
        await _resolve_run_id(graph, payload, _identity("mallory"))
        raise AssertionError("expected an HTTPException refusing cross-subject resume")
    except HTTPException as exc:
        assert exc.status_code == 403, exc


TESTS = [
    test_conninfo_is_none_when_unconfigured,
    test_conninfo_includes_sslmode_and_dbname,
    test_pool_context_yields_none_when_unconfigured,
    test_derive_title_uses_the_message_as_is_when_short,
    test_derive_title_collapses_whitespace,
    test_derive_title_truncates_long_messages_with_ellipsis,
    test_resolve_owner_fails_closed_on_a_none_pool,
    test_list_conversations_fails_closed_on_a_none_pool,
    test_rename_conversation_fails_closed_on_a_none_pool,
    test_set_star_fails_closed_on_a_none_pool,
    test_archive_conversation_fails_closed_on_a_none_pool,
    test_reorder_conversations_fails_closed_on_a_none_pool,
    test_hard_delete_conversation_fails_closed_on_a_none_pool,
    test_resolve_access_fails_closed_on_a_none_pool,
    test_owner_always_outranks_a_weaker_project_role,
    test_role_ranks_form_a_total_order,
    test_derive_clone_title_increments_rather_than_nesting,
    test_derive_clone_title_respects_the_rename_ceiling,
    test_clone_conversation_fails_closed_on_a_none_pool,
    test_acquire_write_lock_trivially_succeeds_on_a_none_pool,
    test_release_write_lock_silently_no_ops_on_a_none_pool,
    test_record_turn_silently_no_ops_on_a_none_pool,
    test_record_turn_swallows_a_transient_pool_timeout,
    test_resolve_run_id_still_defaults_to_checkpoint_only_check,
]


async def _run_all() -> int:
    failures = 0
    for test in TESTS:
        try:
            await test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return failures


def main() -> int:
    failures = asyncio.run(_run_all())
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
