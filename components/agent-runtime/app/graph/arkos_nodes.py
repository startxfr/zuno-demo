"""Arkos-specific LangGraph nodes (ADR-0342/WP-31): plan -> retrieve ->
draft -> write, the concrete second graph shape proving GraphFactory
generalizes past Tekos's retrieve/tool_call/reason/respond flow
(app/graph/nodes.py). Mirrors that module's own pattern - module-level
singletons resolved from the real OKF bundle at import time, fail-fast if
missing - applied to Arkos's own agent/task instead of Tekos's.

Arkos's shape ends in a write side effect (Drive) rather than an
assemble-citations respond node: there is no equivalent of Tekos's
tool_call_node here (Arkos has no live-read trigger to speak of - its live
capabilities, drive.document.create/update, ARE the write itself, not a
freshness check before answering).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.clients.mcp_client import McpClientError, invoke_tool
from app.clients.model_router import ModelRouter, ModelRouterError
from app.clients.rag_client import RagClientError, search
from app.graph.history import build_history_messages
from app.graph.nodes import (
    _GENERATE_IMAGE_TOOL_SCHEMA,
    _LIVE_READ_CLASSIFICATION,
    _code_request_trigger_reason,
    _escalate,
    _image_generation_declared,
    _resolve_image_generation_call,
)
from app.graph.state import AgentState
from app.knowledge import KnowledgePolicyStore, resolve_authorized_domains
from app.registry import AgentRegistry, TaskDefinition

logger = logging.getLogger("agent_runtime.graph.arkos")

# A second, independent AgentRegistry load (mirrors app/graph/nodes.py's
# own reasoning for why app/main.py builds its own instance too rather
# than sharing one across modules): each module that needs agent/task
# data resolves it for itself, module-scoped and fail-fast, rather than
# threading a shared registry object through imports.
_registry = AgentRegistry()
if _registry.load_errors:
    raise RuntimeError(f"agent-runtime: failed to load OKF bundles: {_registry.load_errors}")
_ARKOS = _registry.get("arkos")
if _ARKOS is None:
    raise RuntimeError("agent-runtime: no 'arkos' agent bundle found under AGENTS_DIR")
_DRAFT_TASK = _ARKOS.tasks.get("draft-architecture-testimonial")
if _DRAFT_TASK is None or not _DRAFT_TASK.prompt:
    raise RuntimeError(
        "agent-runtime: arkos's 'draft-architecture-testimonial' task or its prompt file is missing"
    )
# ADR-0514: a second consumer of the retrieve/draft/reflect/write path -
# see _active_task() below for how plan_node's doc_plan.kind picks between
# this and _DRAFT_TASK.
_WORKSHOP_TASK = _ARKOS.tasks.get("workshop-presentation")
if _WORKSHOP_TASK is None or not _WORKSHOP_TASK.prompt:
    raise RuntimeError(
        "agent-runtime: arkos's 'workshop-presentation' task or its prompt file is missing"
    )
# ADR-0417: catalog-only task, referenced solely as a task_name routing
# label by code_node below (see that task's own file for why) - never a
# task GraphFactory builds a graph for directly, same "declared but not
# independently live-routed" status Finage's non-primary tasks have.
_WRITE_CODE_TASK = _ARKOS.tasks.get("write-code")
if _WRITE_CODE_TASK is None:
    raise RuntimeError("agent-runtime: arkos's 'write-code' task bundle is missing")
# Same early-exit, catalog-only shape as _WRITE_CODE_TASK above, this time
# for a demo-narrative request - see demo_node below.
_STRUCTURE_DEMO_TASK = _ARKOS.tasks.get("structure-demo")
if _STRUCTURE_DEMO_TASK is None or not _STRUCTURE_DEMO_TASK.prompt:
    raise RuntimeError(
        "agent-runtime: arkos's 'structure-demo' task or its prompt file is missing"
    )

# ADR-0419/ADR-0514: reflect_node's declarative config, resolved once per
# task rather than duplicating the same fallback logic per task - a
# graceful-degradation fallback to the literal values this used to
# hardcode, not a fail-fast RuntimeError like _DRAFT_TASK/_WRITE_CODE_TASK
# above, matching the ADR's own accepted-risk mitigation ("reflect_node's
# own code still supplies a literal fallback if the slot is absent").


def _resolve_reflect_slot(task: TaskDefinition, fallback_prompt: str) -> tuple[str, str]:
    slot = task.prompts.get("reflect")
    ceiling = (slot.classification_ceiling if slot else None) or "C2"
    prompt = (slot.prompt if slot else None) or fallback_prompt
    return ceiling, prompt


_REFLECT_CLASSIFICATION_CEILING, _REFLECT_SYSTEM_PROMPT = _resolve_reflect_slot(
    _DRAFT_TASK,
    "You are reviewing your own draft of a Design & Architecture "
    "Testimonial before it is saved. Read it critically and return "
    "an improved version: tighten unclear passages, check internal "
    "consistency, and strengthen weak sections. Return only the "
    "revised document body, with no commentary about the review "
    "itself.",
)
_WORKSHOP_REFLECT_CLASSIFICATION_CEILING, _WORKSHOP_REFLECT_SYSTEM_PROMPT = _resolve_reflect_slot(
    _WORKSHOP_TASK,
    "You are reviewing your own draft of an Odyssey architecture "
    "workshop presentation before it is saved. Read it critically and "
    "return an improved version: tighten unclear passages, check "
    "internal consistency, and strengthen weak sections. Return only "
    "the revised document body, with no commentary about the review "
    "itself.",
)

ARKOS_BASE_CLASSIFICATION = _ARKOS.preferred_classification  # from agent.okf.md's zuno.model
RAG_TOP_K = _ARKOS.rag_top_k or 5  # Arkos declares no zuno.rag block; AgentDefinition defaults to 5

# ADR-0417: fixed ceiling for code_node's call only - mirrors reflect_node's
# ADR-0416 C2 override; mistral-codestral is eligible_for: [C1, C2] only,
# never reachable at Arkos's ambient C3 seed without this.
_CODE_GENERATION_CLASSIFICATION = "C2"

_model_router = ModelRouter()
_knowledge_store = KnowledgePolicyStore()

# Deterministic best-effort topic extraction (mirrors app/graph/nodes.py's
# own _extract_product_version pattern) - the model does the real
# drafting; this only needs a short label for the plan/retrieval query/
# document title, not full NLU.
_TOPIC_PATTERN = re.compile(
    r"(?:draft|create|write)\s+(?:a\s+|an\s+)?(?:dat|design\s*(?:&|and)\s*architecture\s+testimonial|"
    r"architecture\s+testimonial|document)\s+(?:for|about|on)\s+(.+)",
    re.IGNORECASE,
)
# ADR-0514: same best-effort extraction as _TOPIC_PATTERN above, matched
# separately (rather than folded into one alternation) since the trigger
# verbs and the "workshop presentation" noun phrase are both independently
# variable.
_WORKSHOP_TOPIC_PATTERN = re.compile(
    r"(?:prepare|structure|draft|create)\s+(?:a\s+|an\s+)?(?:odyssey\s+)?workshop"
    r"(?:\s+presentation)?\s+(?:for|about|on)\s+(.+)",
    re.IGNORECASE,
)


def _extract_topic(message: str) -> str:
    match = _TOPIC_PATTERN.search(message) or _WORKSHOP_TOPIC_PATTERN.search(message)
    if match:
        return match.group(1).strip().rstrip(".")
    return message.strip()


# ADR-0514: classifies which of the two retrieve/draft/reflect/write tasks
# a turn on the "retrieve" route_after_plan branch drafts - "dat" (the
# default) or "workshop". Deliberately checked here, inside plan_node,
# rather than as a fourth route_after_plan branch: both kinds still run
# the identical node sequence, so there is no new graph edge to add, only
# a field on doc_plan the downstream nodes read.
_WORKSHOP_TRIGGER_PATTERN = re.compile(r"\b(?:workshop|odyssey)\b", re.IGNORECASE)


def _classify_doc_kind(message: str) -> str:
    if _WORKSHOP_TRIGGER_PATTERN.search(message or ""):
        return "workshop"
    return "dat"


def _active_task(state: AgentState) -> TaskDefinition:
    """ADR-0514: resolves which of _DRAFT_TASK/_WORKSHOP_TASK this turn's
    retrieve/draft/reflect/write nodes act on, from plan_node's own
    doc_plan.kind classification. Defaults to _DRAFT_TASK when doc_plan is
    absent (defensive only - plan_node always runs first on this route)."""
    kind = (state.get("doc_plan") or {}).get("kind", "dat")
    return _WORKSHOP_TASK if kind == "workshop" else _DRAFT_TASK


def _active_reflect(state: AgentState) -> tuple[str, str]:
    kind = (state.get("doc_plan") or {}).get("kind", "dat")
    if kind == "workshop":
        return _WORKSHOP_REFLECT_CLASSIFICATION_CEILING, _WORKSHOP_REFLECT_SYSTEM_PROMPT
    return _REFLECT_CLASSIFICATION_CEILING, _REFLECT_SYSTEM_PROMPT


# Arkos-local trigger, unlike _code_request_trigger_reason (app/graph/
# nodes.py): "demo"/"structure a demo" is Arkos-only vocabulary today, no
# second agent needs to share the regex, so it stays in this module rather
# than the cross-agent one - same reasoning _TOPIC_PATTERN above already
# follows.
_DEMO_TRIGGER_PATTERN = re.compile(
    r"\b(?:structure|prepare|build|put together|walk\s*through|script)\s+(?:me\s+)?(?:a|an)\s+demo\b"
    r"|\bdemo\s+(?:narrative|script|walkthrough|talk\s*track)\b",
    re.IGNORECASE,
)


def _demo_request_trigger_reason(message: str) -> Optional[str]:
    """Same provisional-heuristic posture as _code_request_trigger_reason:
    expect false negatives/positives, tune from real usage rather than
    trying to enumerate every phrasing up front."""
    if _DEMO_TRIGGER_PATTERN.search(message or ""):
        return "message phrasing matched the demo-structuring trigger pattern"
    return None


async def plan_node(state: AgentState) -> Dict[str, Any]:
    """Derives what document this turn drafts - a short topic, a working
    title and (ADR-0514) which task's kind ("dat" or "workshop") - from
    the user's message. The full v1 DAT workflow (collect -> outline ->
    explicit user review -> generation -> review -> final Google Doc,
    MEMORY.md section 8) stages this over several checkpointed turns with
    explicit review gates; this task proves the plan -> retrieve -> draft
    -> write shape end to end in one turn - see the task file's own scope
    note (workshop-presentation.md's own scope note makes the same
    disclaimer for the full multi-artifact Odyssey workflow).
    """
    topic = _extract_topic(state["message"])
    kind = _classify_doc_kind(state["message"])
    title_prefix = "Workshop" if kind == "workshop" else "DAT"
    return {"doc_plan": {"topic": topic, "doc_title": f"{title_prefix} - {topic}", "kind": kind}}


def route_after_plan(state: AgentState) -> str:
    """ADR-0417: a coding request has nothing to do with drafting/saving a
    document to Drive - short-circuit straight from plan_node, before
    retrieve/draft/reflect/write ever run. Demo-narrative requests get the
    same early-exit treatment, checked second: both are conversational
    replies with no retrieval/write step, distinct from the dat/workshop
    kinds plan_node's own doc_plan.kind classifies for the retrieve path."""
    message = state.get("message", "")
    if _code_request_trigger_reason(message) is not None:
        return "code"
    if _demo_request_trigger_reason(message) is not None:
        return "demo"
    return "retrieve"


