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

from app.auth import CallerIdentity, validate_token
from app.providers import chat_model_for
from app.routing import ProviderCandidate, RoutingError, RoutingTable
from app.schemas import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatMessage,
)
from app.telemetry import init_telemetry, model_call_span

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
    """Operational escape hatch: re-reads provider-routing.yaml from disk
    without a pod restart (mirrors mcp-gateway's /admin/reload-policy).
    """
    routing_table.reload()
    return {"loaded": routing_table.loaded}


def _to_langchain_messages(messages: List[ChatMessage]) -> List[Any]:
    return [_ROLE_TO_MESSAGE[m.role](content=m.content) for m in messages]


@app.post("/v1/chat/completions")
async def chat_completions(
    payload: ChatCompletionRequest,
    identity: CallerIdentity = Depends(validate_token),
    x_zuno_data_classification: str = Header(default="C1", alias="X-Zuno-Data-Classification"),
):
    classification = x_zuno_data_classification.upper()
    try:
        candidates = routing_table.candidates_for(classification)
    except RoutingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    messages = _to_langchain_messages(payload.messages)

    if payload.stream:
        return StreamingResponse(
            _stream_completion(candidates, classification, messages),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return await _invoke_with_fallback(candidates, classification, messages, caller_sub=identity.sub)


async def _invoke_with_fallback(
    candidates: List[ProviderCandidate], classification: str, messages: List[Any], caller_sub: str
) -> ChatCompletionResponse:
    errors: List[str] = []
    for candidate in candidates:
        cfg = routing_table.provider_config(candidate.name)
        model_name = cfg.get("model", candidate.name)
        try:
            with model_call_span(candidate.name, model_name, classification) as call:
                model = chat_model_for(candidate, cfg)
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
        return ChatCompletionResponse(
            model=model_name,
            choices=[ChatCompletionChoice(message=ChatMessage(role="assistant", content=content))],
            usage=ChatCompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            zuno_provider=candidate.name,
        )

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
    candidates: List[ProviderCandidate], classification: str, messages: List[Any]
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
        sent_any = False
        try:
            with model_call_span(candidate.name, model_name, classification):
                model = chat_model_for(candidate, cfg)
                async for event in model.astream(messages):
                    token = getattr(event, "content", "") or ""
                    if token:
                        sent_any = True
                        yield _sse_chunk(completion_id, created, model_name, {"content": token})
        except Exception as exc:
            logger.warning("provider '%s' failed mid-stream-setup: %s", candidate.name, exc)
            errors.append(f"{candidate.name}: {exc}")
            if sent_any:
                yield _sse_chunk(completion_id, created, model_name, {}, finish_reason="error")
                yield "data: [DONE]\n\n"
                return
            continue

        yield _sse_chunk(completion_id, created, model_name, {}, finish_reason="stop")
        yield "data: [DONE]\n\n"
        return

    logger.error("all eligible providers failed for classification %s: %s", classification, "; ".join(errors))
    yield _sse_chunk(completion_id, created, "none", {}, finish_reason="error")
    yield "data: [DONE]\n\n"
