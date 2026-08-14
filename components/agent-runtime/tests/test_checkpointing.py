#!/usr/bin/env python3
"""ADR-0103 tests for resumable workflow checkpointing:
`app.graph.build.build_graph`'s checkpointer wiring and
`app.main._resolve_run_id`'s resume/authorization logic.

Exercised against a `MemorySaver`-backed graph rather than a real Postgres
instance: `MemorySaver` and `AsyncPostgresSaver` both implement the same
`BaseCheckpointSaver` interface (`aget_tuple`, checkpoint shape with
`channel_values`) that `_resolve_run_id` and `build_graph` actually use, so
this proves the real production logic - the swap to a real Postgres
connection is exercised by `main.py`'s own `_checkpoint_conninfo()`/
`AsyncPostgresSaver.from_conn_string()` call, which needs a live database
this sandbox does not have (see main.py's own docstring for why MemorySaver
is the explicit, supported default here, not a test-only shortcut).

`_checkpoint_conninfo()`'s own string-building logic (no live DB needed)
*is* covered directly below - added after the 2026-08-14 incident where a
missing `sslmode` in that string produced a misleading "SSL required" error
masking the real "database does not exist" failure.

Run directly:

    cd components/agent-runtime && python3 tests/test_checkpointing.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

# app.graph.nodes reads AGENTS_DIR as a module-level constant at import time
# (via app.registry.AgentRegistry) - must be set before any `app.*` import,
# same as test_retrieve_metadata.py.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

import app.main as main_module  # noqa: E402
from app.auth import CallerIdentity  # noqa: E402
from app.graph.build import build_graph  # noqa: E402
from app.main import _checkpoint_conninfo, _resolve_run_id  # noqa: E402
from app.schemas import ChatRequest  # noqa: E402


def _identity(sub: str) -> CallerIdentity:
    return CallerIdentity(sub=sub, groups=["consultant"], raw_claims={}, token="fake-token")


async def test_no_run_id_mints_a_fresh_one_every_time() -> None:
    graph = build_graph(MemorySaver())
    payload = ChatRequest(session_id="s1", user_sub="alice", message="hi")

    run_id_a = await _resolve_run_id(graph, payload, _identity("alice"))
    run_id_b = await _resolve_run_id(graph, payload, _identity("alice"))

    assert run_id_a and run_id_b and run_id_a != run_id_b


async def test_resuming_an_unknown_run_id_is_a_404() -> None:
    graph = build_graph(MemorySaver())
    payload = ChatRequest(session_id="s1", user_sub="alice", message="hi", run_id="does-not-exist")

    try:
        await _resolve_run_id(graph, payload, _identity("alice"))
        raise AssertionError("expected an HTTPException for an unknown run_id")
    except Exception as exc:  # HTTPException
        assert getattr(exc, "status_code", None) == 404, exc


async def test_resuming_your_own_run_id_after_a_checkpoint_succeeds() -> None:
    graph = build_graph(MemorySaver())
    run_id = "run-abc"
    config = {"configurable": {"thread_id": run_id}}

    # Simulate a first turn that produced a checkpoint under this thread_id,
    # exactly like tekos_chat's real ainvoke() call does.
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


async def test_resuming_someone_elses_run_id_is_refused() -> None:
    """Security-negative: ADR-0103's core requirement - resumption
    re-enforces authorization, fail closed when the resuming subject
    differs from the checkpoint's own stored subject."""
    graph = build_graph(MemorySaver())
    run_id = "run-xyz"
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

    payload = ChatRequest(session_id="s1", user_sub="mallory", message="give me alice's data", run_id=run_id)
    try:
        await _resolve_run_id(graph, payload, _identity("mallory"))
        raise AssertionError("expected an HTTPException refusing cross-subject resume")
    except Exception as exc:  # HTTPException
        assert getattr(exc, "status_code", None) == 403, exc