async def code_node(state: AgentState) -> Dict[str, Any]:
    """ADR-0417: early-exit branch, reachable only via route_after_plan.
    Never runs retrieve_node, so this call's payload is only the user's
    own message - never retrieved_docs/Confluence content - which is what
    makes evaluating it at a fixed C2 ceiling (below Arkos's ambient C3
    seed) safe, the same scoped-exception shape as reflect_node/
    generate_image. Routes via the (arkos, write-code) strict: true
    preference - mistral-codestral only, no fallback; a ModelRouterError
    here is the turn's genuine, final failure (the concrete form of "ask
    the user to retry/choose a different model" - nothing auto-
    substitutes a model the user didn't ask for).
    """
    system = SystemMessage(content=(
        "You are Arkos, an architecture assistant. The user is asking for "
        "code, a configuration file, or a script - not a document draft. "
        "Respond with the requested code in a fenced code block, plus a "
        "brief explanation only if it adds real value."
    ))
    human = HumanMessage(content=state["message"])
    local_only = state.get("local_only_required", False) or _ARKOS.local_only
    try:
        result, provider = await _model_router.invoke_with_fallback(
            classification=_CODE_GENERATION_CLASSIFICATION,
            messages=[system, human],
            bearer_token=state["bearer_token"],
            local_only=local_only,
            request_id=state.get("request_id"),
            agent_name=_ARKOS.name,
            task_name=_WRITE_CODE_TASK.name,
        )
    except ModelRouterError as exc:
        logger.error("code generation model call failed: %s", exc)
        return {
            "reply": (
                "I could not reach the approved model provider for code "
                "generation right now. Please try again shortly."
            ),
            "provider_used": None,
            "citations": [],
            "source_mode": "none",
            "errors": state.get("errors", []) + [f"code: {exc}"],
        }

    reply_text = result.content if hasattr(result, "content") else str(result)
    # citations/source_mode set explicitly - this is the first Arkos path
    # that skips write_node, the only other place that normally sets them.
    return {"reply": reply_text, "provider_used": provider.name, "citations": [], "source_mode": "none"}


