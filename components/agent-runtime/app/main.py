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
import time
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.memory import MemorySaver

from app import conversations, project_binding, projects
from app.auth import CallerIdentity, validate_token
from app.clients import guardrails_client, project_memory_client
from app.graph import history as history_mod
from app.graph.build import GraphFactory, validate_shapes
from app.graph.classification import _escalate
from app.graph.nodes import _model_router
from app.memory import MemoryExtractionError, extract_memory
from app.registry import AgentDefinition, AgentRegistry
from app.schemas import (
    ChatRequest,
    ChatResponse,
    CreateProjectRequest,
    RenameConversationRequest,
    ReorderConversationsRequest,
    SaveProjectRequest,
)
from app.telemetry import api_request_span, graph_run_span, init_telemetry

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
# same convention as components/mcp-servers/confluence/server.py's
# _conninfo() - a hand-built "key=value" conninfo string never needs
# percent-encoding a generated password that might contain
# URI-special characters, unlike a postgresql:// URI would.
CHECKPOINT_PGHOST = os.getenv("CHECKPOINT_PGHOST", "")
CHECKPOINT_PGPORT = os.getenv("CHECKPOINT_PGPORT", "5432")
CHECKPOINT_PGDATABASE = os.getenv("CHECKPOINT_PGDATABASE", "")
CHECKPOINT_PGUSER = os.getenv("CHECKPOINT_PGUSER", "")
CHECKPOINT_PGPASSWORD = os.getenv("CHECKPOINT_PGPASSWORD", "")
# Omitting sslmode leaves psycopg on its libpq default (`prefer`), which
# retries a second, plaintext connection attempt after any TLS failure -
# PGO's PgBouncer rejects that plaintext attempt with "FATAL: SSL required",
# masking the real error (a missing database) behind a misleading one.
# Same convention as rag_ingestion.py's PGSSLMODE.
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

    ADR-0212 wraps this in `conversations.pool_context()`, a second and
    entirely independent Postgres pool for conversation metadata - never
    sharing a connection or credential with the checkpoint pool below.
    """
    validate_shapes(_registry.all())

    async with conversations.pool_context() as conversations_pool:
        app.state.conversations_pool = conversations_pool
        # ADR-0527 clause 8: re-push every live project's grant set to
        # rag-service, repairing any divergence left by the residual
        # window in projects.save_project (push succeeded, commit then
        # failed) or by a rag-service outage that outlasted a retry.
        # Deliberately non-fatal: a rag-service outage must not stop this
        # runtime from booting, and the projection is a DENY gate - a stale
        # one over-denies, which is the safe direction.
        await projects.reconcile_projections(conversations_pool)

        conninfo = _checkpoint_conninfo()
        if conninfo is None:
            logger.info("CHECKPOINT_PG* not fully configured - using in-memory checkpointing (not resumable across restarts)")
            app.state.graph_factory = GraphFactory(MemorySaver())
            yield
            return

        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        # A connection POOL, not from_conn_string: from_conn_string opens ONE
        # psycopg async connection shared by every concurrent graph run, which
        # fails with "another command is already in progress" under any
        # request concurrency and leaves the connection permanently wedged
        # (every subsequent chat 500s until pod restart). kwargs mirror what
        # from_conn_string sets internally (the saver
        # requires autocommit + dict_row; prepare_threshold=None avoids
        # server-side prepared statements, PgBouncer-safe if the host ever
        # changes back).
        async with AsyncConnectionPool(
            conninfo,
            min_size=1,
            max_size=int(os.getenv("CHECKPOINT_POOL_MAX_SIZE", "10")),
            kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": dict_row},
            # After a Patroni failover, the pool's first-ever handout of a
            # connection opened before the failover can surface "consuming
            # input failed: SSL SYSCALL error: EOF detected" straight to the
            # caller (a 500/error SSE event) - the pool already discards a bad
            # connection on next use, just not before handing it out once.
            # check_connection runs a trivial probe
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
        # ADR-0527: deliberately ABSENT. project_id used to be copied
        # straight from the request body here, which is exactly what made
        # ADR-0512 gate the X-Zuno-Project-Id header on the task's
        # project_required mark - a client could otherwise shift its
        # consumption onto an arbitrary project's quota. agent_chat now
        # resolves it from the conversation's own projects row after
        # verifying the caller holds a grant, and sets it on the state
        # itself. Removing this one line IS the "server-verified project"
        # guarantee ADR-0528 clause 4 relies on; do not restore it.
        "project_context": "",
        "project_classification": None,
        "retrieved_docs": [],
        "tool_results": {},
        "errors": [],
    }


async def _resolve_run_id(
    graph,
    payload: ChatRequest,
    identity: CallerIdentity,
    conversations_pool: Optional[Any] = None,
) -> str:
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

    ADR-0212 widens the ownership check from "must be the checkpoint's own
    stored subject" to "must be the conversations table's owner_sub",
    once conversation tracking is configured (conversations_pool is not
    None) and a row already exists for this run_id - a pre-ADR-0212
    run_id with no conversations row yet falls back to the original
    checkpoint-only check (additive, no backfill, per that ADR's
    Operational considerations). conversations_pool defaults to None so
    every existing call site/test keeps today's exact behavior unchanged.

    ADR-0527 widens it again, and moves the ACL from the conversation to
    the project: any effective role - the caller's own conversation, or any
    grant on its project - may resolve/resume a run_id. This is the
    *read/resume* gate only. agent_chat additionally requires `write` or
    `admin` before letting a resumed run_id accept a new message (see its
    own write-role check), so `read` and `clone` members reach the
    transcript and nothing more.
    """
    if payload.run_id is None:
        return str(uuid.uuid4())

    config = {"configurable": {"thread_id": payload.run_id}}
    tuple_ = await graph.checkpointer.aget_tuple(config)
    if tuple_ is None:
        raise HTTPException(status_code=404, detail=f"no workflow run found for run_id '{payload.run_id}'")

    stored_sub = (tuple_.checkpoint.get("channel_values") or {}).get("user_sub")
    if conversations_pool is not None:
        access = await conversations.resolve_access(
            conversations_pool,
            run_id=payload.run_id,
            subject=identity.sub,
            groups=identity.groups,
        )
        if access is not None:
            return payload.run_id
        # No effective role. Fall through to the checkpoint-only check
        # below, which still covers a pre-ADR-0212 run_id with no
        # conversations row - but only for its own original subject, so a
        # missing row can never become "no project restriction".
        owner_sub = await conversations.resolve_owner(conversations_pool, payload.run_id)
        if owner_sub is not None:
            stored_sub = owner_sub

    if stored_sub != identity.sub:
        logger.warning(
            "refused to resume run_id=%s: checkpoint belongs to a different subject",
            payload.run_id,
        )
        raise HTTPException(status_code=403, detail="this workflow run belongs to a different user")

    return payload.run_id


