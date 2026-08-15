"""Zuno AI Inference Gateway (ADR-0009, ADR-0020, ADR-0021).

OpenAI-compatible `POST /v1/chat/completions`: resolves the eligible
provider fallback chain for the caller-declared `X-Zuno-Data-Classification`
header, then either invokes (non-streaming) or streams (`stream: true`)
the first provider that succeeds. See README.md for the exact HTTP API
contract, and docs/adr/0009-*.md for why this exists as a service separate
from components/agent-runtime.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app import semantic_cache
from app.auth import CallerIdentity, validate_token
from app.model_routing_policy import AdapterDeclaration, ModelRoutingPolicy
from app.providers import chat_model_for
from app.routing import ProviderCandidate, RoutingError, RoutingTable
from app.schemas import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatMessage,
)
from app.telemetry import init_telemetry, model_call_span, record_cache_outcome

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ai_gateway")

init_telemetry("ai-gateway")  # ADR-0029: traces/metrics to the shared OTel Collector

app = FastAPI(
    title="Zuno AI Inference Gateway",
    version="0.1.0",
    description=(
        "OpenAI-compatible inference routing, classification-eligibility "
        "and provider fallback (ADR-0009, ADR-0020, ADR-0021)."
    ),
)

routing_table = RoutingTable()
model_routing_policy = ModelRoutingPolicy()  # ADR-0303 (WP-39)

_ROLE_TO_MESSAGE = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    if routing_table.loaded:
        return JSONResponse({"status": "ready"})
    return JSONResponse(
        {"status": "not-ready", "reason": "provider routing config not loaded"}, status_code=503
    )


@app.post("/admin/reload-routing")
async def reload_routing() -> Dict[str, Any]:
    """Operational escape hatch: re-reads provider-routing.yaml and
    policies/model-routing/model-routing-policy.yaml from disk without a
    pod restart (mirrors mcp-gateway's /admin/reload-policy).
    """
    routing_table.reload()
    model_routing_policy.reload()
    return {"loaded": routing_table.loaded}


def _to_langchain_messages(messages: List[ChatMessage]) -> List[Any]:
    return [_ROLE_TO_MESSAGE[m.role](content=m.content) for m in messages]


@app.post("/v1/chat/completions")
async def chat_completions(
    payload: ChatCompletionRequest,
    identity: CallerIdentity = Depends(validate_token),
    x_zuno_data_classification: str = Header(default="C1", alias="X-Zuno-Data-Classification"),
    x_zuno_local_only: str = Header(default="false", alias="X-Zuno-Local-Only"),
    # ADR-0104: optional, degrades safely to "" (the cache key still binds
    # to it, so this can never widen a hit across tasks). ADR-0303
    # (WP-39): as of components/agent-runtime/app/clients/model_router.py,
    # every real caller now sends this alongside X-Zuno-Agent below -
    # together they're the (agent, task) key model_routing_policy.py
    # resolves an adapter declaration from.
    x_zuno_task: str = Header(default="", alias="X-Zuno-Task"),
    # ADR-0303 (WP-39): optional, degrades safely to "" - a caller that
    # never sends it simply never resolves to a declared adapter (falls
    # back to the base model, the same fail-closed-to-safe default as an
    # unresolved X-Zuno-Task).
    x_zuno_agent: str = Header(default="", alias="X-Zuno-Agent"),
    # ADR-0201 (WP-27) usage correlation: the same request id agent-runtime
    # mints per chat turn (components/agent-runtime/app/main.py's
    # _request_id) and forwards via ModelRouter - optional, so this
    # endpoint stays callable by anything that doesn't send it yet; a
    # fresh id is minted here rather than left blank, so every model_call
    # span still carries a stable id even for a caller that never sends
    # one (never blank, always joinable to something).
    x_zuno_request_id: str = Header(default="", alias="X-Zuno-Request-Id"),
):
    classification = x_zuno_data_classification.upper()
    local_only = x_zuno_local_only.strip().lower() == "true"
    request_id = x_zuno_request_id.strip() or str(uuid.uuid4())
    try:
        candidates = routing_table.candidates_for(classification, local_only=local_only)
    except RoutingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ADR-0303 (WP-39): resolved once, from the classification-eligible
    # candidate list's own request context - never itself widens or
    # narrows `candidates`, only picks which model name a `local`
    # candidate uses once the fallback loop reaches it.
    adapter_decl = model_routing_policy.adapter_for(x_zuno_agent, x_zuno_task)

    messages = _to_langchain_messages(payload.messages)

    if payload.stream:
        return StreamingResponse(
            _stream_completion(candidates, classification, messages, request_id, adapter_decl),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return await _invoke_with_fallback(
        candidates,
        classification,
        messages,
        caller_sub=identity.sub,
        local_only=local_only,
        task_id=x_zuno_task,
        requested_model=payload.model,
        raw_messages=payload.messages,
        request_id=request_id,
        adapter_decl=adapter_decl,
    )


def _resolve_adapter(candidate: ProviderCandidate, adapter_decl: Optional[AdapterDeclaration]) -> Optional[str]:
    """None unless the candidate is local and a declaration exists for
    this request's (agent, task) - the same guard app/providers.py's
    chat_model_for() re-checks itself (ADR-0303/WP-39 defense in depth)."""
    if adapter_decl and candidate.kind == "local":
        return adapter_decl.adapter
    return None


async def _invoke_with_fallback(
    candidates: List[ProviderCandidate],
    classification: str,
    messages: List[Any],
    caller_sub: str,
    local_only: bool,
    task_id: str,
    requested_model: str,
    raw_messages: List[ChatMessage],
    request_id: str,
    adapter_decl: Optional[AdapterDeclaration] = None,
) -> ChatCompletionResponse:
    # ADR-0104: cache check happens strictly AFTER routing_table.candidates_for()
    # already ran in chat_completions() above - a cache hit can never bypass
    # an eligibility/policy denial, only ever short-circuit an already-authorized
    # call. Gated on the most-preferred candidate's config (per-model
    # enablement); the cache key itself binds to `requested_model`, not the
    # specific candidate, so this stays correct regardless of which
    # candidate ends up serving an uncached request.
    cache_key: Optional[str] = None
    if candidates and semantic_cache.should_use_cache(routing_table.provider_config(candidates[0].name)):
        prompt_text = "\n".join(f"{m.role}: {m.content}" for m in raw_messages)
        context = semantic_cache.CacheContext(
            model_name=requested_model,
            user_sub=caller_sub,
            classification=classification,
            local_only=local_only,
            task_id=task_id,
        )
        try:
            cache_key = await semantic_cache.compute_cache_key(prompt_text, context)
            cached = await semantic_cache.get_cached_response(cache_key)
        except semantic_cache.CacheUnavailable as exc:
            logger.warning("semantic cache unavailable, proceeding uncached: %s", exc)
            record_cache_outcome("unavailable", requested_model)
            cached = None
            cache_key = None
        else:
            record_cache_outcome("hit" if cached is not None else "miss", requested_model)
        if cached is not None:
            # `cached` carries only the CACHEABLE_FIELDS below - id/created
            # are freshly generated by ChatCompletionResponse's own
            # default_factory here, since a response's own id/timestamp
            # describing "when was this returned" should reflect this
            # call, not the original one that populated the cache entry.
            return ChatCompletionResponse(**cached)

    errors: List[str] = []
    for candidate in candidates:
        cfg = routing_table.provider_config(candidate.name)
        model_name = cfg.get("model", candidate.name)
        # ADR-0303 (WP-39): adapter_name is None unless this candidate is
        # local AND a declaration exists - effective_model_name is what
        # actually gets served/traced/returned, always the adapter's own
        # name when one applies.
        adapter_name = _resolve_adapter(candidate, adapter_decl)
        effective_model_name = adapter_name or model_name
        try:
            with model_call_span(candidate.name, effective_model_name, classification, request_id, adapter=adapter_name) as call:
                model = chat_model_for(candidate, cfg, request_id=request_id, adapter=adapter_name)
                result = await model.ainvoke(messages)
                usage = getattr(result, "usage_metadata", None) or {}
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)
                call.record_usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        except Exception as exc:
            logger.warning(
                "provider '%s' failed for caller=%s, trying next fallback: %s",
                candidate.name, caller_sub, exc,
            )
            errors.append(f"{candidate.name}: {exc}")
            continue

        content = result.content if hasattr(result, "content") else str(result)
        response = ChatCompletionResponse(
            model=effective_model_name,
            choices=[ChatCompletionChoice(message=ChatMessage(role="assistant", content=content))],
            usage=ChatCompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            zuno_provider=candidate.name,
        )
        if cache_key is not None:
            cacheable = response.model_dump(include={"model", "choices", "usage", "zuno_provider"})
            await semantic_cache.set_cached_response(cache_key, cacheable)
        return response

    raise HTTPException(
        status_code=502,
        detail=f"all eligible providers failed for classification {classification}: {'; '.join(errors)}",
    )


def _sse_chunk(completion_id: str, created: int, model_name: str, delta: Dict[str, str], finish_reason: Optional[str] = None) -> str:
    return "data: " + json.dumps(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
    ) + "\n\n"


async def _stream_completion(
    candidates: List[ProviderCandidate],
    classification: str,
    messages: List[Any],
    request_id: str,
    adapter_decl: Optional[AdapterDeclaration] = None,
) -> AsyncIterator[str]:
    """Streams the first candidate that produces at least one token. A
    candidate that fails *before* yielding any token falls back to the next
    one, same as the non-streaming path. A candidate that fails *after*
    already streaming tokens to the caller cannot be silently retried
    (the client has already received partial content that a different
    provider's answer wouldn't continue coherently) - that case ends the
    stream with an error chunk instead. This mirrors the fallback boundary
    the pre-refactor `ModelRouter.streaming_model_for()` docstring
    described but never actually wired up.
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    errors: List[str] = []

    for candidate in candidates:
        cfg = routing_table.provider_config(candidate.name)
        model_name = cfg.get("model", candidate.name)
        adapter_name = _resolve_adapter(candidate, adapter_decl)
        effective_model_name = adapter_name or model_name
        sent_any = False
        try:
            with model_call_span(candidate.name, effective_model_name, classification, request_id, adapter=adapter_name):
                model = chat_model_for(candidate, cfg, request_id=request_id, adapter=adapter_name)
                async for event in model.astream(messages):
                    token = getattr(event, "content", "") or ""
                    if token:
                        sent_any = True
                        yield _sse_chunk(completion_id, created, effective_model_name, {"content": token})
        except Exception as exc:
            logger.warning("provider '%s' failed mid-stream-setup: %s", candidate.name, exc)
            errors.append(f"{candidate.name}: {exc}")
            if sent_any:
                yield _sse_chunk(completion_id, created, effective_model_name, {}, finish_reason="error")
                yield "data: [DONE]\n\n"
                return
            continue

        yield _sse_chunk(completion_id, created, effective_model_name, {}, finish_reason="stop")
        yield "data: [DONE]\n\n"
        return

    logger.error("all eligible providers failed for classification %s: %s", classification, "; ".join(errors))
    yield _sse_chunk(completion_id, created, "none", {}, finish_reason="error")
    yield "data: [DONE]\n\n"