async def demo_node(state: AgentState) -> Dict[str, Any]:
    """Early-exit branch, reachable only via route_after_plan, same shape
    as code_node above: never runs retrieve_node, so this call's payload
    is only the user's own message. Unlike code_node's fixed C2 ceiling
    (which exists to reach mistral-codestral, eligible_for [C1, C2] only),
    this call has no such routing constraint - it rides Arkos's own
    ambient classification like draft_node does, just without a
    retrieve/write step around it."""
    system = SystemMessage(content=_STRUCTURE_DEMO_TASK.prompt)
    human = HumanMessage(content=state["message"])
    local_only = state.get("local_only_required", False) or _ARKOS.local_only
    try:
        result, provider = await _model_router.invoke_with_fallback(
            classification=ARKOS_BASE_CLASSIFICATION,
            messages=[system, human],
            bearer_token=state["bearer_token"],
            local_only=local_only,
            request_id=state.get("request_id"),
            agent_name=_ARKOS.name,
            task_name=_STRUCTURE_DEMO_TASK.name,
        )
    except ModelRouterError as exc:
        logger.error("demo-structuring model call failed: %s", exc)
        return {
            "reply": (
                "I could not reach the approved model provider to structure "
                "this demo right now. Please try again shortly."
            ),
            "provider_used": None,
            "citations": [],
            "source_mode": "none",
            "errors": state.get("errors", []) + [f"demo: {exc}"],
        }

    reply_text = result.content if hasattr(result, "content") else str(result)
    return {"reply": reply_text, "provider_used": provider.name, "citations": [], "source_mode": "none"}


