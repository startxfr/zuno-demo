#!/usr/bin/env python3
"""ADR-0550 (WP-135) tests for app/clients/model_router.py's
fetch_routing_decision - the best-effort GET against ai-gateway's
routing-decisions side-channel. httpx.AsyncClient is faked the same way
tests/test_guardrails.py fakes it for guardrails_client's POST calls; no
live network needed.

Run directly:

    cd components/agent-runtime && python3 tests/test_model_router_routing_decision.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

from app.clients import model_router  # noqa: E402


class _FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeAsyncClient:
    last_call = None

    def __init__(self, response=None, exc=None, **kwargs):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None):
        _FakeAsyncClient.last_call = {"url": url, "headers": headers}
        if self._exc is not None:
            raise self._exc
        return self._response


def _run(coro):
    return asyncio.run(coro)


def test_fetch_returns_the_decision_on_success() -> None:
    decision = {
        "provider": "local-gpt-oss", "model": "gpt-oss-20b", "kind": "local",
        "classification": "C2", "fallback_used": False, "fallback_from": None,
    }
    factory = lambda **kw: _FakeAsyncClient(response=_FakeResponse(decision), **kw)  # noqa: E731
    with mock.patch.object(model_router.httpx, "AsyncClient", factory):
        result = _run(model_router.fetch_routing_decision("req-1", "bearer-token"))
    assert result == decision


def test_fetch_sends_the_bearer_token_and_correct_url() -> None:
    factory = lambda **kw: _FakeAsyncClient(response=_FakeResponse({"provider": "local"}), **kw)  # noqa: E731
    with mock.patch.object(model_router.httpx, "AsyncClient", factory):
        _run(model_router.fetch_routing_decision("req-42", "my-token"))
    call = _FakeAsyncClient.last_call
    assert call["url"] == f"{model_router.AI_GATEWAY_URL}/v1/routing-decisions/req-42"
    assert call["headers"] == {"Authorization": "Bearer my-token"}


def test_fetch_returns_none_on_404() -> None:
    factory = lambda **kw: _FakeAsyncClient(response=_FakeResponse(status_code=404), **kw)  # noqa: E731
    with mock.patch.object(model_router.httpx, "AsyncClient", factory):
        result = _run(model_router.fetch_routing_decision("req-2", "t"))
    assert result is None


def test_fetch_returns_none_when_the_gateway_is_unreachable() -> None:
    factory = lambda **kw: _FakeAsyncClient(exc=RuntimeError("connection refused"), **kw)  # noqa: E731
    with mock.patch.object(model_router.httpx, "AsyncClient", factory):
        result = _run(model_router.fetch_routing_decision("req-3", "t"))
    assert result is None, "a fetch failure must degrade to None, never raise"


def test_fetch_returns_none_on_a_5xx_status() -> None:
    factory = lambda **kw: _FakeAsyncClient(response=_FakeResponse(status_code=502), **kw)  # noqa: E731
    with mock.patch.object(model_router.httpx, "AsyncClient", factory):
        result = _run(model_router.fetch_routing_decision("req-4", "t"))
    assert result is None


def test_fetch_is_a_noop_for_an_empty_request_id() -> None:
    def _must_not_be_called(**_kw):
        raise AssertionError("must not construct an HTTP client for an empty request_id")

    with mock.patch.object(model_router.httpx, "AsyncClient", _must_not_be_called):
        result = _run(model_router.fetch_routing_decision("", "t"))
    assert result is None


def test_fetch_is_a_noop_for_a_none_request_id() -> None:
    def _must_not_be_called(**_kw):
        raise AssertionError("must not construct an HTTP client for a None request_id")

    with mock.patch.object(model_router.httpx, "AsyncClient", _must_not_be_called):
        result = _run(model_router.fetch_routing_decision(None, "t"))
    assert result is None


TESTS = [
    test_fetch_returns_the_decision_on_success,
    test_fetch_sends_the_bearer_token_and_correct_url,
    test_fetch_returns_none_on_404,
    test_fetch_returns_none_when_the_gateway_is_unreachable,
    test_fetch_returns_none_on_a_5xx_status,
    test_fetch_is_a_noop_for_an_empty_request_id,
    test_fetch_is_a_noop_for_a_none_request_id,
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
