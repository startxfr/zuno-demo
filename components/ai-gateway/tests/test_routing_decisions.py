"""ADR-0550 (WP-135) tests for app/routing_decisions.py: the short-TTL
Redis side-channel publishing the real per-request routing decision, and
fail-open behavior when Redis is unreachable or an entry is malformed -
same pattern as tests/test_semantic_cache.py. No live Redis needed.

Run from this directory:

    python3 tests/test_routing_decisions.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import routing_decisions  # noqa: E402

_DECISION = {
    "provider": "ovhcloud-gpt-oss-120b",
    "model": "gpt-oss-120b",
    "kind": "saas",
    "classification": "C1",
    "fallback_used": False,
    "fallback_from": None,
}


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)


class _BrokenRedis:
    async def set(self, *_a, **_k):
        raise ConnectionError("redis down")

    async def get(self, *_a, **_k):
        raise ConnectionError("redis down")


def test_set_then_get_round_trips() -> None:
    fake = _FakeRedis()

    async def run():
        with mock.patch.object(routing_decisions, "_redis_client", return_value=fake):
            await routing_decisions.set_routing_decision("req-1", _DECISION)
            result = await routing_decisions.get_routing_decision("req-1")
        assert result == _DECISION

    asyncio.run(run())


def test_get_returns_none_for_an_unknown_request_id() -> None:
    fake = _FakeRedis()

    async def run():
        with mock.patch.object(routing_decisions, "_redis_client", return_value=fake):
            result = await routing_decisions.get_routing_decision("never-published")
        assert result is None

    asyncio.run(run())


def test_get_returns_none_when_redis_is_unreachable() -> None:
    async def run():
        with mock.patch.object(routing_decisions, "_redis_client", return_value=_BrokenRedis()):
            result = await routing_decisions.get_routing_decision("req-1")
        assert result is None, "a Redis failure must be treated as absent, never an exception"

    asyncio.run(run())


def test_set_never_raises_when_redis_is_unreachable() -> None:
    """Publish failure must never affect the chat call already served -
    the whole point of this being a best-effort side-channel."""
    async def run():
        with mock.patch.object(routing_decisions, "_redis_client", return_value=_BrokenRedis()):
            await routing_decisions.set_routing_decision("req-1", _DECISION)  # must not raise

    asyncio.run(run())


def test_get_returns_none_when_entry_is_malformed_json() -> None:
    class _MalformedRedis:
        async def get(self, _key):
            return "not valid json {{{"

    async def run():
        with mock.patch.object(routing_decisions, "_redis_client", return_value=_MalformedRedis()):
            result = await routing_decisions.get_routing_decision("req-1")
        assert result is None

    asyncio.run(run())


def test_set_is_a_noop_for_an_empty_request_id() -> None:
    fake = _FakeRedis()

    async def run():
        with mock.patch.object(routing_decisions, "_redis_client", return_value=fake):
            await routing_decisions.set_routing_decision("", _DECISION)
        assert fake.store == {}

    asyncio.run(run())


def test_get_is_none_for_an_empty_request_id_without_touching_redis() -> None:
    async def run():
        with mock.patch.object(routing_decisions, "_redis_client", return_value=_BrokenRedis()):
            # A broken client would raise if get() were actually called -
            # an empty request_id must short-circuit before that happens.
            result = await routing_decisions.get_routing_decision("")
        assert result is None

    asyncio.run(run())


def test_key_is_namespaced_by_request_id() -> None:
    fake = _FakeRedis()

    async def run():
        with mock.patch.object(routing_decisions, "_redis_client", return_value=fake):
            await routing_decisions.set_routing_decision("req-a", _DECISION)
            await routing_decisions.set_routing_decision("req-b", {**_DECISION, "provider": "local"})
        assert json.loads(fake.store[routing_decisions._key("req-a")])["provider"] == "ovhcloud-gpt-oss-120b"
        assert json.loads(fake.store[routing_decisions._key("req-b")])["provider"] == "local"

    asyncio.run(run())


def test_missing_redis_addr_is_treated_as_unavailable_not_a_crash() -> None:
    saved = routing_decisions.REDIS_ADDR
    try:
        routing_decisions.REDIS_ADDR = ""

        async def run():
            await routing_decisions.set_routing_decision("req-1", _DECISION)  # must not raise
            result = await routing_decisions.get_routing_decision("req-1")
            assert result is None

        asyncio.run(run())
    finally:
        routing_decisions.REDIS_ADDR = saved


TESTS = [
    test_set_then_get_round_trips,
    test_get_returns_none_for_an_unknown_request_id,
    test_get_returns_none_when_redis_is_unreachable,
    test_set_never_raises_when_redis_is_unreachable,
    test_get_returns_none_when_entry_is_malformed_json,
    test_set_is_a_noop_for_an_empty_request_id,
    test_get_is_none_for_an_empty_request_id_without_touching_redis,
    test_key_is_namespaced_by_request_id,
    test_missing_redis_addr_is_treated_as_unavailable_not_a_crash,
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