async def _build_transcript_structured(graph, run_id: str) -> List[Dict[str, Any]]:
    """ADR-0209/ADR-0212: reconstructs the full conversation for this
    run_id from every checkpoint LangGraph recorded for it, grouped by
    turn - AgentState's message/reply channels hold only the latest
    *value* each (plain LastValue channels), and LangGraph checkpoints
    after every graph super-step, not once per turn (a single Tekos turn
    walks retrieve -> [tool_call] -> reason -> respond, 3-4 super-steps,
    each producing its own checkpoint row). Naively emitting a line
    whenever message/reply is truthy - the pre-ADR-0212 approach -
    therefore repeated the same pair once per super-step: a real user
    reopening a conversation saw one question+answer duplicated 4-5x.

    `checkpoint.metadata["source"] == "input"` is LangGraph's own,
    persisted (unlike "writes", which is stripped before Postgres
    storage) marker for the first checkpoint of each turn, before that
    turn's graph execution has written anything - used here to group
    checkpoints into turns rather than treating each one as its own
    exchange.
    """
    config = {"configurable": {"thread_id": run_id}}
    checkpoints = [c async for c in graph.checkpointer.alist(config)]
    checkpoints.reverse()  # alist() yields newest-first

    turns: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    def _flush() -> None:
        if current is None:
            return
        if current["message"]:
            turns.append({"role": "user", "content": current["message"], "ts": current["ts"]})
        if current["reply"]:
            # ADR-0415: generated_images is a cumulative LastValue channel
            # (never reset between turns, like reply/history) - the slice
            # against images_before (captured at this turn's "input"
            # checkpoint, below) isolates just the images THIS turn added,
            # the same way this whole function isolates this turn's reply
            # from the growing checkpoint stream.
            new_images = current["images"][current["images_before"]:]
            entry = {"role": "assistant", "content": current["reply"], "ts": current["reply_ts"]}
            if new_images:
                entry["images"] = new_images
            turns.append(entry)

    for checkpoint_tuple in checkpoints:
        channel_values = checkpoint_tuple.checkpoint.get("channel_values") or {}
        if checkpoint_tuple.metadata.get("source") == "input":
            _flush()
            current = {
                "message": None,
                "ts": checkpoint_tuple.checkpoint.get("ts"),
                "reply": None,
                "reply_ts": None,
                "images": channel_values.get("generated_images") or [],
                "images_before": len(channel_values.get("generated_images") or []),
            }
            # The "input" checkpoint predates this turn's own graph
            # execution entirely - neither this turn's message nor its
            # reply are visible in
            # channel_values yet (message only becomes visible starting
            # at the *next* checkpoint, once the graph's first node
            # actually runs; reply is still whatever the *previous* turn
            # last wrote, LastValue channels never reset between turns).
            # Reading either field here would mispair stale/missing data
            # with this turn. Only ts is taken from this checkpoint.
            continue
        if current is not None:
            if current["message"] is None:
                current["message"] = channel_values.get("message") or ""
            reply = channel_values.get("reply")
            if reply:
                current["reply"] = reply
                current["reply_ts"] = checkpoint_tuple.checkpoint.get("ts")
            if "generated_images" in channel_values:
                current["images"] = channel_values["generated_images"]
    _flush()
    return turns


async def _seed_history_backfill(
    graph, run_id: str, is_resume: bool, initial_state: Dict[str, Any], agent_def: AgentDefinition
) -> None:
    """ADR-0215: a resumed run_id whose checkpoint predates conversation
    history tracking has no `history` channel yet (app/graph/state.py) -
    seed it once from the existing transcript reconstruction so the
    conversation regains context on its first post-upgrade turn, rather
    than silently starting over as if it were brand new. A fresh
    conversation (`is_resume` False) needs no backfill - there is nothing
    to reconstruct yet, and `record_history` will start populating
    `history` from this very turn. Never raises: a checkpoint-read failure
    here degrades to "start tracking history from now on", the same
    posture app/graph/history.py's own compaction failure takes - it must
    never turn into a failed chat turn.
    """
    if not is_resume:
        return
    try:
        tuple_ = await graph.checkpointer.aget_tuple({"configurable": {"thread_id": run_id}})
        channel_values = (tuple_.checkpoint.get("channel_values") if tuple_ else None) or {}
        if "history" in channel_values:
            return  # already tracking history - record_history owns it from here on
        transcript = await _build_transcript_structured(graph, run_id)
        history = history_mod.history_from_transcript(transcript)
        if history:
            initial_state["history"] = history
        stored_classification = channel_values.get("effective_classification", agent_def.preferred_classification)
        initial_state["history_classification"] = _escalate(
            agent_def.preferred_classification, stored_classification
        )
    except Exception as exc:  # noqa: BLE001 - never block a chat turn on backfill
        logger.warning("history backfill failed for run_id=%s, starting fresh: %s", run_id, exc)


async def _build_transcript(graph, run_id: str) -> str:
    """ADR-0209: the plain-string transcript /extract-memory's LLM prompt
    needs - a thin wrapper over _build_transcript_structured so both
    call sites share one, correctly turn-grouped, implementation."""
    turns = await _build_transcript_structured(graph, run_id)
    lines = [f"{'User' if t['role'] == 'user' else 'Assistant'}: {t['content']}" for t in turns]
    return "\n".join(lines)


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
            agent_local_only=agent_def.local_only,
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


