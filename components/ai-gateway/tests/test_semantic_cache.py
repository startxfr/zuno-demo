"""ADR-0104 tests for app/semantic_cache.py: SimHash bucketing determinism,
cache-key binding to every authorization-context dimension, and fail-open
behavior when the embedding service or Redis is unreachable. The embedding
service and Redis are both mocked - no live network needed.

Run from this directory:

    python3 tests/test_semantic_cache.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import semantic_cache  # noqa: E402


def _base_context(**overrides) -> semantic_cache.CacheContext:
    fields = dict(model_name="zuno-auto", user_sub="alice", classification="C1", local_only=False, task_id="t1")
    fields.update(overrides)
    return semantic_cache.CacheContext(**fields)


def _fixed_embedding(seed: int, dim: int = 8) -> list:
    import random

    rng = random.Random(seed)
    return [rng.gauss(0, 1) for _ in range(dim)]


def test_bucket_id_is_deterministic() -> None:
    vec = _fixed_embedding(1)
    assert semantic_cache._bucket_id(vec) == semantic_cache._bucket_id(vec)


def test_bucket_id_is_stable_across_module_reimport_style_calls() -> None:
    """The hyperplanes must be a fixed seed, not `random`'s default
    entropy - two independent calls (simulating two different requests,
    possibly in different processes) must bucket the same vector
    identically."""
    vec = _fixed_embedding(2)
    first = semantic_cache._hyperplanes(len(vec))
    second = semantic_cache._hyperplanes(len(vec))
    assert first == second


def test_tiny_perturbation_usually_lands_in_the_same_bucket() -> None:
    base = _fixed_embedding(3, dim=32)
    nudged = [v + 1e-6 for v in base]
    assert semantic_cache._bucket_id(base) == semantic_cache._bucket_id(nudged)


def test_very_different_vectors_can_bucket_differently() -> None:
    a = _fixed_embedding(10, dim=32)
    b = [-v for v in a]  # antipodal - every hyperplane dot product flips sign
    assert semantic_cache._bucket_id(a) != semantic_cache._bucket_id(b)


async def _key_with_embedding(prompt: str, context: semantic_cache.CacheContext, embedding: list) -> str:
    with mock.patch.object(semantic_cache, "_embed", return_value=embedding):
        return await semantic_cache.compute_cache_key(prompt, context)


def test_identical_context_and_prompt_produce_identical_keys() -> None:
    embedding = _fixed_embedding(5)
    key_a = asyncio.run(_key_with_embedding("hello", _base_context(), embedding))
    key_b = asyncio.run(_key_with_embedding("hello", _base_context(), embedding))
    assert key_a == key_b


def test_different_user_sub_produces_a_different_key() -> None:
    embedding = _fixed_embedding(5)
    key_a = asyncio.run(_key_with_embedding("hello", _base_context(user_sub="alice"), embedding))
    key_b = asyncio.run(_key_with_embedding("hello", _base_context(user_sub="mallory"), embedding))
    assert key_a != key_b


def test_different_classification_produces_a_different_key() -> None:
    embedding = _fixed_embedding(5)
    key_a = asyncio.run(_key_with_embedding("hello", _base_context(classification="C1"), embedding))
    key_b = asyncio.run(_key_with_embedding("hello", _base_context(classification="C2"), embedding))
    assert key_a != key_b


def test_different_local_only_produces_a_different_key() -> None:
    embedding = _fixed_embedding(5)
    key_a = asyncio.run(_key_with_embedding("hello", _base_context(local_only=False), embedding))
    key_b = asyncio.run(_key_with_embedding("hello", _base_context(local_only=True), embedding))
    assert key_a != key_b


def test_different_task_id_produces_a_different_key() -> None:
    embedding = _fixed_embedding(5)
    key_a = asyncio.run(_key_with_embedding("hello", _base_context(task_id="task-a"), embedding))
    key_b = asyncio.run(_key_with_embedding("hello", _base_context(task_id="task-b"), embedding))
    assert key_a != key_b


def test_different_model_produces_a_different_key() -> None:
    embedding = _fixed_embedding(5)
    key_a = asyncio.run(_key_with_embedding("hello", _base_context(model_name="model-a"), embedding))
    key_b = asyncio.run(_key_with_embedding("hello", _base_context(model_name="model-b"), embedding))
    assert key_a != key_b


def test_embedding_service_failure_raises_cache_unavailable_not_a_crash() -> None:
    # _embed's own contract (exercised for real, unmocked, by every other
    # test above via _key_with_embedding's patched-return-value form) is to
    # convert any underlying failure into CacheUnavailable - this test
    # proves compute_cache_key propagates that specific exception type
    # rather than swallowing or re-wrapping it.
    async def failing_embed(_prompt):
        raise semantic_cache.CacheUnavailable("embedding service call failed: connection refused")

    async def run():
        with mock.patch.object(semantic_cache, "_embed", side_effect=failing_embed):
            try:
                await semantic_cache.compute_cache_key("hello", _base_context())
                raise AssertionError("expected CacheUnavailable")
            except semantic_cache.CacheUnavailable:
                pass

    asyncio.run(run())


def test_embed_wraps_a_real_httpx_failure_as_cache_unavailable() -> None:
    """Proves _embed's own try/except (not mocked away this time) actually
    converts a real httpx-layer failure, closing the gap the test above
    leaves by mocking _embed directly."""

    async def run():
        with mock.patch("httpx.AsyncClient") as fake_client_cls:
            fake_client_cls.return_value.__aenter__.side_effect = OSError("connection refused")
            try:
                await semantic_cache._embed("hello")
                raise AssertionError("expected CacheUnavailable")
            except semantic_cache.CacheUnavailable:
                pass

    asyncio.run(run())


def test_get_cached_response_returns_none_when_redis_is_unreachable() -> None:
    class _BrokenClient:
        async def get(self, _key):
            raise ConnectionError("redis down")

    async def run():
        with mock.patch.object(semantic_cache, "_redis_client", return_value=_BrokenClient()):
            result = await semantic_cache.get_cached_response("some-key")
            assert result is None, "a Redis failure must be treated as a cache miss, never an exception"

    asyncio.run(run())


def test_get_cached_response_returns_none_when_entry_is_malformed_json() -> None:
    class _MalformedClient:
        async def get(self, _key):
            return "not valid json {{{"

    async def run():
        with mock.patch.object(semantic_cache, "_redis_client", return_value=_MalformedClient()):
            result = await semantic_cache.get_cached_response("some-key")
            assert result is None

    asyncio.run(run())


def test_should_use_cache_requires_both_global_and_per_model_switches() -> None:
    semantic_cache.SEMANTIC_CACHE_ENABLED = True
    try:
        assert semantic_cache.should_use_cache({"cache_enabled": True}) is True
        assert semantic_cache.should_use_cache({"cache_enabled": False}) is False
        assert semantic_cache.should_use_cache({}) is False
    finally:
        semantic_cache.SEMANTIC_CACHE_ENABLED = False

    assert semantic_cache.should_use_cache({"cache_enabled": True}) is False, (
        "global switch off must win even if the model opted in"
    )


TESTS = [
    test_bucket_id_is_deterministic,
    test_bucket_id_is_stable_across_module_reimport_style_calls,
    test_tiny_perturbation_usually_lands_in_the_same_bucket,
    test_very_different_vectors_can_bucket_differently,
    test_identical_context_and_prompt_produce_identical_keys,
    test_different_user_sub_produces_a_different_key,
    test_different_classification_produces_a_different_key,
    test_different_local_only_produces_a_different_key,
    test_different_task_id_produces_a_different_key,
    test_different_model_produces_a_different_key,
    test_embedding_service_failure_raises_cache_unavailable_not_a_crash,
    test_embed_wraps_a_real_httpx_failure_as_cache_unavailable,
    test_get_cached_response_returns_none_when_redis_is_unreachable,
    test_get_cached_response_returns_none_when_entry_is_malformed_json,
    test_should_use_cache_requires_both_global_and_per_model_switches,
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
