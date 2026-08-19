"""Zuno Agent Runtime (ADR-0009, ADR-0018): shared stateful orchestration
service. ADR-0342 (WP-30) generalized this from a single hardcoded Tekos
route to agent-name-driven dispatch resolved through `AgentRegistry` and
`GraphFactory` - Tekos remains the only `active` agent until WP-31 lands
Arkos as the second, but nothing here is hardcoded to Tekos by name
anymore. See README.md for the exact HTTP API contract.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.memory import MemorySaver

from app.auth import CallerIdentity, validate_token
from app.clients import project_memory_client
from app.graph.build import GraphFactory, validate_shapes
from app.graph.nodes import _model_router
from app.memory import MemoryExtractionError, extract_memory
from app.registry import AgentDefinition, AgentRegistry
from app.schemas import ChatRequest, ChatResponse
from app.telemetry import graph_run_span, init_telemetry

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("agent_runtime")

init_telemetry("agent-runtime")  # ADR-0029: traces/metrics to the shared OTel Collector

# ADR-0342 (WP-30): the generic dispatch route's own registry lookup - a
# second AgentRegistry instance from app/graph/nodes.py's (that one stays
# Tekos-coupled for now, see that module's own docstring); both read the
# same checked-in agents/ bundles, so a second idempotent load here is
# cheap and keeps this module's dispatch concern independent of nodes.py's
# internals. Fails fast at import time, same posture as nodes.py's own
# registry.
_registry = AgentRegistry()
if _registry.load_errors:
    raise RuntimeError(f"agent-runtime: failed to load OKF bundles: {_registry.load_errors}")


def _active_agent_or_404(agent: str) -> AgentDefinition:
    """Every route keyed on a path `{agent}` segment resolves through
    here: an unknown name or a `placeholder` agent (no runtime workflow
    exists for it, ADR-0007) both fail the same deterministic way, before
    GraphFactory is ever consulted."""
    agent_def = _registry.get(agent)
    if agent_def is None or agent_def.status != "active":
        raise HTTPException(status_code=404, detail=f"unknown agent '{agent}'")
    return agent_def


# ADR-0103: separate PG* variables (never a single combined DSN env var),
# same convention as components/mcp-servers/sales-db/server.py's
# _conninfo() - a hand-built "key=value" conninfo string never needs
# percent-encoding a generated password that might contain
# URI-special characters, unlike a postgresql:// URI would.
CHECKPOINT_PGHOST = os.getenv("CHECKPOINT_PGHOST", "")
CHECKPOINT_PGPORT = os.getenv("CHECKPOINT_PGPORT", "5432")
CHECKPOINT_PGDATABASE = os.getenv("CHECKPOINT_PGDATABASE", "")
CHECKPOINT_PGUSER = os.getenv("CHECKPOINT_PGUSER", "")
CHECKPOINT_PGPASSWORD = os.getenv("CHECKPOINT_PGPASSWORD", "")
# Incident 2026-08-14: omitting sslmode left psycopg on its libpq default
# (`prefer`), which retries a second, plaintext connection attempt after any
# TLS failure - PGO's PgBouncer rejects that plaintext attempt with
# "FATAL: SSL required", masking the real error (a missing database) behind
# a misleading one. Same convention as rag_ingestion.py's PGSSLMODE.
CHECKPOINT_PGSSLMODE = os.getenv("CHECKPOINT_PGSSLMODE", "require")


def _checkpoint_conninfo() -> Optional[str]:
    """None when unconfigured - the caller falls back to MemorySaver (the
    default for tests/local dev, per ADR-0103's explicit requirement)."""
    if not (CHECKPOINT_PGHOST and CHECKPOINT_PGDATABASE and CHECKPOINT_PGUSER and CHECKPOINT_PGPASSWORD):
        return None
    return (
        f"host={CHECKPOINT_PGHOST} port={CHECKPOINT_PGPORT} dbname={CHECKPOINT_PGDATABASE} "
        f"user={CHECKPOINT_PGUSER} password={CHECKPOINT_PGPASSWORD} sslmode={CHECKPOINT_PGSSLMODE}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """ADR-0103/ADR-0342: builds one `GraphFactory` at startup against
    either a persistent Postgres checkpointer (CHECKPOINT_PG* configured)
    or an in-memory one (default) - stored on `app.state`, not a
    module-level constant, since a Postgres-backed checkpointer needs a
    live async connection that can't be opened before the event loop
    exists. Fail-fast: every registered agent must resolve to a known
    graph shape before the app finishes starting (ADR-0342 Operational
    considerations) - this runs regardless of which checkpointer backend
    is selected.
    """
    validate_shapes(_registry.all())
    conninfo = _checkpoint_conninfo()
    if conninfo is None:
        logger.info("CHECKPOINT_PG* not fully configured - using in-memory checkpointing (not resumable across restarts)")
        app.state.graph_factory = GraphFactory(MemorySaver())
        yield
        return

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    # A connection POOL, not from_conn_string - VERIFIED live (2026-08-16):
    # from_conn_string opens ONE psycopg async connection shared by every
    # concurrent graph run, which fails with "another command is already in
    # progress" under any request concurrency and leaves the connection
    # permanently wedged (every subsequent chat 500s until pod restart).
    # kwargs mirror what from_conn_string sets internally (the saver
    # requires autocommit + dict_row; prepare_threshold=None avoids
    # server-side prepared statements, PgBouncer-safe if the host ever
    # changes back).
    async with AsyncConnectionPool(
        conninfo,
        min_size=1,
        max_size=int(os.getenv("CHECKPOINT_POOL_MAX_SIZE", "10")),
        kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": dict_row},
        # VERIFIED live 2026-08-19: after this cluster's Patroni failovers,
        # the pool's first-ever handout of a connection opened before the
        # failover surfaced "consuming input failed: SSL SYSCALL error: EOF
        # detected" straight to the caller (a 500/error SSE event) - the
        # pool already discards a bad connection on next use, just not
        # before handing it out once. check_connection runs a trivial probe
        # before checkout and swaps a dead connection for a fresh one first,
        # so callers never see a connection that was already broken.
        check=AsyncConnectionPool.check_connection,
    ) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()  # idempotent - creates the checkpoint tables on first run
        app.state.graph_factory = GraphFactory(checkpointer)
        logger.info("Postgres-backed checkpointing enabled at %s:%s/%s", CHECKPOINT_PGHOST, CHECKPOINT_PGPORT, CHECKPOINT_PGDATABASE)
        yield


app = FastAPI(
    title="Zuno Agent Runtime",
    version="0.1.0",
    description=(
        "Shared LangGraph-based orchestration runtime (ADR-0009, ADR-0018). "
        "v0 implements the Tekos technical-consultant workflow."
    ),
    lifespan=lifespan,
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


def _initial_state(payload: ChatRequest, identity: CallerIdentity, request_id: str) -> Dict[str, Any]:
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
        # ADR-0201 (WP-27): threaded to reason_node -> ModelRouter ->
        # ai-gateway -> (when routed via MaaS) the MaaS adapter, so a
        # model-call trace/usage record can be joined back to this exact
        # chat turn.
        "request_id": request_id,
        # ADR-0209/WP-28: forwarded as received - this runtime does not
        # itself validate project membership (rag-service does, fail
        # closed, at retrieval time).
        "project_id": payload.project_id,
        "retrieved_docs": [],
        "tool_results": {},
        "errors": [],
    }


async def _resolve_run_id(graph, payload: ChatRequest, identity: CallerIdentity) -> str:
    """ADR-0103: mints a new run_id when the caller isn't resuming anything,
    or validates a resume attempt against the checkpoint the run_id
    actually points at.

    Fail closed on resume: a run_id that doesn't resolve to any existing
    checkpoint is treated as a resume attempt against unknown/expired
    state (404) rather than silently starting a fresh run under the
    caller-supplied id - and a checkpoint whose stored `user_sub` differs
    from the validated caller's own subject is refused (403), regardless
    of what run_id.user_sub the checkpoint's *content* claims, this is
    exactly the re-enforced-authorization property ADR-0103's Decision
    text requires.
    """
    if payload.run_id is None:
        return str(uuid.uuid4())

    config = {"configurable": {"thread_id": payload.run_id}}
    tuple_ = await graph.checkpointer.aget_tuple(config)
    if tuple_ is None:
        raise HTTPException(status_code=404, detail=f"no workflow run found for run_id '{payload.run_id}'")

    stored_sub = (tuple_.checkpoint.get("channel_values") or {}).get("user_sub")
    if stored_sub != identity.sub:
        logger.warning(
            "refused to resume run_id=%s: checkpoint belongs to a different subject",
            payload.run_id,
        )
        raise HTTPException(status_code=403, detail="this workflow run belongs to a different user")

    return payload.run_id


async def _build_transcript(graph, run_id: str) -> str:
    """ADR-0209: reconstructs the full conversation for this run_id from
    every checkpoint LangGraph recorded for it (oldest first) -
    AgentState's message/reply channels hold only the latest turn each,
    not a running history, so a single checkpoint read (like
    _resolve_run_id's) would only ever see the last exchange."""
    config = {"configurable": {"thread_id": run_id}}
    turns = []
    async for checkpoint_tuple in graph.checkpointer.alist(config):
        channel_values = checkpoint_tuple.checkpoint.get("channel_values") or {}
        message = channel_values.get("message")
        reply = channel_values.get("reply")
        if message:
            turns.append(f"User: {message}")
        if reply:
            turns.append(f"Assistant: {reply}")
    turns.reverse()  # alist() yields newest-first
    return "\n".join(turns)


@app.post("/v1/agents/{agent}/runs/{run_id}/extract-memory")
async def extract_memory_endpoint(
    agent: str,
    run_id: str,
    request: Request,
    identity: CallerIdentity = Depends(validate_token),
) -> Dict[str, Any]:
    """ADR-0209 (WP-28), generalized per ADR-0342 (WP-30): the explicit
    extraction step - session end or an explicit checkpoint, never
    automatic per-turn. Reuses _resolve_run_id's ownership check (404
    unknown run, 403 wrong subject) since this endpoint reads the exact
    same checkpoint state, then requires the run to actually carry a
    project_id (a run with none has nothing to extract INTO -
    knowledge.project is per-project, not a default bucket).
    """
    agent_def = _active_agent_or_404(agent)
    graph = request.app.state.graph_factory.graph_for(agent_def)
    config = {"configurable": {"thread_id": run_id}}
    tuple_ = await graph.checkpointer.aget_tuple(config)
    if tuple_ is None:
        raise HTTPException(status_code=404, detail=f"no workflow run found for run_id '{run_id}'")

    channel_values = tuple_.checkpoint.get("channel_values") or {}
    stored_sub = channel_values.get("user_sub")
    if stored_sub != identity.sub:
        logger.warning("refused to extract memory for run_id=%s: belongs to a different subject", run_id)
        raise HTTPException(status_code=403, detail="this workflow run belongs to a different user")

    project_id = channel_values.get("project_id")
    if not project_id:
        raise HTTPException(
            status_code=400, detail="this run has no project_id - nothing to extract memory into"
        )

    transcript = await _build_transcript(graph, run_id)
    if not transcript.strip():
        return {"facts_written": 0, "memories_written": 0, "note": "empty transcript, nothing to extract"}

    # ADR-0034: the highest classification reached across this run's
    # turns, monotonically escalated by _escalate - never re-derived or
    # downgraded here. Falls back to this agent's own OKF-declared
    # baseline (not a Tekos-specific constant) if the checkpoint somehow
    # never recorded one.
    classification = channel_values.get("effective_classification", agent_def.preferred_classification)

    try:
        facts, memories = await extract_memory(
            model_router=_model_router,
            transcript=transcript,
            classification=classification,
            bearer_token=identity.token,
        )
    except MemoryExtractionError as exc:
        # ADR-0209 Operational considerations: logged, not silently
        # treated as "nothing worth remembering" - surfaced as a 502 so
        # the caller can retry rather than assume success.
        logger.error("memory extraction failed for run_id=%s project_id=%s: %s", run_id, project_id, exc)
        raise HTTPException(status_code=502, detail=f"memory extraction failed: {exc}") from exc

    if not facts and not memories:
        return {"facts_written": 0, "memories_written": 0, "note": "nothing durable identified"}

    try:
        result = await project_memory_client.write_project_memory(
            project_id=project_id,
            caller_sub=identity.sub,
            caller_groups=identity.groups,
            agent=agent_def.name,
            session_id=channel_values.get("session_id"),
            classification=classification,
            facts=facts,
            memories=memories,
        )
    except project_memory_client.ProjectMembershipDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except project_memory_client.ProjectMemoryClientError as exc:
        logger.error("project-memory write failed for run_id=%s project_id=%s: %s", run_id, project_id, exc)
        raise HTTPException(status_code=502, detail=f"project-memory write failed: {exc}") from exc

    return result


async def _ainvoke_with_retry(graph, initial_state: Dict[str, Any], config: Dict[str, Any], *, session_id: str, request_id: str):
    """One bounded retry for a checkpoint DB connection that was already
    dead at the moment of use (psycopg.OperationalError) - lifespan's
    `check=` callback is the primary defense (catches this before a
    connection is ever handed out), this covers a connection that dies
    mid-operation after passing that check. Any other exception (a real
    application bug) propagates immediately, unretried - retrying
    something that isn't a connection failure would just double the
    latency/LLM cost for a call guaranteed to fail again identically."""
    try:
        return await graph.ainvoke(initial_state, config=config)
    except psycopg.OperationalError as exc:
        logger.warning(
            "checkpoint DB connection failed, retrying once: session=%s request_id=%s: %s",
            session_id, request_id, exc,
        )
        return await graph.ainvoke(initial_state, config=config)


@app.post("/v1/agents/{agent}/chat")
async def agent_chat(
    agent: str,
    payload: ChatRequest,
    request: Request,
    identity: CallerIdentity = Depends(validate_token),
):
    """Synchronous JSON response, or SSE token streaming when the caller
    sends `Accept: text/event-stream`. ADR-0342 (WP-30): `{agent}` is
    resolved through `AgentRegistry`/`GraphFactory` - no per-agent
    hardcoded route or graph. Tekos's own chat path keeps working
    unchanged (agent-bff already calls this exact generic pattern with its
    own configured `AGENT_NAME`, per components/agent-bff/internal/
    runtime/client.go) - only the server-side dispatch generalized.
    """
    agent_def = _active_agent_or_404(agent)
    graph = request.app.state.graph_factory.graph_for(agent_def)
    accept = request.headers.get("accept", "")
    request_id = _request_id(request)
    initial_state = _initial_state(payload, identity, request_id)
    run_id = await _resolve_run_id(graph, payload, identity)
    config = {"configurable": {"thread_id": run_id}}

    if "text/event-stream" in accept:
        return StreamingResponse(
            _stream_chat(graph, initial_state, config, request_id, run_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                REQUEST_ID_HEADER: request_id,
            },
        )

    try:
        with graph_run_span(payload.session_id, agent=agent_def.name, graph_shape=agent_def.graph_shape) as recorder:
            final_state = await _ainvoke_with_retry(
                graph, initial_state, config, session_id=payload.session_id, request_id=request_id,
            )
            recorder.source_mode = final_state.get("source_mode", "none")
            recorder.live_read_trigger_reason = final_state.get("live_read_trigger_reason")
    except Exception as exc:
        logger.error("graph execution failed for session=%s request_id=%s: %s", payload.session_id, request_id, exc)
        raise HTTPException(status_code=500, detail=f"agent workflow failed: {exc}") from exc

    return ChatResponse(
        reply=final_state.get("reply", ""),
        citations=final_state.get("citations", []),
        run_id=run_id,
        source_mode=final_state.get("source_mode", "indexed"),
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


async def _stream_chat(
    graph, initial_state: Dict[str, Any], config: Dict[str, Any], request_id: str, run_id: str
) -> AsyncIterator[str]:
    """Streams token deltas from the `reason` node's underlying chat model
    via LangGraph's `astream_events` (v2), which surfaces
    `on_chat_model_stream` events for any model call nested inside a node
    -- no need to restructure the node itself for streaming to work. Also
    surfaces `tool` events (start/end of `_TOOL_NODES` entries) and a
    `start` event carrying request_id and run_id (ADR-0045, ADR-0103) -
    the frontend needs run_id to resume this exact workflow later.
    """
    yield _sse("start", {"request_id": request_id, "run_id": run_id})

    citations: Any = []
    source_mode = "indexed"
    # One bounded retry, same rationale as _ainvoke_with_retry, but only
    # safe to take before any token has reached the client (ADR-0029-style
    # precedent: components/ai-gateway/app/main.py's _stream_completion
    # never silently retries a candidate that already streamed partial
    # content, since the client has content a fresh run wouldn't continue
    # coherently) - sent_any tracks that boundary.
    sent_any = False
    attempts_remaining = 2
    while attempts_remaining:
        attempts_remaining -= 1
        try:
            async for event in graph.astream_events(initial_state, config=config, version="v2"):
                kind = event.get("event")
                name = event.get("name")
                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    token = getattr(chunk, "content", "") if chunk is not None else ""
                    if token:
                        sent_any = True
                        yield _sse("token", {"delta": token})
                elif kind == "on_chain_start" and name in _TOOL_NODES:
                    yield _sse("tool", {"name": _TOOL_NODES[name], "status": "started"})
                elif kind == "on_chain_end" and name in _TOOL_NODES:
                    yield _sse("tool", {"name": _TOOL_NODES[name], "status": "finished"})
                elif kind == "on_chain_end" and name == "respond":
                    output = event["data"].get("output") or {}
                    citations = output.get("citations", [])
                    # ADR-0205/WP-24: same field the non-streaming response
                    # carries - the streaming path must not silently omit it.
                    source_mode = output.get("source_mode", "indexed")
        except psycopg.OperationalError as exc:
            if sent_any or attempts_remaining == 0:
                logger.error("SSE stream failed request_id=%s: %s", request_id, exc)
                yield _sse("error", {"message": str(exc)})
                return
            logger.warning(
                "checkpoint DB connection failed before any token sent, retrying once: request_id=%s: %s",
                request_id, exc,
            )
            continue
        except Exception as exc:
            logger.error("SSE stream failed request_id=%s: %s", request_id, exc)
            yield _sse("error", {"message": str(exc)})
            return
        else:
            break

    yield _sse("done", {"citations": citations, "source_mode": source_mode})