@app.get("/v1/agents/{agent}/conversations")
async def list_conversations_endpoint(
    agent: str,
    request: Request,
    starred: bool = False,
    identity: CallerIdentity = Depends(validate_token),
) -> List[Dict[str, Any]]:
    """ADR-0527: the caller's project-less conversations for this agent,
    plus every live conversation of every project they hold a grant on -
    including colleagues', which is the point of a shared project. Each
    row carries project_id and the caller's effective role so the sidebar
    can group them and decide read-only mode without a second call."""
    agent_def = _active_agent_or_404(agent)
    return await conversations.list_conversations(
        request.app.state.conversations_pool,
        agent_name=agent_def.name,
        subject=identity.sub,
        groups=identity.groups,
        starred_only=starred,
    )


@app.put("/v1/agents/{agent}/conversations/reorder")
async def reorder_conversations_endpoint(
    agent: str,
    payload: ReorderConversationsRequest,
    request: Request,
    identity: CallerIdentity = Depends(validate_token),
) -> Dict[str, int]:
    """ADR-0515: persists a drag-drop reorder of the caller's own
    conversation list for this agent. run_ids the caller doesn't own (or
    that belong to a different agent) are silently skipped rather than
    failing the whole request - conversations.reorder_conversations scopes
    every row by (agent_name, owner_sub)."""
    agent_def = _active_agent_or_404(agent)
    updated = await conversations.reorder_conversations(
        request.app.state.conversations_pool,
        agent_name=agent_def.name,
        owner_sub=identity.sub,
        run_ids=payload.run_ids,
    )
    return {"updated": updated}


@app.get("/v1/agents/{agent}/runs/{run_id}/transcript")
async def transcript_endpoint(
    agent: str,
    run_id: str,
    request: Request,
    identity: CallerIdentity = Depends(validate_token),
) -> List[Dict[str, Any]]:
    """ADR-0212: reopening a conversation from the left-nav repopulates
    its exact prior message history from here. Reuses the same 404
    (unknown run)/403 (wrong subject) split as extract_memory_endpoint,
    widened by conversations.resolve_owner the same way _resolve_run_id
    is (see that function's docstring). ADR-0213: any granted role
    (read/clone/write/admin) may read the transcript - reading is the
    minimum right every ADR-0527 role carries."""
    agent_def = _active_agent_or_404(agent)
    graph = request.app.state.graph_factory.graph_for(agent_def)
    config = {"configurable": {"thread_id": run_id}}
    tuple_ = await graph.checkpointer.aget_tuple(config)
    if tuple_ is None:
        raise HTTPException(status_code=404, detail=f"no workflow run found for run_id '{run_id}'")

    stored_sub = (tuple_.checkpoint.get("channel_values") or {}).get("user_sub")
    conversations_pool = request.app.state.conversations_pool
    if conversations_pool is not None:
        access = await conversations.resolve_access(
            conversations_pool, run_id=run_id, subject=identity.sub, groups=identity.groups
        )
        if access is not None:
            return await _build_transcript_structured(graph, run_id)
    owner_sub = await conversations.resolve_owner(conversations_pool, run_id)
    if owner_sub is not None:
        stored_sub = owner_sub
    if stored_sub != identity.sub:
        logger.warning("refused to read transcript for run_id=%s: belongs to a different subject", run_id)
        raise HTTPException(status_code=403, detail="this workflow run belongs to a different user")

    return await _build_transcript_structured(graph, run_id)


@app.patch("/v1/agents/{agent}/runs/{run_id}")
async def rename_conversation_endpoint(
    agent: str,
    run_id: str,
    payload: RenameConversationRequest,
    request: Request,
    identity: CallerIdentity = Depends(validate_token),
) -> Dict[str, str]:
    """ADR-0212. 404 for both an unknown run_id and one owned by a
    different subject (conversations.rename_conversation collapses both
    - see its own docstring), so this endpoint never confirms another
    subject's run_id exists."""
    _active_agent_or_404(agent)
    ok = await conversations.rename_conversation(
        request.app.state.conversations_pool,
        run_id=run_id,
        subject=identity.sub,
        groups=identity.groups,
        title=payload.title,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"no conversation found for run_id '{run_id}'")
    return {"run_id": run_id, "title": payload.title}


@app.put("/v1/agents/{agent}/runs/{run_id}/star")
async def star_conversation_endpoint(
    agent: str, run_id: str, request: Request, identity: CallerIdentity = Depends(validate_token)
) -> Dict[str, bool]:
    """ADR-0212: toggles the caller's own personal star (a private
    organizing flag, never shared - see conversations.py's own schema
    comment)."""
    _active_agent_or_404(agent)
    ok = await conversations.set_star(
        request.app.state.conversations_pool,
        run_id=run_id,
        subject=identity.sub,
        groups=identity.groups,
        starred=True,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"no conversation found for run_id '{run_id}'")
    return {"starred": True}


@app.delete("/v1/agents/{agent}/runs/{run_id}/star")
async def unstar_conversation_endpoint(
    agent: str, run_id: str, request: Request, identity: CallerIdentity = Depends(validate_token)
) -> Dict[str, bool]:
    _active_agent_or_404(agent)
    ok = await conversations.set_star(
        request.app.state.conversations_pool,
        run_id=run_id,
        subject=identity.sub,
        groups=identity.groups,
        starred=False,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"no conversation found for run_id '{run_id}'")
    return {"starred": False}


@app.delete("/v1/agents/{agent}/runs/{run_id}")
async def archive_conversation_endpoint(
    agent: str, run_id: str, request: Request, identity: CallerIdentity = Depends(validate_token)
) -> Dict[str, bool]:
    """ADR-0212 follow-up: soft-delete. Hides the conversation (404 for
    both unknown and not-owned, same collapsed-case rationale as rename/
    star) - the underlying LangGraph checkpoint is never touched, only
    conversations.archived_at."""
    _active_agent_or_404(agent)
    ok = await conversations.archive_conversation(
        request.app.state.conversations_pool,
        run_id=run_id,
        subject=identity.sub,
        groups=identity.groups,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"no conversation found for run_id '{run_id}'")
    return {"archived": True}


