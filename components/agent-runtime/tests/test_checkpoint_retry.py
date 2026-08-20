#!/usr/bin/env python3
"""Tests for the checkpoint-DB connection-failure retry added 2026-08-19,
after a live incident: a cluster with several Patroni failovers left
agent-runtime's checkpoint pool handing out an already-dead connection,
surfacing `psycopg.OperationalError` ("SSL SYSCALL error: EOF detected")
straight to the caller as a 500 (non-streaming) or an `error` SSE event
(streaming) - even though the pool itself would have self-healed on the
very next request. `app.main._ainvoke_with_retry` and `_stream_chat`'s own
retry-once loop cover this; `lifespan`'s `check=AsyncConnectionPool.
check_connection` (not exercised here - needs a live pool) is the
complementary, proactive half of the fix.

Uses fake graph objects (no real LangGraph/Postgres involved) so this
never needs a live database, same posture as test_checkpointing.py's own
MemorySaver-based tests.

Run directly:

    cd components/agent-runtime && python3 tests/test_checkpoint_retry.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

# app.graph.nodes reads AGENTS_DIR as a module-level constant at import time
# (via app.registry.AgentRegistry) - must be set before any `app.*` import,
# same as test_checkpointing.py.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

import psycopg  # noqa: E402

import app.main as main_module  # noqa: E402


class _FakeAinvokeGraph:
    """`side_effects[i]` is either an exception instance (raised) or a
    return value, one entry consumed per `ainvoke` call."""

    def __init__(self, side_effects: list) -> None:
        self.calls = 0
        self._side_effects = list(side_effects)

    async def ainvoke(self, initial_state, config=None):
        effect = self._side_effects[self.calls]
        self.calls += 1
        if isinstance(effect, BaseException):
            raise effect
        return effect


async def test_ainvoke_retries_once_on_operational_error() -> None:
    graph = _FakeAinvokeGraph([
        psycopg.OperationalError("consuming input failed: SSL SYSCALL error: EOF detected"),
        {"reply": "ok", "source_mode": "indexed"},
    ])
    result = await main_module._ainvoke_with_retry(graph, {}, {}, session_id="s1", request_id="r1")
    assert result == {"reply": "ok", "source_mode": "indexed"}
    assert graph.calls == 2


async def test_ainvoke_does_not_retry_non_connection_errors() -> None:
    """A real application bug (anything that isn't psycopg.OperationalError)
    must propagate immediately - retrying it would just double the
    latency/LLM cost for a call guaranteed to fail again identically."""
    graph = _FakeAinvokeGraph([ValueError("some unrelated bug")])
    try:
        await main_module._ainvoke_with_retry(graph, {}, {}, session_id="s1", request_id="r1")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError to propagate, not be swallowed/retried")
    assert graph.calls == 1


async def test_ainvoke_second_failure_still_raises() -> None:
    """A DB that's genuinely still down after the retry must still surface
    as a failure - existing 500 behavior for a real outage is unchanged."""
    graph = _FakeAinvokeGraph([
        psycopg.OperationalError("first failure"),
        psycopg.OperationalError("second failure"),
    ])
    try:
        await main_module._ainvoke_with_retry(graph, {}, {}, session_id="s1", request_id="r1")
    except psycopg.OperationalError as exc:
        assert "second failure" in str(exc)
    else:
        raise AssertionError("expected the second OperationalError to propagate")
    assert graph.calls == 2


def _token_event(text: str, tags: list = None) -> dict:
    event = {"event": "on_chat_model_stream", "name": "reason", "data": {"chunk": SimpleNamespace(content=text)}}
    if tags is not None:
        event["tags"] = tags
    return event


class _FakeAstreamGraph:
    """`attempts[i]` is an async-generator function (no args) producing the
    events for the i-th `astream_events` call - lets a test script exactly
    what each attempt yields/raises."""

    def __init__(self, attempts: list) -> None:
        self.calls = 0
        self._attempts = attempts

    async def astream_events(self, initial_state, config=None, version="v2"):
        attempt = self._attempts[self.calls]
        self.calls += 1
        async for event in attempt():
            yield event


async def _raise_before_any_event():
    raise psycopg.OperationalError("consuming input failed: SSL SYSCALL error: EOF detected")
    yield  # pragma: no cover - unreachable, keeps this an async generator function


async def _yield_one_token():
    yield _token_event("hello")


async def _yield_token_then_raise():
    yield _token_event("hello")
    raise psycopg.OperationalError("consuming input failed: SSL SYSCALL error: EOF detected")


async def test_stream_retries_before_any_token_sent() -> None:
    graph = _FakeAstreamGraph([_raise_before_any_event, _yield_one_token])
    chunks = [c async for c in main_module._stream_chat(graph, {}, {}, "req-1", "run-1")]
    assert graph.calls == 2, "expected exactly one retry"
    assert any('"delta": "hello"' in c for c in chunks), "the retried attempt's token must still reach the client"
    assert not any(c.startswith("event: error") for c in chunks), "a successful retry must not also emit an error event"


async def test_stream_does_not_retry_after_a_token_was_sent() -> None:
    graph = _FakeAstreamGraph([_yield_token_then_raise])
    chunks = [c async for c in main_module._stream_chat(graph, {}, {}, "req-1", "run-1")]
    assert graph.calls == 1, "must not retry once partial content has already reached the client"
    assert any(c.startswith("event: error") for c in chunks), "the failure must still surface as an error event"


async def _yield_a_user_token_and_an_internal_token():
    yield _token_event("visible reply")
    yield _token_event("internal compaction summary text", tags=["zuno-internal"])


async def test_stream_filters_out_zuno_internal_tagged_tokens() -> None:
    """ADR-0215: app/graph/history.py's compaction call is a nested model
    invocation inside the same graph run astream_events observes - tagged
    "zuno-internal" (app/clients/model_router.py's `tags` param) so its
    own output never reaches the browser as a chat token, unlike the
    user-visible reason/draft call's own tokens."""
    graph = _FakeAstreamGraph([_yield_a_user_token_and_an_internal_token])
    chunks = [c async for c in main_module._stream_chat(graph, {}, {}, "req-1", "run-1")]
    assert any('"delta": "visible reply"' in c for c in chunks)
    assert not any("internal compaction summary text" in c for c in chunks)


TESTS = [
    test_ainvoke_retries_once_on_operational_error,
    test_ainvoke_does_not_retry_non_connection_errors,
    test_ainvoke_second_failure_still_raises,
    test_stream_retries_before_any_token_sent,
    test_stream_does_not_retry_after_a_token_was_sent,
    test_stream_filters_out_zuno_internal_tagged_tokens,
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
