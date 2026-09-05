"""ADR-0550 (WP-135) integration tests: app.main._invoke_with_fallback and
_stream_completion actually publish a routing decision via
app.routing_decisions - the real wiring, not just routing_decisions.py's
own unit tests. Same fake-model/mocked-provider_config pattern as
tests/test_cache_integration.py and tests/test_stream_telemetry.py; no
live network or Redis needed (routing_decisions.set_routing_decision
itself is spied on directly).

Run from this directory:

    python3 tests/test_routing_decision_publishing.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import AIMessageChunk  # noqa: E402

from fastapi import HTTPException  # noqa: E402

from app import main as app_main  # noqa: E402
from app import routing_decisions  # noqa: E402
from app.auth import CallerIdentity  # noqa: E402
from app.routing import ProviderCandidate  # noqa: E402
from app.schemas import ChatMessage  # noqa: E402

_IDENTITY = CallerIdentity(sub="alice", groups=["consultant"], raw_claims={}, token="t")


class _FakeModel:
    def __init__(self, reply: str = "an answer") -> None:
        self.reply = reply

    async def ainvoke(self, _messages):
        class _Result:
            content = self.reply
            usage_metadata = {"input_tokens": 3, "completion_tokens": 5}

        return _Result()


class _FailingModel:
    async def ainvoke(self, _messages):
        raise RuntimeError("provider unavailable")


class _FakeStreamingModel:
    def __init__(self, tokens=("hi",)) -> None:
        self._tokens = tokens

    async def astream(self, _messages):
        for tok in self._tokens:
            yield AIMessageChunk(content=tok)


def _spy_publish():
    calls = []

    async def fake_publish(request_id, decision):
        calls.append((request_id, decision))

    return calls, mock.patch.object(app_main.routing_decisions, "set_routing_decision", side_effect=fake_publish)


# --- _invoke_with_fallback -------------------------------------------------


def test_invoke_with_fallback_publishes_the_serving_candidate() -> None:
    calls, patch = _spy_publish()
    candidates = [ProviderCandidate(name="local-gpt-oss", kind="local")]
    with patch, mock.patch.object(app_main, "chat_model_for", return_value=_FakeModel()), mock.patch.object(
        app_main.routing_table, "provider_config", return_value={"model": "gpt-oss-20b"}
    ):
        asyncio.run(app_main._invoke_with_fallback(
            candidates, "C2", [], caller_sub="alice", local_only=True, task_id="draft-architecture-testimonial",
            requested_model="zuno-auto", raw_messages=[ChatMessage(role="user", content="hi")], request_id="req-1",
        ))
    assert len(calls) == 1
    request_id, decision = calls[0]
    assert request_id == "req-1"
    assert decision == {
        "provider": "local-gpt-oss", "model": "gpt-oss-20b", "kind": "local",
        "classification": "C2", "fallback_used": False, "fallback_from": None,
    }


def test_invoke_with_fallback_publishes_fallback_used_when_the_first_candidate_fails() -> None:
    calls, patch = _spy_publish()
    candidates = [
        ProviderCandidate(name="ovhcloud-gpt-oss-120b", kind="saas"),
        ProviderCandidate(name="local-gpt-oss", kind="local"),
    ]
    models = {"ovhcloud-gpt-oss-120b": _FailingModel(), "local-gpt-oss": _FakeModel()}
    with patch, mock.patch.object(
        app_main, "chat_model_for", side_effect=lambda candidate, *_a, **_k: models[candidate.name]
    ), mock.patch.object(app_main.routing_table, "provider_config", return_value={"model": "gpt-oss-20b"}):
        asyncio.run(app_main._invoke_with_fallback(
            candidates, "C1", [], caller_sub="alice", local_only=False, task_id="draft-architecture-testimonial",
            requested_model="zuno-auto", raw_messages=[ChatMessage(role="user", content="hi")], request_id="req-2",
        ))
    assert len(calls) == 1
    _, decision = calls[0]
    assert decision["provider"] == "local-gpt-oss"
    assert decision["fallback_used"] is True
    assert decision["fallback_from"] == "ovhcloud-gpt-oss-120b"


def test_invoke_with_fallback_cache_hit_still_publishes_a_decision() -> None:
    """A cache hit skips the fallback loop entirely - the separate
    publish call on that branch (app/main.py) must still fire, using the
    ORIGINAL call's own provider/model, not stale data from a different
    request_id."""
    from app import semantic_cache

    class _FakeRedis:
        def __init__(self):
            self._store = {}

        async def get(self, key):
            return self._store.get(key)

        async def set(self, key, value, ex=None):
            self._store[key] = value

    fake_redis = _FakeRedis()
    calls, publish_patch = _spy_publish()
    candidates = [ProviderCandidate(name="local-gpt-oss", kind="local")]
    semantic_cache.SEMANTIC_CACHE_ENABLED = True
    try:
        with publish_patch, mock.patch.object(
            app_main, "chat_model_for", return_value=_FakeModel()
        ), mock.patch.object(
            app_main.routing_table, "provider_config", return_value={"model": "gpt-oss-20b", "cache_enabled": True, "kind": "local"}
        ), mock.patch.object(
            semantic_cache, "_redis_client", return_value=fake_redis
        ), mock.patch.object(
            semantic_cache, "_embed", return_value=[0.1, 0.2, 0.3]
        ):
            kwargs = dict(
                classification="C1", messages=[], caller_sub="alice", local_only=False,
                task_id="draft-architecture-testimonial", requested_model="zuno-auto",
                raw_messages=[ChatMessage(role="user", content="hi")], request_id="req-3",
            )
            asyncio.run(app_main._invoke_with_fallback(candidates, **kwargs))
            asyncio.run(app_main._invoke_with_fallback(candidates, **kwargs))
    finally:
        semantic_cache.SEMANTIC_CACHE_ENABLED = False
    assert len(calls) == 2, "both the original call and the cache-hit branch must publish a decision"
    _, second_decision = calls[1]
    assert second_decision["provider"] == "local-gpt-oss"
    assert second_decision["fallback_used"] is False


# --- _stream_completion -----------------------------------------------------


def test_stream_completion_publishes_the_serving_candidate() -> None:
    calls, patch = _spy_publish()
    candidates = [ProviderCandidate(name="ovhcloud-gpt-oss-120b", kind="saas")]
    with patch, mock.patch.object(
        app_main, "chat_model_for", return_value=_FakeStreamingModel()
    ), mock.patch.object(app_main.routing_table, "provider_config", return_value={"model": "gpt-oss-120b"}):
        async def drain():
            async for _ in app_main._stream_completion(candidates, "C1", [], "req-4"):
                pass
        asyncio.run(drain())
    assert len(calls) == 1
    request_id, decision = calls[0]
    assert request_id == "req-4"
    assert decision["provider"] == "ovhcloud-gpt-oss-120b"
    assert decision["kind"] == "saas"
    assert decision["fallback_used"] is False


def test_stream_completion_publishes_fallback_used_when_the_first_candidate_fails_before_any_token() -> None:
    calls, patch = _spy_publish()
    candidates = [
        ProviderCandidate(name="ovhcloud-gpt-oss-120b", kind="saas"),
        ProviderCandidate(name="local-gpt-oss", kind="local"),
    ]

    class _RaisesImmediately:
        async def astream(self, _messages):
            raise RuntimeError("provider unavailable")
            yield  # pragma: no cover - unreachable, makes this an async generator

    models = {"ovhcloud-gpt-oss-120b": _RaisesImmediately(), "local-gpt-oss": _FakeStreamingModel()}
    with patch, mock.patch.object(
        app_main, "chat_model_for", side_effect=lambda candidate, *_a, **_k: models[candidate.name]
    ), mock.patch.object(app_main.routing_table, "provider_config", return_value={"model": "gpt-oss-20b"}):
        async def drain():
            async for _ in app_main._stream_completion(candidates, "C2", [], "req-5"):
                pass
        asyncio.run(drain())
    assert len(calls) == 1
    _, decision = calls[0]
    assert decision["provider"] == "local-gpt-oss"
    assert decision["fallback_used"] is True
    assert decision["fallback_from"] == "ovhcloud-gpt-oss-120b"


def test_stream_completion_does_not_publish_when_every_candidate_fails() -> None:
    """No successful candidate means no routing decision was ever made -
    publishing a decision here would describe a request that failed, not
    one that was routed."""
    calls, patch = _spy_publish()
    candidates = [ProviderCandidate(name="local-gpt-oss", kind="local")]

    class _AlwaysFails:
        async def astream(self, _messages):
            raise RuntimeError("provider unavailable")
            yield  # pragma: no cover

    with patch, mock.patch.object(
        app_main, "chat_model_for", return_value=_AlwaysFails()
    ), mock.patch.object(app_main.routing_table, "provider_config", return_value={"model": "gpt-oss-20b"}):
        async def drain():
            async for _ in app_main._stream_completion(candidates, "C1", [], "req-6"):
                pass
        asyncio.run(drain())
    assert calls == []


# --- GET /v1/routing-decisions/{request_id} --------------------------------


def test_get_routing_decision_endpoint_returns_a_published_decision() -> None:
    decision = {
        "provider": "local-gpt-oss", "model": "gpt-oss-20b", "kind": "local",
        "classification": "C2", "fallback_used": False, "fallback_from": None,
    }
    with mock.patch.object(routing_decisions, "get_routing_decision", return_value=decision):
        result = asyncio.run(app_main.get_routing_decision("req-7", identity=_IDENTITY))
    assert result.provider == "local-gpt-oss"
    assert result.fallback_used is False


def test_get_routing_decision_endpoint_404s_when_absent() -> None:
    with mock.patch.object(routing_decisions, "get_routing_decision", return_value=None):
        try:
            asyncio.run(app_main.get_routing_decision("never-published", identity=_IDENTITY))
            raise AssertionError("expected an HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 404


TESTS = [
    test_get_routing_decision_endpoint_returns_a_published_decision,
    test_get_routing_decision_endpoint_404s_when_absent,
    test_invoke_with_fallback_publishes_the_serving_candidate,
    test_invoke_with_fallback_publishes_fallback_used_when_the_first_candidate_fails,
    test_invoke_with_fallback_cache_hit_still_publishes_a_decision,
    test_stream_completion_publishes_the_serving_candidate,
    test_stream_completion_publishes_fallback_used_when_the_first_candidate_fails_before_any_token,
    test_stream_completion_does_not_publish_when_every_candidate_fails,
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