@app.delete("/v1/agents/{agent}/runs/{run_id}/hard-delete")
async def hard_delete_conversation_endpoint(
    agent: str, run_id: str, request: Request, identity: CallerIdentity = Depends(validate_token)
) -> Dict[str, bool]:
    """ADR-0515: irreversible. Unlike archive_conversation_endpoint (soft
    delete, hides the row only), this purges both the conversations
    metadata row and the underlying LangGraph checkpoint/message history.
    The metadata row is deleted first (fail-closed 404 for both unknown
    and not-owned, same collapsed-case rationale as every other
    conversation-management endpoint here) and the checkpoint second, so a
    crash between the two calls leaves at worst an orphaned checkpoint no
    longer reachable through this caller's conversation list - never a
    visible conversation whose history silently vanished."""
    agent_def = _active_agent_or_404(agent)
    ok = await conversations.hard_delete_conversation(
        request.app.state.conversations_pool, run_id=run_id, owner_sub=identity.sub
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"no conversation found for run_id '{run_id}'")
    graph = request.app.state.graph_factory.graph_for(agent_def)
    await graph.checkpointer.adelete_thread(run_id)
    return {"deleted": True}


# --------------------------------------------------------------------------
# ADR-0527: projects. Deliberately outside the /v1/agents/{agent} family -
# a project is cross-agent (clause 6), and only its conversations are
# agent-scoped. Every handler resolves the caller's effective role through
# app/projects.py, which fails closed on an absent grant.
# --------------------------------------------------------------------------


@app.get("/v1/projects")
async def list_projects_endpoint(
    request: Request, identity: CallerIdentity = Depends(validate_token)
) -> List[Dict[str, Any]]:
    """Every live project the caller holds a grant on - directly or
    through one of their business-role groups - with their effective role,
    their personal star and a live conversation count."""
    return await projects.list_projects(
        request.app.state.conversations_pool, subject=identity.sub, groups=identity.groups
    )


@app.post("/v1/projects")
async def create_project_endpoint(
    payload: CreateProjectRequest,
    request: Request,
    identity: CallerIdentity = Depends(validate_token),
) -> Dict[str, str]:
    """ADR-0527 clause 3: no owner column - the creator is simply given an
    `admin` grant, merged into whatever grants the dialog submitted (and
    overriding a weaker self-grant, so a creator cannot lock themselves
    out on the very first save). ADR-0528: a supplied Salesforce
    opportunity is verified here, under this caller's own identity, before
    the project is stored - a project is never persisted with an
    unverified link."""
    pool = request.app.state.conversations_pool
    grants = [g.model_dump() for g in payload.grants if g.subject != identity.sub]
    grants.append({"subject": identity.sub, "group_name": None, "role": "admin"})

    sf_id, sf_at = await _verify_salesforce_link(payload.salesforce_opportunity_id, identity)
    project_id = await projects.create_project(
        pool,
        title=payload.title,
        context=payload.context,
        classification=payload.classification,
        salesforce_opportunity_id=sf_id,
        salesforce_verified_at=sf_at,
        created_by=identity.sub,
        grants=grants,
    )
    return {"project_id": project_id}


@app.get("/v1/projects/{project_id}")
async def get_project_endpoint(
    project_id: str, request: Request, identity: CallerIdentity = Depends(validate_token)
) -> Dict[str, Any]:
    """Any grant reads the project. `grants` and the Salesforce identifier
    are returned only to an admin - the grant list names colleagues, and
    ADR-0528 keeps the opportunity id off every surface that does not
    strictly need it."""
    return await projects.get_project(
        request.app.state.conversations_pool,
        project_id=project_id,
        subject=identity.sub,
        groups=identity.groups,
    )


@app.put("/v1/projects/{project_id}")
async def save_project_endpoint(
    project_id: str,
    payload: SaveProjectRequest,
    request: Request,
    identity: CallerIdentity = Depends(validate_token),
) -> Dict[str, str]:
    """The single-save commit behind ADR-0527's two-tab dialog: the whole
    desired state arrives at once, which is why this ADR needs one
    endpoint where ADR-0213 needed five.

    `write` covers the Description tab. Touching grants or the Salesforce
    link requires `admin`, checked explicitly rather than silently
    ignored - a UI that sends a change it may not make should be told, not
    quietly obeyed in part."""
    pool = request.app.state.conversations_pool
    role = await projects.require_role(
        pool, project_id=project_id, subject=identity.sub, groups=identity.groups, minimum="write"
    )

    current = await projects.get_project(
        pool, project_id=project_id, subject=identity.sub, groups=identity.groups
    )
    wants_grant_change = payload.grants is not None
    wants_link_change = (
        payload.salesforce_opportunity_id or None
    ) != current.get("salesforce_opportunity_id")
    if (wants_grant_change or wants_link_change) and role != "admin":
        raise HTTPException(
            status_code=403,
            detail="changing project members or the Salesforce link requires the 'admin' role",
        )

    if wants_link_change:
        sf_id, sf_at = await _verify_salesforce_link(payload.salesforce_opportunity_id, identity)
    else:
        sf_id = current.get("salesforce_opportunity_id")
        sf_at = current.get("salesforce_verified_at")

    await projects.save_project(
        pool,
        project_id=project_id,
        title=payload.title,
        context=payload.context,
        salesforce_opportunity_id=sf_id,
        salesforce_verified_at=sf_at,
        grants=[g.model_dump() for g in payload.grants] if payload.grants is not None else None,
        actor=identity.sub,
    )
    return {"project_id": project_id}


@app.get("/v1/projects/{project_id}/delete-preview")
async def delete_project_preview_endpoint(
    project_id: str, request: Request, identity: CallerIdentity = Depends(validate_token)
) -> Dict[str, int]:
    """ADR-0527 clause 7: the counts the confirmation must name before an
    admin archives colleagues' visible work."""
    pool = request.app.state.conversations_pool
    await projects.require_role(
        pool, project_id=project_id, subject=identity.sub, groups=identity.groups, minimum="admin"
    )
    return await projects.delete_preview(pool, project_id=project_id, subject=identity.sub)