async def retrieve_node(state: AgentState) -> Dict[str, Any]:
    """The same ADR-0203 knowledge-domain intersection Tekos's own
    retrieve_node runs (app/graph/nodes.py), evaluated independently here
    against Arkos's own agent/task declarations - proving knowledge-domain
    sharing (knowledge.project alongside knowledge.tech) works identically
    regardless of which graph shape executes the task (ADR-0342/ADR-0209).
    Query-driven by the plan's topic rather than the raw message, since a
    request like "draft a DAT for the OpenShift AI GPU sizing project"
    should retrieve on "the OpenShift AI GPU sizing project", not the
    whole imperative sentence.

    Also calls live Confluence search (ADR-0117/WP-02's real MCP server)
    when the task declares it - ADR-0326's "live Jira/Confluence actions
    without physical endpoint coupling" completion-pattern bullet. Unlike
    Tekos's separate, conditionally-triggered tool_call_node, Arkos folds
    this into retrieve_node itself and calls it unconditionally: a DAT
    always benefits from checking internal Confluence context alongside
    the RAG corpus, there is no "does this look like a live-data question"
    trigger to evaluate first - one more structural way this shape
    genuinely differs from Tekos's.
    """
    task = _active_task(state)
    caller_groups = state.get("groups", [])
    project_id = state.get("project_id")

    decision = resolve_authorized_domains(
        store=_knowledge_store,
        agent_declared=_ARKOS.declared_knowledge(),
        task_allowed=task.allowed_knowledge,
        caller_groups=caller_groups,
        project_id=project_id,
    )
    authorized_domains = decision.authorized_domains
    topic = (state.get("doc_plan") or {}).get("topic") or state["message"]

    docs = []
    effective_classification = ARKOS_BASE_CLASSIFICATION
    errors = list(state.get("errors", []))

    if not authorized_domains:
        logger.warning(
            "no knowledge domain authorized for this call, skipping RAG retrieval: %s", decision.denied
        )
        errors.append(f"retrieve: no authorized knowledge domain ({decision.denied})")
    else:
        try:
            docs = await search(
                query=topic,
                top_k=RAG_TOP_K,
                caller_groups=caller_groups,
                domains=authorized_domains,
                project_id=project_id,
                caller_sub=state.get("user_sub"),
            )
        except RagClientError as exc:
            logger.warning("rag-service search failed, continuing without retrieved context: %s", exc)
            errors.append(f"retrieve: {exc}")

    for doc in docs:
        effective_classification = _escalate(effective_classification, doc.get("classification", "C1"))

    update: Dict[str, Any] = {"retrieved_docs": docs, "effective_classification": effective_classification, "errors": errors}

    if "confluence.page.search" not in task.allowed_tools:
        return update

    escalated = _escalate(effective_classification, _LIVE_READ_CLASSIFICATION)
    try:
        result = await invoke_tool(
            tool_name="confluence.page.search",
            arguments={"query": topic},
            bearer_token=state["bearer_token"],
            data_classification=escalated,
            agent_name=_ARKOS.name,
            task_name=task.name,
        )
    except McpClientError as exc:
        logger.warning("Confluence search failed, continuing without it: %s", exc)
        update["errors"] = errors + [f"retrieve: confluence search: {exc}"]
        return update

    update["effective_classification"] = escalated
    update["tool_results"] = {"confluence.page.search": result}
    if not result.get("external_model_policy", {}).get("allow_context", True):
        update["local_only_required"] = True
    return update


