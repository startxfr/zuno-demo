"""Zuno Agent Runtime (ADR-0009, ADR-0018): shared stateful orchestration
service. This v0 build implements the Tekos workflow only - the other four
agents are access-gated placeholder tiles built by a parallel track and do
not have a runtime workflow yet. See README.md for the exact HTTP API
contract.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncIterator, Dict

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.auth import CallerIdentity, validate_token
from app.graph.build import tekos_graph
from app.schemas import ChatRequest, ChatResponse
from app.telemetry import init_telemetry

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("agent_runtime")

init_telemetry("agent-runtime")  # ADR-0029: traces/metrics to the shared OTel Collector

app = FastAPI(
    title="Zuno Agent Runtime",
    version="0.1.0",
    description=(
        "Shared LangGraph-based orchestration runtime (ADR-0009, ADR-0018). "
        "v0 implements the Tekos technical-consultant workflow."
    ),
)


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> Dict[str, str]:
    return {"status": "ready"}


REQUEST_ID_HEADER = "x-zuno-request-id"


def _request_id(request: Request) -> str:
    """ADR-0045 "preserve request correlation ... across the chain":
    agent-frontend normally mints this ID and agent-bff forwards it
    unchanged (see their own reqid packages); this runtime is usually the
    last hop, so it just needs to propagate whatever it received into its
    own logs and (for the streaming path) the "start" SSE event, minting
    one itself only if called directly (e.g. security_checks.py).
    """
    return request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())


def _initial_state(payload: ChatRequest, identity: CallerIdentity) -> Dict[str, Any]:
    # ADR-0033: user_sub in the request body is informational/correlation
    # only, never an authorization input - the graph state's "user_sub"
    # (and every downstream classification/tool-authorization decision) is
    # always derived from the validated token's own `sub` claim, never from
    # this JSON field. A mismatch is not a security failure (nothing here
    # was ever trusted from the body), just worth a log line since the BFF
    # is expected to send its own claims.Subject value (ADR-0032) and a
    # persistent mismatch would indicate a BFF bug, not an attack.
    if identity.sub != payload.user_sub:
        logger.warning(
            "informational user_sub did not match validated token sub (ignored): body=%s token=%s (session=%s)",
            payload.user_sub,
            identity.sub,
            payload.session_id,
        )
    return {
        "session_id": payload.session_id,
        "user_sub": identity.sub,
        "groups": identity.groups,
        "bearer_token": identity.token,
        "message": payload.message,
        "retrieved_docs": [],
        "tool_results": {},
        "errors": [],
    }


@app.post("/v1/agents/tekos/chat")
async def tekos_chat(
    payload: ChatRequest,
    request: Request,
    identity: CallerIdentity = Depends(validate_token),
):
    """Synchronous JSON response, or SSE token streaming when the caller
    sends `Accept: text/event-stream`.
    """
    accept = request.headers.get("accept", "")
    initial_state = _initial_state(payload, identity)
    request_id = _request_id(request)

    if "text/event-stream" in accept:
        return StreamingResponse(
            _stream_chat(initial_state, request_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                REQUEST_ID_HEADER: request_id,
            },
        )

    try:
        final_state = await tekos_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.error("graph execution failed for session=%s request_id=%s: %s", payload.session_id, request_id, exc)
        raise HTTPException(status_code=500, detail=f"agent workflow failed: {exc}") from exc

    return ChatResponse(
        reply=final_state.get("reply", ""),
        citations=final_state.get("citations", []),
    )


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# Node names that trigger a `tool` SSE event (ADR-0045 "tool status
# events"), mapped to the human-facing tool name the frontend should show
# (e.g. "Using search_confluence…"). v0 has exactly one tool-calling node
# (app/graph/nodes.py:tool_call_node), which itself only ever calls
# search_confluence - see that function's own docstring. A second
# tool-calling node would add a second entry here.
_TOOL_NODES = {"tool_call": "search_confluence"}


async def _stream_chat(initial_state: Dict[str, Any], request_id: str) -> AsyncIterator[str]:
    """Streams token deltas from the `reason` node's underlying chat model
    via LangGraph's `astream_events` (v2), which surfaces
    `on_chat_model_stream` events for any model call nested inside a node
    -- no need to restructure the node itself for streaming to work. Also
    surfaces `tool` events (start/end of `_TOOL_NODES` entries) and a
    `start` event carrying request_id, per ADR-0045.
    """
    yield _sse("start", {"request_id": request_id})

    citations: Any = []
    try:
        async for event in tekos_graph.astream_events(initial_state, version="v2"):
            kind = event.get("event")
            name = event.get("name")
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                token = getattr(chunk, "content", "") if chunk is not None else ""
                if token:
                    yield _sse("token", {"delta": token})
            elif kind == "on_chain_start" and name in _TOOL_NODES:
                yield _sse("tool", {"name": _TOOL_NODES[name], "status": "started"})
            elif kind == "on_chain_end" and name in _TOOL_NODES:
                yield _sse("tool", {"name": _TOOL_NODES[name], "status": "finished"})
            elif kind == "on_chain_end" and name == "respond":
                output = event["data"].get("output") or {}
                citations = output.get("citations", [])
    except Exception as exc:
        logger.error("SSE stream failed request_id=%s: %s", request_id, exc)
        yield _sse("error", {"message": str(exc)})
        return

    yield _sse("done", {"citations": citations})