@app.delete("/v1/projects/{project_id}")
async def delete_project_endpoint(
    project_id: str, request: Request, identity: CallerIdentity = Depends(validate_token)
) -> Dict[str, int]:
    """ADR-0527 clause 7: cascade SOFT-delete. The project and every
    conversation in it - including colleagues' - get archived_at; nothing
    is erased, which is why this is offered to a project admin at all. The
    irreversible purge stays per-conversation and owner-only."""
    pool = request.app.state.conversations_pool
    await projects.require_role(
        pool, project_id=project_id, subject=identity.sub, groups=identity.groups, minimum="admin"
    )
    return await projects.archive_project_cascade(pool, project_id=project_id)


@app.put("/v1/projects/{project_id}/star")
async def star_project_endpoint(
    project_id: str, request: Request, identity: CallerIdentity = Depends(validate_token)
) -> Dict[str, bool]:
    """A member's private organizing flag - available to anyone who may
    read the project, the same reasoning ADR-0212 applied to
    conversation_stars."""
    pool = request.app.state.conversations_pool
    await projects.require_role(
        pool, project_id=project_id, subject=identity.sub, groups=identity.groups, minimum="read"
    )
    await projects.set_project_star(pool, project_id=project_id, subject=identity.sub, starred=True)
    return {"starred": True}


@app.delete("/v1/projects/{project_id}/star")
async def unstar_project_endpoint(
    project_id: str, request: Request, identity: CallerIdentity = Depends(validate_token)
) -> Dict[str, bool]:
    pool = request.app.state.conversations_pool
    await projects.require_role(
        pool, project_id=project_id, subject=identity.sub, groups=identity.groups, minimum="read"
    )
    await projects.set_project_star(pool, project_id=project_id, subject=identity.sub, starred=False)
    return {"starred": False}