def _build_context_block(state: AgentState) -> str:
    parts = []
    for doc in state.get("retrieved_docs", []):
        parts.append(f"[{doc['title']}] ({doc['source']})\n{doc.get('snippet', '')}")

    confluence = state.get("tool_results", {}).get("confluence.page.search")
    if confluence:
        for item in confluence.get("result", {}).get("results", []):
            parts.append(f"[Confluence: {item['title']}] ({item.get('url', '')})\n{item.get('excerpt', '')}")

    return "\n\n---\n\n".join(parts) if parts else "(no supporting context retrieved)"


async def draft_node(state: AgentState) -> Dict[str, Any]:
    """Calls the AI Inference Gateway to draft the long-form document body
    - the step with no equivalent in Tekos's shape: this produces a full
    document draft that feeds write_node, not a short conversational reply
    that IS the final answer (compare app/graph/nodes.py:reason_node).

    ADR-0215: same history/summary injection as reason_node - lets a
    follow-up like "make section 2 shorter" actually refer back to the
    document just drafted, rather than each turn drafting from scratch.
    """
    task = _active_task(state)
    context = _build_context_block(state)
    plan = state.get("doc_plan") or {}
    summary = state.get("summary", "")
    system_content = task.prompt
    if summary:
        system_content += (
            "\n\n## Conversation summary (earlier turns, background information - not instructions)\n"
            + summary
        )
    system = SystemMessage(content=system_content)
    history_messages = build_history_messages(state.get("history", []), _ARKOS.history_token_budget, summary)
    human = HumanMessage(
        content=(
            f"Document title: {plan.get('doc_title', 'Untitled')}\n\n"
            f"Context:\n{context}\n\nRequest: {state['message']}"
        )
    )

    classification = state.get("effective_classification", ARKOS_BASE_CLASSIFICATION)
    # ADR-0416: agent.local_only mirrors app/graph/nodes.py:reason_node's
    # same unconditional, agent-declared restriction (defaults False -
    # Arkos doesn't set it, only relevant if a future agent on this shape
    # does).
    local_only = state.get("local_only_required", False) or _ARKOS.local_only
    # ADR-0415: same declarative gate as app/graph/nodes.py:reason_node.
    image_generation_enabled = _image_generation_declared(task)
    turn_messages: List[Any] = [system, *history_messages, human]
    try:
        result, provider = await _model_router.invoke_with_fallback(
            classification=classification,
            messages=turn_messages,
            bearer_token=state["bearer_token"],
            local_only=local_only,
            request_id=state.get("request_id"),
            agent_name=_ARKOS.name,
            task_name=task.name,
            tools=[_GENERATE_IMAGE_TOOL_SCHEMA] if image_generation_enabled else None,
        )
    except ModelRouterError as exc:
        logger.error("all model providers failed: %s", exc)
        return {
            "document_draft": None,
            "reply": (
                "I could not reach any approved model provider to draft this document "
                "right now. Please try again shortly."
            ),
            "provider_used": None,
            "errors": state.get("errors", []) + [f"draft: {exc}"],
        }

    tool_calls = getattr(result, "tool_calls", None) or []
    image_call = next((tc for tc in tool_calls if tc.get("name") == "generate_image"), None)
    if image_call:
        # ADR-0415: arkos's draft is the document body itself
        # (document_draft, not reply) - the shared helper's own reply/
        # provider_used/generated_images result is remapped onto that
        # field here rather than reused verbatim.
        resolved = await _resolve_image_generation_call(
            state, _ARKOS, task, turn_messages, result, image_call, provider,
        )
        return {
            "document_draft": resolved.get("reply"),
            "provider_used": resolved.get("provider_used"),
            **({"errors": resolved["errors"]} if "errors" in resolved else {}),
            **({"generated_images": resolved["generated_images"]} if "generated_images" in resolved else {}),
        }

    draft_text = result.content if hasattr(result, "content") else str(result)
    return {"document_draft": draft_text, "provider_used": provider.name}


