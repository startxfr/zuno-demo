"""ADR-0550 (WP-135): a short-TTL Redis side-channel publishing the real
per-request routing decision (provider, model, classification, fallback)
so components/agent-runtime can fetch it once its own model call
completes and expose it to the frontend's routing-details panel.

Why a side-channel rather than a response field: `ChatCompletionResponse`
already carries `zuno_provider` (see schemas.py's own docstring), but
components/agent-runtime talks to this gateway via
`langchain_openai.ChatOpenAI`, which only parses the standard OpenAI
response schema - any extra top-level field is silently dropped before
agent-runtime ever sees it. The streaming SSE path (the one every real
chat turn actually uses) has no equivalent field at all. This is the
same structural gap ADR-0536's live verification had to work around by
reading OTel spans instead of the response itself.

Same graceful-degradation posture as semantic_cache.py, which this
module deliberately duplicates the small Redis-client-construction logic
from rather than importing (independent lifecycles, same reasoning
model_routing_policy.py's own docstring gives for its own duplication):
Redis unavailable/unreachable degrades to "no routing decision available
for this request_id" - this is purely an observability feature (ADR-0550
decision 9), never a routing or security control, so its own failure
must never affect the chat call itself.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("ai_gateway.routing_decisions")

REDIS_ADDR = os.getenv("REDIS_ADDR", "")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
ROUTING_DECISION_TTL_SECONDS = int(os.getenv("ROUTING_DECISION_TTL_SECONDS", "120"))


class RoutingDecisionUnavailable(Exception):
    """Raised for any side-channel infrastructure problem (Redis
    unreachable, malformed entry, etc.) - callers must treat this as "no
    decision available", never as a request failure."""


def _redis_client():
    if not REDIS_ADDR:
        raise RoutingDecisionUnavailable("REDIS_ADDR is not configured")
    import redis.asyncio as redis

    host, _, port = REDIS_ADDR.partition(":")
    return redis.Redis(host=host, port=int(port or 6379), password=REDIS_PASSWORD or None, decode_responses=True)


def _key(request_id: str) -> str:
    return f"zuno:ai-gateway:routing-decision:{request_id}"


async def set_routing_decision(request_id: str, decision: Dict[str, Any]) -> None:
    """Best-effort publish - never raises. Called from the success path of
    both _invoke_with_fallback and _stream_completion in app/main.py,
    after the fallback loop has already picked a candidate."""
    if not request_id:
        return
    try:
        client = _redis_client()
        await client.set(_key(request_id), json.dumps(decision), ex=ROUTING_DECISION_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 - publish failure must never affect the chat call already served
        logger.warning("routing-decision publish failed for request_id=%s: %s", request_id, exc)


async def get_routing_decision(request_id: str) -> Optional[Dict[str, Any]]:
    """Returns None (never raises) if Redis is unavailable, the entry
    expired/was never published, or is malformed - callers (agent-runtime)
    must degrade to their own placeholder routing metadata."""
    if not request_id:
        return None
    try:
        client = _redis_client()
        raw = await client.get(_key(request_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("routing-decision read failed for request_id=%s, treating as absent: %s", request_id, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        logger.warning("routing-decision entry for request_id=%s was not valid JSON: %s", request_id, exc)
        return None
