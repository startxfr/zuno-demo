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
    _escalate,
    _image_generation_declared,
    _resolve_image_generation_call,
)
from app.graph.state import AgentState
from app.knowledge import KnowledgePolicyStore, resolve_authorized_domains
from app.registry import AgentRegistry

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

ARKOS_BASE_CLASSIFICATION = _ARKOS.preferred_classification  # from agent.okf.md's zuno.model
RAG_TOP_K = _ARKOS.rag_top_k or 5  # Arkos declares no zuno.rag block; AgentDefinition defaults to 5

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


def _extract_topic(message: str) -> str:
    match = _TOPIC_PATTERN.search(message)
    if match:
        return match.group(1).strip().rstrip(".")
    return message.strip()


async def plan_node(state: AgentState) -> Dict[str, Any]:
    """Derives what document this turn drafts - a short topic and a
    working title - from the user's message. The full v1 DAT workflow
    (collect -> outline -> explicit user review -> generation -> review ->
    final Google Doc, MEMORY.md section 8) stages this over several
    checkpointed turns with explicit review gates; this task proves the
    plan -> retrieve -> draft -> write shape end to end in one turn - see
    the task file's own scope note.
    """
    topic = _extract_topic(state["message"])
    return {"doc_plan": {"topic": topic, "doc_title": f"DAT - {topic}"}}


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
    caller_groups = state.get("groups", [])
    project_id = state.get("project_id")

    decision = resolve_authorized_domains(
        store=_knowledge_store,
        agent_declared=_ARKOS.declared_knowledge(),
        task_allowed=_DRAFT_TASK.allowed_knowledge,
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

    if "confluence.page.search" not in _DRAFT_TASK.allowed_tools:
        return update

    escalated = _escalate(effective_classification, _LIVE_READ_CLASSIFICATION)
    try:
        result = await invoke_tool(
            tool_name="confluence.page.search",
            arguments={"query": topic},
            bearer_token=state["bearer_token"],
            data_classification=escalated,
            agent_name=_ARKOS.name,
            task_name=_DRAFT_TASK.name,
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
    context = _build_context_block(state)
    plan = state.get("doc_plan") or {}
    summary = state.get("summary", "")
    system_content = _DRAFT_TASK.prompt
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
    local_only = state.get("local_only_required", False)
    # ADR-0415: same declarative gate as app/graph/nodes.py:reason_node.
    image_generation_enabled = _image_generation_declared(_DRAFT_TASK)
    turn_messages: List[Any] = [system, *history_messages, human]
    try:
        result, provider = await _model_router.invoke_with_fallback(
            classification=classification,
            messages=turn_messages,
            bearer_token=state["bearer_token"],
            local_only=local_only,
            request_id=state.get("request_id"),
            agent_name=_ARKOS.name,
            task_name=_DRAFT_TASK.name,
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
            state, _ARKOS, _DRAFT_TASK, turn_messages, result, image_call, provider,
        )
        return {
            "document_draft": resolved.get("reply"),
            "provider_used": resolved.get("provider_used"),
            **({"errors": resolved["errors"]} if "errors" in resolved else {}),
            **({"generated_images": resolved["generated_images"]} if "generated_images" in resolved else {}),
        }

    draft_text = result.content if hasattr(result, "content") else str(result)
    return {"document_draft": draft_text, "provider_used": provider.name}


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
            task_name=_DRAFT_TASK.name,
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
