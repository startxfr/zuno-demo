"""ADR-0104 controlled semantic cache: an opt-in Redis-backed cache for
non-streaming `/v1/chat/completions` responses, keyed so a cache entry can
only ever be served back to a request with an *identical* authorization
context - never across users, classifications, local-only requirements or
tasks.

"Semantic" here means bucketed by embedding similarity, not exact prompt
text: the prompt is embedded via the same shared embedding InferenceService
`components/rag-service` already calls
(`EMBEDDING_SERVICE_URL`, default `embeddings-predictor.zuno-ai-run.svc`),
then bucketed with a small, fixed set of random hyperplanes (SimHash-style
locality-sensitive hashing) - cosine-similar prompts land in the same
bucket with high probability, without needing a vector index. The
hyperplanes are deterministic (fixed seed), not re-randomized per process,
so the same prompt always buckets the same way across restarts - a moving
bucket boundary would silently and permanently disable cache hits after
every redeploy.

Fail-open on cache *infrastructure* problems (Redis or the embedding
service unreachable): caching is a latency/cost optimization, never a
correctness or security control, so its own failure must never block or
change the outcome of the actual model call - the request just proceeds
uncached, exactly as if the cache were disabled. This is deliberately
different from a policy/authorization failure, which must fail closed;
nothing here is ever in a position to reach that decision, since the
eligibility/classification check in app/routing.py always runs first, by
construction of the request-handling order in app/main.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_gateway.semantic_cache")

SEMANTIC_CACHE_ENABLED = os.getenv("SEMANTIC_CACHE_ENABLED", "false").strip().lower() == "true"
SEMANTIC_CACHE_TTL_SECONDS = int(os.getenv("SEMANTIC_CACHE_TTL_SECONDS", "3600"))
EMBEDDING_SERVICE_URL = os.getenv(
    "EMBEDDING_SERVICE_URL", "http://embeddings-predictor.zuno-ai-run.svc:8080/v1/embeddings"
)
REDIS_ADDR = os.getenv("REDIS_ADDR", "")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# Fixed, never randomized per process - see module docstring for why a
# moving bucket boundary would be a real bug, not a harmless variation.
_SIMHASH_SEED = 0x5A11_0104  # arbitrary constant, stable across restarts/deploys
_SIMHASH_BITS = 16


class CacheUnavailable(Exception):
    """Raised for any cache-infrastructure problem (embedding service or
    Redis unreachable, malformed response, etc.) - callers must treat this
    as a cache miss, never as a request failure."""


def should_use_cache(cfg: Dict[str, Any]) -> bool:
    """Two-gate rule, same pattern as app/maas_adapter.py's should_use_maas:
    the global chart switch AND this specific model's provider-routing.yaml
    entry must both opt in."""
    return SEMANTIC_CACHE_ENABLED and bool(cfg.get("cache_enabled", False))


@dataclass(frozen=True)
class CacheContext:
    """Every field the ADR-0104 Decision requires the cache key to bind to.
    Two requests produce the same key if and only if all of these match -
    the mechanism by which a cache hit can never cross a user,
    classification, local-only requirement or task boundary."""

    model_name: str
    user_sub: str
    classification: str
    local_only: bool
    task_id: str = ""


def _hyperplanes(dimension: int) -> List[List[float]]:
    """Deterministic pseudo-random hyperplanes for SimHash bucketing -
    seeded, not `random`'s default entropy, so the same dimension always
    yields the same hyperplanes (see module docstring)."""
    import random

    rng = random.Random(_SIMHASH_SEED)
    return [[rng.gauss(0, 1) for _ in range(dimension)] for _ in range(_SIMHASH_BITS)]


def _bucket_id(embedding: List[float]) -> str:
    planes = _hyperplanes(len(embedding))
    bits = 0
    for i, plane in enumerate(planes):
        dot = sum(e * p for e, p in zip(embedding, plane))
        if dot >= 0:
            bits |= 1 << i
    return format(bits, f"0{_SIMHASH_BITS}b")


async def _embed(prompt_text: str) -> List[float]:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(EMBEDDING_SERVICE_URL, json={"input": prompt_text})
            resp.raise_for_status()
            payload = resp.json()
        return payload["data"][0]["embedding"]
    except Exception as exc:  # noqa: BLE001 - any failure here is "cache unavailable"
        raise CacheUnavailable(f"embedding service call failed: {exc}") from exc


async def compute_cache_key(prompt_text: str, context: CacheContext) -> str:
    """Raises CacheUnavailable (never a request-affecting exception) if the
    embedding service can't be reached - callers must catch this and
    proceed without caching."""
    embedding = await _embed(prompt_text)
    bucket = _bucket_id(embedding)
    key_material = (
        f"{bucket}:{context.model_name}:{context.user_sub}:"
        f"{context.classification}:{context.local_only}:{context.task_id}"
    )
    digest = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
    return f"zuno:ai-gateway:semantic-cache:{digest}"


def _redis_client():
    if not REDIS_ADDR:
        raise CacheUnavailable("REDIS_ADDR is not configured")
    import redis.asyncio as redis

    host, _, port = REDIS_ADDR.partition(":")
    return redis.Redis(host=host, port=int(port or 6379), password=REDIS_PASSWORD or None, decode_responses=True)


async def get_cached_response(cache_key: str) -> Optional[Dict[str, Any]]:
    try:
        client = _redis_client()
        raw = await client.get(cache_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic cache read failed, treating as miss: %s", exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        logger.warning("semantic cache entry was not valid JSON, treating as miss: %s", exc)
        return None


async def set_cached_response(cache_key: str, response: Dict[str, Any]) -> None:
    try:
        client = _redis_client()
        await client.set(cache_key, json.dumps(response), ex=SEMANTIC_CACHE_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic cache write failed (response already served to the caller): %s", exc)