async def _verify_salesforce_link(
    candidate: Optional[str], identity: CallerIdentity
) -> tuple:
    """ADR-0528 clause 2: verification moved from conversation start to
    project save. The same project_binding.verify_project_binding call
    under the caller's own identity (ADR-0013/ADR-0032), the same three
    distinguishable causes - only the moment changed. An empty candidate
    means "free project" and is not an error.

    Failure rejects the save rather than storing an unverified link, so
    ck_projects_salesforce_pair's "both or neither" invariant holds by
    construction."""
    if not candidate:
        return None, None
    try:
        verified = await project_binding.verify_project_binding(
            candidate,
            bearer_token=identity.token,
            agent_name="project-admin",
            task_name="project-salesforce-link",
        )
    except project_binding.ProjectCandidateMissingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except project_binding.ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except project_binding.ProjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except project_binding.ProjectBindingUnreachableError as exc:
        logger.error("salesforce verification unreachable for candidate=%s: %s", candidate, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return verified, datetime.now(timezone.utc)


@app.post("/v1/agents/{agent}/runs/{run_id}/clone")
async def clone_conversation_endpoint(
    agent: str, run_id: str, request: Request, identity: CallerIdentity = Depends(validate_token)
) -> Dict[str, str]:
    """ADR-0527 clause 4: any role from `clone` upward may clone. The copy
    stays in the SOURCE's project (ADR-0213 made it a project-less,
    independently-owned conversation - that is what changed) and takes a
    derived title, but the cloner becomes its owner_sub, which is exactly
    what makes the `clone` role useful: they may write to their own copy
    while remaining unable to write to the original.

    The checkpoint copy is a full snapshot, not an incremental write - no
    live sync back. Fails closed (404) for both an unknown run_id and an
    insufficient role, the same collapsed-case rationale as every other
    conversation-management endpoint here."""
    agent_def = _active_agent_or_404(agent)
    pool = request.app.state.conversations_pool
    access = await conversations.resolve_access(
        pool, run_id=run_id, subject=identity.sub, groups=identity.groups
    )
    if access is None or conversations.rank_of(access["role"]) < conversations.ROLE_RANK["clone"]:
        raise HTTPException(status_code=404, detail=f"no conversation found for run_id '{run_id}'")

    graph = request.app.state.graph_factory.graph_for(agent_def)
    tuple_ = await graph.checkpointer.aget_tuple({"configurable": {"thread_id": run_id}})
    if tuple_ is None:
        raise HTTPException(status_code=404, detail=f"no workflow run found for run_id '{run_id}'")

    new_run_id = str(uuid.uuid4())
    new_checkpoint = dict(tuple_.checkpoint)
    new_checkpoint["id"] = str(uuid.uuid4())
    channel_values = dict(new_checkpoint.get("channel_values") or {})
    channel_values["user_sub"] = identity.sub
    new_checkpoint["channel_values"] = channel_values
    await graph.checkpointer.aput(
        {"configurable": {"thread_id": new_run_id}},
        new_checkpoint,
        tuple_.metadata or {},
        new_checkpoint.get("channel_versions") or {},
    )

    new_title = await conversations.clone_conversation(
        pool, source_run_id=run_id, new_run_id=new_run_id, owner_sub=identity.sub
    )
    if new_title is None:
        raise HTTPException(status_code=404, detail=f"no conversation found for run_id '{run_id}'")
    return {
        "run_id": new_run_id,
        "source_run_id": run_id,
        "title": new_title,
        "project_id": access["project_id"] or "",
    }


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


async def _require_customer_project(
    agent_def: AgentDefinition,
    identity: CallerIdentity,
    conversations_pool: Optional[Any],
    project_id: Optional[str],
) -> None:
    """ADR-0528 clause 3, superseding ADR-0512 clause 3: a
    `zuno.project_required` task must run in a CUSTOMER project - one
    whose Salesforce link is present and currently valid. The enforcement
    point moved from "verify a caller-supplied candidate at conversation
    start" to "check the conversation's own project", but the fail-closed
    posture did not: no project is a 400, a free project is a 403, and
    Salesforce being unreachable during a re-verification is a 503.

    Returns immediately for every task that does not set
    `zuno.project_required: true` - those behave exactly as before.

    Re-verification now happens once per PROJECT per validity window
    rather than once per conversation, which is ADR-0512's own
    "latency lands once per conversation, not per turn" taken one level
    further now that a project outlives a conversation. The ordinary chat
    path makes no Salesforce call at all while the stamp is fresh.
    """
    task = agent_def.tasks.get(agent_def.primary_task) if agent_def.primary_task else None
    if task is None or not task.project_required:
        return

    if project_id is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"task '{task.name}' requires a project - start this conversation "
                "inside a customer project"
            ),
        )

    # get_project fails closed (503) on an unconfigured pool, and 404s
    # when the caller holds no grant - a project_required task cannot run
    # without both.
    detail = await projects.get_project(
        conversations_pool, project_id=project_id, subject=identity.sub, groups=identity.groups
    )
    if not detail["is_customer"]:
        raise HTTPException(
            status_code=403,
            detail=(
                f"task '{task.name}' requires a customer project - this project has no "
                "verified Salesforce opportunity"
            ),
        )

    # get_project only reveals the Salesforce fields to an admin (ADR-0528
    # keeps the identifier off every surface that does not need it), so a
    # non-admin member cannot trigger the re-verification below. That is
    # deliberate: re-verification must run under an identity that may read
    # the opportunity, and a project admin is the identity that set it.
    verified_at = detail.get("salesforce_verified_at")
    opportunity_id = detail.get("salesforce_opportunity_id")
    if opportunity_id is None or project_binding.is_binding_still_valid(verified_at):
        return

    try:
        await project_binding.verify_project_binding(
            opportunity_id,
            bearer_token=identity.token,
            agent_name=agent_def.name,
            task_name=task.name,
        )
    except project_binding.ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except project_binding.ProjectAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except project_binding.ProjectBindingUnreachableError as exc:
        logger.error("project re-verification unreachable for project_id=%s: %s", project_id, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await projects.stamp_salesforce_verification(conversations_pool, project_id=project_id)


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
    conversations_pool = request.app.state.conversations_pool
    run_id = await _resolve_run_id(graph, payload, identity, conversations_pool)
    # ADR-0543: threaded through graph node calls (app/graph/nodes.py,
    # arkos_nodes.py) so their MCP/RAG/model-router clients can forward it
    # as X-Zuno-Run-Id, distinct from the request_id above (one HTTP call
    # vs. the whole conversation turn) - needed for the per-run resource
    # dashboard.
    initial_state["run_id"] = run_id
    await _seed_history_backfill(graph, run_id, payload.run_id is not None, initial_state, agent_def)
    # ADR-0527: resolve which project this turn belongs to, server-side.
    # On a RESUME the conversation's own row decides and payload.project_id
    # is ignored outright (a conversation's project is fixed at creation -
    # letting a later turn move it would silently move it between two
    # different ACLs). On a BRAND-NEW conversation the caller's requested
    # project is checked against their own grants before it is recorded.
    # _initial_state no longer copies payload.project_id at all, so nothing
    # downstream can see an unverified value.
    resolved_project_id: Optional[str] = None
    project_context = ""
    project_classification: Optional[str] = None
    if payload.run_id is not None and conversations_pool is not None:
        access = await conversations.resolve_access(
            conversations_pool, run_id=run_id, subject=identity.sub, groups=identity.groups
        )
        if access is not None:
            resolved_project_id = access["project_id"]
            project_context = access["project_context"]
            project_classification = access["project_classification"]
            if payload.project_id is not None and payload.project_id != resolved_project_id:
                logger.warning(
                    "ignoring client-supplied project_id on resume: body=%s conversation=%s (run_id=%s)",
                    payload.project_id, resolved_project_id, run_id,
                )
    elif payload.project_id is not None and conversations_pool is not None:
        # Brand-new conversation asking to be created inside a project:
        # `write` or better, or it does not get created there at all.
        await projects.require_role(
            conversations_pool,
            project_id=payload.project_id,
            subject=identity.sub,
            groups=identity.groups,
            minimum="write",
        )
        resolved_project_id = payload.project_id
        detail = await projects.get_project(
            conversations_pool,
            project_id=payload.project_id,
            subject=identity.sub,
            groups=identity.groups,
        )
        project_context = detail["context"]
        project_classification = detail["classification"]

    if resolved_project_id is not None:
        initial_state["project_id"] = resolved_project_id
    # ADR-0527 clause 5: the project's standing context, injected in
    # reason_node/draft_node as delimited background - never instructions.
    initial_state["project_context"] = project_context
    if project_classification:
        initial_state["project_classification"] = project_classification

    # ADR-0512/WP-55 (re-keyed by ADR-0528): fail-closed before any graph
    # action for a project_required primary task - raises HTTPException
    # itself on any denial, so nothing below this line runs unverified.
    await _require_customer_project(agent_def, identity, conversations_pool, resolved_project_id)

    # ADR-0212: creates the conversations row on first use of run_id
    # (title derived from this opening message) or just bumps updated_at
    # on resume - no-ops if conversation persistence isn't configured, so
    # chat itself never depends on this pool being up.
    await conversations.record_turn(
        conversations_pool,
        run_id=run_id,
        agent_name=agent_def.name,
        owner_sub=identity.sub,
        opening_message=payload.message,
        project_id=resolved_project_id,
    )

    # ADR-0527: a resumed conversation requires a write-capable effective
    # role (`write` or `admin` - _resolve_run_id above only proved *read*
    # access, which `read` and `clone` also carry) and the
    # single-active-writer lease. Checked only after record_turn above,
    # which guarantees a conversations row exists for run_id by now -
    # conversation_write_locks has a foreign key on conversations.run_id,
    # so acquiring any earlier could fail for a run_id resuming a
    # genuinely pre-ADR-0212 checkpoint. A brand new conversation
    # (payload.run_id was None) has no role to check yet and no lease to
    # contend for.
    write_lock_holder: Optional[str] = None
    if payload.run_id is not None and conversations_pool is not None:
        role = access["role"] if access is not None else None
        if role is not None and conversations.rank_of(role) < conversations.ROLE_RANK["write"]:
            raise HTTPException(status_code=403, detail="this role cannot send messages in this conversation")
        if not await conversations.acquire_write_lock(conversations_pool, run_id=run_id, holder_sub=identity.sub):
            raise HTTPException(
                status_code=409, detail="another collaborator is currently writing to this conversation"
            )
        write_lock_holder = identity.sub

    config = {"configurable": {"thread_id": run_id}}

    if "text/event-stream" in accept:
        return StreamingResponse(
            _stream_chat(
                graph, initial_state, config, request_id, run_id,
                agent=agent_def.name, graph_shape=agent_def.graph_shape,
                conversations_pool=conversations_pool, write_lock_holder=write_lock_holder,
                project_id=resolved_project_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                REQUEST_ID_HEADER: request_id,
            },
        )

    try:
        with api_request_span(
            run_id, agent=agent_def.name, request_id=request_id, project_id=resolved_project_id
        ):
            with graph_run_span(
                payload.session_id, agent=agent_def.name, graph_shape=agent_def.graph_shape,
                run_id=run_id, project_id=resolved_project_id,
            ) as recorder:
                final_state = await _ainvoke_with_retry(
                    graph, initial_state, config, session_id=payload.session_id, request_id=request_id,
                )
                recorder.source_mode = final_state.get("source_mode", "none")
                recorder.live_read_trigger_reason = final_state.get("live_read_trigger_reason")
    except Exception as exc:
        logger.error("graph execution failed for session=%s request_id=%s: %s", payload.session_id, request_id, exc)
        raise HTTPException(status_code=500, detail=f"agent workflow failed: {exc}") from exc
    finally:
        if write_lock_holder is not None:
            await conversations.release_write_lock(conversations_pool, run_id=run_id, holder_sub=write_lock_holder)

    # ADR-0534/WP-109: observe-only guardrails evaluation of the converged
    # exchange, spawned fire-and-forget AFTER the response below is already
    # decided - it can never delay, block or alter it. Detections land in
    # the agent_runtime.guardrails log stream only.
    guardrails_client.observe_exchange(
        message=final_state.get("message", ""),
        reply=final_state.get("reply", ""),
        run_id=run_id,
        agent=agent_def.name,
        project_id=resolved_project_id,
        tool_results=final_state.get("tool_results"),
        retrieved_doc_count=len(final_state.get("retrieved_docs") or []),
    )

    return ChatResponse(
        reply=final_state.get("reply", ""),
        citations=final_state.get("citations", []),
        images=final_state.get("generated_images", []),
        run_id=run_id,
        source_mode=final_state.get("source_mode", "indexed"),
        # ADR-0528: lets agent-bff tag its own span on the non-streaming
        # path (the streaming path reads it from the SSE start event).
        project_id=resolved_project_id or "",
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

# ADR-0527: how often the streaming path renews its write lease. Comfortably
# inside conversations._WRITE_LOCK_TTL_SECONDS (30) so a renewal that is late
# by a scheduling hiccup still lands before the lease expires, and far enough
# apart that a long reply costs a handful of UPDATEs rather than one per token.
_WRITE_LOCK_RENEW_SECONDS = 10

# Shown to the client for an unexpected exception in _stream_chat's own
# except blocks - never str(exc) directly (see the comment at each yield
# site for the incident this followed). request_id is already what
# logger.error prints just above each yield, so it's the natural
# correlator to hand back to the user for support/bug reports without
# exposing internals.
_CLIENT_FACING_STREAM_ERROR = "Something went wrong on our side. Please try again. (ref: {request_id})"


async def _stream_chat(
    graph,
    initial_state: Dict[str, Any],
    config: Dict[str, Any],
    request_id: str,
    run_id: str,
    *,
    agent: Optional[str] = None,
    graph_shape: Optional[str] = None,
    conversations_pool: Optional[Any] = None,
    write_lock_holder: Optional[str] = None,
    project_id: Optional[str] = None,
) -> AsyncIterator[str]:
    """Streams token deltas from the `reason` node's underlying chat model
    via LangGraph's `astream_events` (v2), which surfaces
    `on_chat_model_stream` events for any model call nested inside a node
    -- no need to restructure the node itself for streaming to work. Also
    surfaces `tool` events (start/end of `_TOOL_NODES` entries) and a
    `start` event carrying request_id and run_id (ADR-0045, ADR-0103) -
    the frontend needs run_id to resume this exact workflow later.

    ADR-0213: when write_lock_holder is set (a resumed, lease-guarded
    conversation - agent_chat only passes it then), the outer `finally`
    releases the write lease on every exit path, including a client
    disconnect - an async generator's `finally` runs when FastAPI closes
    it mid-iteration, which is exactly the "on-disconnect handler" the
    ADR's Decision text asks for. The lease's own TTL is the fallback if
    even this never runs (a hard crash).

    ADR-0527 fixes what ADR-0213 specified but never implemented: the
    lease is also RENEWED while tokens stream. Its TTL is 30 seconds and
    agent-bff allows an SSE response 180, so a long reply routinely
    outlived its own lease - leaving it expired and stealable mid-run,
    which is precisely the checkpoint race the lease exists to prevent.
    Renewal is throttled on a monotonic clock so it costs one UPDATE every
    ~10 seconds rather than one per token, and a failed renewal ends the
    stream with an error event rather than continuing unprotected.

    ADR-0543: wraps this whole generator's execution in api_request_span,
    the streaming-path equivalent of the sync path's span in agent_chat -
    errors are handled internally here (an SSE "error" event, not a raised
    exception), so the two `except` branches below call
    api_recorder.mark_error() explicitly rather than relying on the span
    catching a propagating exception. The retry loop itself is additionally
    wrapped in graph_run_span (agent_graph_run) - the streaming-path
    equivalent of the non-streaming path's own graph_run_span in
    agent_chat, previously only emitted for non-streaming calls even
    though streaming is the common case.
    """
    with api_request_span(
        run_id, agent=agent, request_id=request_id, project_id=project_id
    ) as api_recorder:
        try:
            # ADR-0528: the start event carries the server-resolved project
            # so agent-bff can tag its own span from the streaming path, the
            # way it reads run_id today.
            yield _sse("start", {"request_id": request_id, "run_id": run_id, "project_id": project_id or ""})

            citations: Any = []
            images: Any = []
            source_mode = "indexed"
            # One bounded retry, same rationale as _ainvoke_with_retry, but only
            # safe to take before any token has reached the client (ADR-0029-style
            # precedent: components/ai-gateway/app/main.py's _stream_completion
            # never silently retries a candidate that already streamed partial
            # content, since the client has content a fresh run wouldn't continue
            # coherently) - sent_any tracks that boundary.
            sent_any = False
            attempts_remaining = 2
            # ADR-0527: lease renewal state. next_renewal_at is monotonic,
            # so it is immune to a wall-clock step during a long stream.
            lease_lost = False
            next_renewal_at = time.monotonic() + _WRITE_LOCK_RENEW_SECONDS
            with graph_run_span(
                initial_state.get("session_id", ""), agent=agent, graph_shape=graph_shape,
                run_id=run_id, project_id=project_id,
            ) as graph_recorder:
                while attempts_remaining:
                    attempts_remaining -= 1
                    try:
                        async for event in graph.astream_events(initial_state, config=config, version="v2"):
                            kind = event.get("event")
                            name = event.get("name")
                            if kind == "on_chat_model_stream":
                                # ADR-0215: the history-compaction node's own internal
                                # summarization call is a real nested chat-model
                                # invocation inside this same graph run, so it emits
                                # on_chat_model_stream events too - tagged
                                # "zuno-internal" (app/clients/model_router.py) so it
                                # never reaches the user as a chat token.
                                if "zuno-internal" in (event.get("tags") or []):
                                    continue
                                chunk = event["data"].get("chunk")
                                token = getattr(chunk, "content", "") if chunk is not None else ""
                                if token:
                                    sent_any = True
                                    yield _sse("token", {"delta": token})
                                    if (
                                        write_lock_holder is not None
                                        and conversations_pool is not None
                                        and time.monotonic() >= next_renewal_at
                                    ):
                                        # acquire_write_lock's ON CONFLICT
                                        # renews in place when we are still
                                        # the holder, and returns False only
                                        # if someone else legitimately took
                                        # over after ours expired - at which
                                        # point continuing would race their
                                        # writes on the same thread.
                                        if not await conversations.acquire_write_lock(
                                            conversations_pool, run_id=run_id, holder_sub=write_lock_holder
                                        ):
                                            lease_lost = True
                                            break
                                        next_renewal_at = time.monotonic() + _WRITE_LOCK_RENEW_SECONDS
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
                            elif kind == "on_chain_end" and name in ("reason", "draft"):
                                # ADR-0415: generate_image results are returned by
                                # whichever node actually calls the model
                                # (retrieve_reason_respond's "reason", plan_draft_write's
                                # "draft") - unlike citations/source_mode above, there is
                                # no later node in either shape that re-assembles this,
                                # so it's captured here directly.
                                output = event["data"].get("output") or {}
                                if output.get("generated_images"):
                                    images = output["generated_images"]
                        if lease_lost:
                            # ADR-0527: another collaborator legitimately
                            # took the lease over after ours expired.
                            # Stopping here is the point - continuing would
                            # race their writes on the same LangGraph
                            # thread, the exact data-integrity gap the
                            # lease closes.
                            logger.warning(
                                "write lease lost mid-stream, ending reply: run_id=%s holder=%s",
                                run_id, write_lock_holder,
                            )
                            api_recorder.mark_error()
                            graph_recorder.mark_error()
                            yield _sse(
                                "error",
                                {
                                    "message": (
                                        "Another collaborator started writing to this conversation, "
                                        "so this reply was stopped. Reopen the conversation to see "
                                        "the current state."
                                    )
                                },
                            )
                            return
                    except psycopg.OperationalError as exc:
                        if sent_any or attempts_remaining == 0:
                            logger.error("SSE stream failed request_id=%s: %s", request_id, exc)
                            api_recorder.mark_error()
                            graph_recorder.mark_error()
                            yield _sse("error", {"message": _CLIENT_FACING_STREAM_ERROR.format(request_id=request_id)})
                            return
                        logger.warning(
                            "checkpoint DB connection failed before any token sent, retrying once: request_id=%s: %s",
                            request_id, exc,
                        )
                        continue
                    except Exception as exc:
                        # Live-cluster-confirmed 2026-08-23: an unexpected exception
                        # here (e.g. a KeyError from a malformed tool response) used
                        # to reach the client verbatim via str(exc) - a raw Python
                        # repr with no context, displayed in the chat bubble as if
                        # it were a real reply. The full exception still goes to the
                        # server log immediately above; only the client-facing
                        # message is generic now. Deliberate exceptions from a graph
                        # node's own graceful-degradation path (e.g.
                        # _resolve_image_generation_call's "error" in result branch)
                        # never reach this handler at all - those return a normal
                        # AIMessage-driven reply through the second model call, not
                        # a raised exception.
                        logger.error("SSE stream failed request_id=%s: %s", request_id, exc)
                        api_recorder.mark_error()
                        graph_recorder.mark_error()
                        yield _sse("error", {"message": _CLIENT_FACING_STREAM_ERROR.format(request_id=request_id)})
                        return
                    else:
                        break
                graph_recorder.source_mode = source_mode

            yield _sse("done", {"citations": citations, "images": images, "source_mode": source_mode})

            # ADR-0534/WP-109: observe-only guardrails on the streaming
            # path - the common one in production, so skipping it would
            # leave guardrails observing almost no real traffic. The
            # stream never materializes final_state, so the converged
            # exchange is read back from the checkpoint (same
            # channel_values pattern extract_memory_endpoint uses). The
            # "done" event above is already sent: nothing here can delay
            # or alter what the client received. Failures only log.
            try:
                tuple_ = await graph.checkpointer.aget_tuple(config)
                channel_values = (tuple_.checkpoint.get("channel_values") or {}) if tuple_ else {}
                guardrails_client.observe_exchange(
                    message=channel_values.get("message", ""),
                    reply=channel_values.get("reply", ""),
                    run_id=run_id,
                    agent=agent,
                    project_id=project_id,
                    tool_results=channel_values.get("tool_results"),
                    retrieved_doc_count=len(channel_values.get("retrieved_docs") or []),
                )
            except Exception as exc:  # noqa: BLE001 - observe-only
                logger.warning(
                    "guardrails checkpoint read failed (observe-only, stream unaffected): "
                    "run_id=%s: %s", run_id, exc,
                )
        finally:
            if conversations_pool is not None and write_lock_holder is not None:
                await conversations.release_write_lock(
                    conversations_pool, run_id=run_id, holder_sub=write_lock_holder
                )