async def reflect_node(state: AgentState) -> Dict[str, Any]:
    """ADR-0416: a self-review/refinement pass over draft_node's output -
    reads and writes only `document_draft` (Arkos's own already-generated
    prose), never `retrieved_docs`/the Confluence tool result draft_node
    was grounded in. That narrow scope is what makes it safe to evaluate
    at a fixed classification ceiling below (ADR-0419: declared as this
    task's `reflect` prompt slot, `_REFLECT_CLASSIFICATION_CEILING` -
    "C2" today, see agents/arkos/tasks/draft-architecture-testimonial.md),
    the same scoped-exception pattern ADR-0415 established for
    generate_image: that call's payload is also a short agent-authored
    string rather than raw source material, so it can be evaluated below
    the turn's own effective_classification without the genuinely
    C3-classified source content this turn may have touched ever entering
    the call.

    Still honors `local_only_required` (ADR-0035) unconditionally - that
    flag means a source explicitly forbids ITS OWN influence from
    reaching any external model, and the draft may already have been
    shaped by that source's content. The ceiling below overrides
    classification ESCALATION only (state's `effective_classification`,
    which for Arkos starts at its C3 seed and only ever climbs, ADR-0034);
    it never overrides this separate source-level restriction.

    Tagged "zuno-internal" (ADR-0215) for the same reason
    app/graph/history.py:compact is: this is a second nested chat-model
    call inside the same graph run draft_node's own call already made -
    app/main.py's `_stream_chat` forwards every `on_chat_model_stream`
    event unless tagged, so without this the user would see the original
    draft stream in full, then this call's refined version stream in
    full again right after it, concatenated into one message.
    """
    draft = state.get("document_draft")
    if not draft:
        return {}

    task = _active_task(state)
    reflect_ceiling, reflect_prompt = _active_reflect(state)
    system = SystemMessage(content=reflect_prompt)
    human = HumanMessage(content=draft)

    local_only = state.get("local_only_required", False) or _ARKOS.local_only
    try:
        result, provider = await _model_router.invoke_with_fallback(
            # ADR-0416/ADR-0419/ADR-0514: fixed ceiling for this call
            # only - see the docstring above for why that's safe here.
            classification=reflect_ceiling,
            messages=[system, human],
            bearer_token=state["bearer_token"],
            local_only=local_only,
            request_id=state.get("request_id"),
            agent_name=_ARKOS.name,
            task_name=task.name,
            tags=["zuno-internal"],
        )
    except ModelRouterError as exc:
        logger.warning("reflection pass failed, keeping the original draft: %s", exc)
        return {"errors": state.get("errors", []) + [f"reflect: {exc}"]}

    refined = result.content if hasattr(result, "content") else str(result)
    return {"document_draft": refined, "provider_used": provider.name}