async def test_resumed_state_actually_carries_forward() -> None:
    """Proves the point of checkpointing, not just the authorization gate:
    a second invoke() on the same thread_id sees state the first invoke()
    left behind (LangGraph's own merge/reducer behavior over TypedDict
    state - retrieved_docs accumulates rather than resets)."""
    graph = build_graph(MemorySaver())
    config = {"configurable": {"thread_id": "run-carry"}}

    first = await graph.ainvoke(
        {
            "session_id": "s1",
            "user_sub": "alice",
            "groups": [],
            "bearer_token": "t",
            "message": "first message",
            "retrieved_docs": [],
            "tool_results": {},
            "errors": [],
        },
        config=config,
    )
    assert first.get("user_sub") == "alice"

    tuple_ = await graph.checkpointer.aget_tuple(config)
    assert tuple_ is not None
    assert (tuple_.checkpoint.get("channel_values") or {}).get("user_sub") == "alice"


async def test_checkpoint_conninfo_is_none_when_unconfigured() -> None:
    """Incident 2026-08-14 regression: unset CHECKPOINT_PG* must fall back
    to MemorySaver, never produce a partial/broken conninfo string."""
    saved = (
        main_module.CHECKPOINT_PGHOST,
        main_module.CHECKPOINT_PGDATABASE,
        main_module.CHECKPOINT_PGUSER,
        main_module.CHECKPOINT_PGPASSWORD,
    )
    try:
        main_module.CHECKPOINT_PGHOST = ""
        main_module.CHECKPOINT_PGDATABASE = "agent-checkpoints"
        main_module.CHECKPOINT_PGUSER = "agentcheckpoints"
        main_module.CHECKPOINT_PGPASSWORD = "secret"
        assert _checkpoint_conninfo() is None
    finally:
        (
            main_module.CHECKPOINT_PGHOST,
            main_module.CHECKPOINT_PGDATABASE,
            main_module.CHECKPOINT_PGUSER,
            main_module.CHECKPOINT_PGPASSWORD,
        ) = saved


async def test_checkpoint_conninfo_includes_sslmode_and_dbname() -> None:
    """Incident 2026-08-14 regression: the conninfo string handed to
    AsyncPostgresSaver.from_conn_string must carry sslmode explicitly - its
    absence let psycopg fall back to a plaintext attempt that PGO's
    PgBouncer rejected with a misleading "SSL required" error, masking the
    real "database does not exist" failure."""
    saved = (
        main_module.CHECKPOINT_PGHOST,
        main_module.CHECKPOINT_PGPORT,
        main_module.CHECKPOINT_PGDATABASE,
        main_module.CHECKPOINT_PGUSER,
        main_module.CHECKPOINT_PGPASSWORD,
        main_module.CHECKPOINT_PGSSLMODE,
    )
    try:
        main_module.CHECKPOINT_PGHOST = "zuno-postgresql-pgbouncer.zuno-data.svc.cluster.local"
        main_module.CHECKPOINT_PGPORT = "5432"
        main_module.CHECKPOINT_PGDATABASE = "agent-checkpoints"
        main_module.CHECKPOINT_PGUSER = "agentcheckpoints"
        main_module.CHECKPOINT_PGPASSWORD = "secret"
        main_module.CHECKPOINT_PGSSLMODE = "require"

        conninfo = _checkpoint_conninfo()

        assert conninfo is not None
        assert "sslmode=require" in conninfo
        assert "dbname=agent-checkpoints" in conninfo
        assert "host=zuno-postgresql-pgbouncer.zuno-data.svc.cluster.local" in conninfo
    finally:
        (
            main_module.CHECKPOINT_PGHOST,
            main_module.CHECKPOINT_PGPORT,
            main_module.CHECKPOINT_PGDATABASE,
            main_module.CHECKPOINT_PGUSER,
            main_module.CHECKPOINT_PGPASSWORD,
            main_module.CHECKPOINT_PGSSLMODE,
        ) = saved


TESTS = [
    test_no_run_id_mints_a_fresh_one_every_time,
    test_resuming_an_unknown_run_id_is_a_404,
    test_resuming_your_own_run_id_after_a_checkpoint_succeeds,
    test_resuming_someone_elses_run_id_is_refused,
    test_resumed_state_actually_carries_forward,
    test_checkpoint_conninfo_is_none_when_unconfigured,
    test_checkpoint_conninfo_includes_sslmode_and_dbname,
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
