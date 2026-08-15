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
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.clients.mcp_client import McpClientError, invoke_tool
from app.clients.model_router import ModelRouter, ModelRouterError
from app.clients.rag_client import RagClientError, search
from app.graph.nodes import _escalate
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

    if not authorized_domains:
        logger.warning(
            "no knowledge domain authorized for this call, skipping retrieval: %s", decision.denied
        )
        return {
            "retrieved_docs": [],
            "effective_classification": ARKOS_BASE_CLASSIFICATION,
            "errors": state.get("errors", []) + [f"retrieve: no authorized knowledge domain ({decision.denied})"],
        }

    topic = (state.get("doc_plan") or {}).get("topic") or state["message"]
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
        return {
            "retrieved_docs": [],
            "effective_classification": ARKOS_BASE_CLASSIFICATION,
            "errors": state.get("errors", []) + [f"retrieve: {exc}"],
        }

    effective_classification = ARKOS_BASE_CLASSIFICATION
    for doc in docs:
        effective_classification = _escalate(effective_classification, doc.get("classification", "C1"))

    return {"retrieved_docs": docs, "effective_classification": effective_classification}


def _build_context_block(state: AgentState) -> str:
    parts = []
    for doc in state.get("retrieved_docs", []):
        parts.append(f"[{doc['title']}] ({doc['source']})\n{doc.get('snippet', '')}")
    return "\n\n---\n\n".join(parts) if parts else "(no supporting context retrieved)"


async def draft_node(state: AgentState) -> Dict[str, Any]:
    """Calls the AI Inference Gateway to draft the long-form document body
    - the step with no equivalent in Tekos's shape: this produces a full
    document draft that feeds write_node, not a short conversational reply
    that IS the final answer (compare app/graph/nodes.py:reason_node).
    """
    context = _build_context_block(state)
    plan = state.get("doc_plan") or {}
    system = SystemMessage(content=_DRAFT_TASK.prompt)
    human = HumanMessage(
        content=(
            f"Document title: {plan.get('doc_title', 'Untitled')}\n\n"
            f"Context:\n{context}\n\nRequest: {state['message']}"
        )
    )

    classification = state.get("effective_classification", ARKOS_BASE_CLASSIFICATION)
    local_only = state.get("local_only_required", False)
    try:
        result, provider = await _model_router.invoke_with_fallback(
            classification=classification,
            messages=[system, human],
            bearer_token=state["bearer_token"],
            local_only=local_only,
            request_id=state.get("request_id"),
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

    draft_text = result.content if hasattr(result, "content") else str(result)
    return {"document_draft": draft_text, "provider_used": provider.name}


def _citations(state: AgentState):
    return [{"source": doc["source"], "title": doc["title"]} for doc in state.get("retrieved_docs", [])]


def _compute_source_mode(state: AgentState) -> str:
    return "indexed" if state.get("retrieved_docs") else "none"


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