def _citations(state: AgentState):
    citations = [{"source": doc["source"], "title": doc["title"]} for doc in state.get("retrieved_docs", [])]
    confluence = state.get("tool_results", {}).get("confluence.page.search")
    if confluence:
        for item in confluence.get("result", {}).get("results", []):
            citations.append({"source": item.get("url", "confluence"), "title": item["title"]})
    return citations


def _compute_source_mode(state: AgentState) -> str:
    used_indexed = bool(state.get("retrieved_docs"))
    confluence = state.get("tool_results", {}).get("confluence.page.search") or {}
    used_live = bool(confluence.get("result", {}).get("results"))
    if used_indexed and used_live:
        return "both"
    if used_live:
        return "live"
    if used_indexed:
        return "indexed"
    return "none"


def _drive_result_url(result: Dict[str, Any]) -> Optional[str]:
    payload = result.get("result") if isinstance(result.get("result"), dict) else result
    return payload.get("url") if isinstance(payload, dict) else None


async def write_node(state: AgentState) -> Dict[str, Any]:
    """Persists the draft to Google Drive via the MCP Gateway's delegated
    drive.document.create capability (ADR-0208 delegated-user auth) - the
    step with no equivalent in Tekos's shape at all, satisfying ADR-0326's
    "delegated Google Drive/Docs write" completion-pattern bullet.
    """
    task = _active_task(state)
    draft = state.get("document_draft")
    citations = _citations(state)
    source_mode = _compute_source_mode(state)
    if not draft:
        # draft_node already recorded why (provider failure) and set its
        # own `reply` - nothing to write, and writing an empty/failed
        # draft would be worse than a visible failure.
        return {"citations": citations, "source_mode": source_mode}

    plan = state.get("doc_plan") or {}
    # ADR-0034: Drive is a C1-classified sink (policies/tools/
    # tool-policy.yaml), but the write must never downgrade what retrieval
    # already escalated to.
    escalated = _escalate(state.get("effective_classification", ARKOS_BASE_CLASSIFICATION), "C1")
    try:
        result = await invoke_tool(
            tool_name="drive.document.create",
            arguments={"title": plan.get("doc_title", "Untitled"), "content": draft},
            bearer_token=state["bearer_token"],
            data_classification=escalated,
            agent_name=_ARKOS.name,
            task_name=task.name,
        )
    except McpClientError as exc:
        logger.warning("Drive write failed, returning the draft inline instead: %s", exc)
        return {
            "reply": draft,
            "citations": citations,
            "source_mode": source_mode,
            "errors": state.get("errors", []) + [f"write: {exc}"],
        }

    doc_url = _drive_result_url(result)
    if doc_url:
        reply = f'Drafted "{plan.get("doc_title", "Untitled")}" - saved to Drive: {doc_url}'
    else:
        reply = f'Drafted "{plan.get("doc_title", "Untitled")}" (Drive did not return a URL):\n\n{draft}'

    return {
        "reply": reply,
        "citations": citations,
        "drive_doc_url": doc_url,
        "source_mode": source_mode,
    }
