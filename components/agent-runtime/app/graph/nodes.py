"""LangGraph nodes for the Tekos workflow: retrieve -> tool-call (conditional)
-> reason -> respond (ADR-0018).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from app.clients.mcp_client import McpClientError, invoke_tool
from app.clients.model_router import ModelRouter, ModelRouterError
from app.clients.rag_client import RagClientError, search
from app.graph.state import AgentState

logger = logging.getLogger("agent_runtime.graph")

# v0 simplification: Tekos's OKF task/tool declaration doesn't exist yet
# (agents/tekos/tasks, agents/tekos/tools are still stubs -- owned by
# Track E). Until that lands, this heuristic decides when a live
# Confluence lookup is worth the extra round trip, standing in for what
# should eventually be an OKF-declared task capability check.
_TOOL_TRIGGER_PATTERN = re.compile(
    r"\b(confluence|latest|recent|current|up.?to.?date|internal doc(?:ument)?s?)\b",
    re.IGNORECASE,
)

# Mirrors policies/data-classification/classification.yaml's data_domains
# (Track B is the source of truth; these are not independently authored
# here - see that file's comments for the full policy). ADR-0034: the
# effective classification for a turn is the highest of every contributing
# source, never a static per-agent constant - retrieve_node seeds it at the
# baseline technical-docs domain (RAG's only domain today), and
# tool_call_node escalates it when a higher-classified source (Confluence)
# is touched. ADR-0035: Confluence is additionally source-restricted to
# local-only inference regardless of C2's own broader SaaS-eligibility -
# see policies/tools/tool-policy.yaml's external_model_policy field, echoed
# back by the MCP Gateway's invoke response rather than duplicated here.
TEKOS_BASE_CLASSIFICATION = "C1"  # technical-docs
CONFLUENCE_CLASSIFICATION = "C2"  # confluence
RAG_TOP_K = 5

_CLASSIFICATION_RANK = {"C1": 1, "C2": 2, "C3": 3}


def _escalate(current: str, candidate: str) -> str:
    """Highest-sensitivity-wins, never downgrades (ADR-0034 Security
    considerations): once a turn's effective classification is raised, no
    later source can lower it back down.
    """
    if _CLASSIFICATION_RANK.get(candidate, 0) > _CLASSIFICATION_RANK.get(current, 0):
        return candidate
    return current


_model_router = ModelRouter()


async def retrieve_node(state: AgentState) -> Dict[str, Any]:
    """Calls rag-service for technical documents relevant to the question.

    Seeds effective_classification at the baseline technical-docs level
    (ADR-0034) - rag-service doesn't carry per-document classification
    metadata yet (that's ADR-0046's scope), and technical-docs is the only
    domain it serves today, so every retrieved doc is C1 by construction.
    """
    try:
        docs = await search(query=state["message"], top_k=RAG_TOP_K)
    except RagClientError as exc:
        logger.warning("rag-service search failed, continuing without retrieved context: %s", exc)
        return {
            "retrieved_docs": [],
            "effective_classification": TEKOS_BASE_CLASSIFICATION,
            "errors": state.get("errors", []) + [f"retrieve: {exc}"],
        }
    return {"retrieved_docs": docs, "effective_classification": TEKOS_BASE_CLASSIFICATION}


def should_call_tools(state: AgentState) -> str:
    """Conditional edge selector: decides whether the tool_call node runs."""
    if _TOOL_TRIGGER_PATTERN.search(state.get("message", "")):
        return "tool_call"
    return "reason"


async def tool_call_node(state: AgentState) -> Dict[str, Any]:
    """Calls the MCP Gateway for search_confluence when the question looks
    like it needs live/internal context beyond the static RAG corpus.

    Confluence is a known C2 source (ADR-0034/0035), so the outgoing
    X-Zuno-Data-Classification is escalated *before* the call - the tool's
    own min_classification (tool-policy.yaml) now requires at least C2, so
    a stale C1 declaration would simply be denied. On success, this node
    also escalates effective_classification for every later step (the
    reason node's model call) and honors the gateway's
    external_model_policy.allow_context verdict by forcing local-only
    inference for the rest of this turn when it's false.
    """
    escalated = _escalate(
        state.get("effective_classification", TEKOS_BASE_CLASSIFICATION), CONFLUENCE_CLASSIFICATION
    )
    try:
        result = await invoke_tool(
            tool_name="search_confluence",
            arguments={"query": state["message"]},
            bearer_token=state["bearer_token"],
            data_classification=escalated,
        )
    except McpClientError as exc:
        logger.warning("MCP Gateway tool call failed, continuing without live tool context: %s", exc)
        return {"tool_results": {}, "errors": state.get("errors", []) + [f"tool_call: {exc}"]}

    allow_external_context = result.get("external_model_policy", {}).get("allow_context", True)
    update: Dict[str, Any] = {
        "tool_results": {"search_confluence": result},
        "effective_classification": escalated,
    }
    if not allow_external_context:
        update["local_only_required"] = True
    return update


def _build_context_block(state: AgentState) -> str:
    parts = []
    for doc in state.get("retrieved_docs", []):
        parts.append(f"[{doc['title']}] ({doc['source']})\n{doc.get('snippet', '')}")

    confluence = state.get("tool_results", {}).get("search_confluence")
    if confluence:
        for item in confluence.get("result", {}).get("results", []):
            parts.append(f"[Confluence: {item['title']}] ({item.get('url', '')})\n{item.get('excerpt', '')}")

    return "\n\n---\n\n".join(parts) if parts else "(no supporting context retrieved)"


async def reason_node(state: AgentState) -> Dict[str, Any]:
    """Calls the AI Inference Gateway (components/ai-gateway, ADR-0009),
    which resolves the local vLLM model first, falling back through the
    approved SaaS providers per ADR-0020/0021 -- this node itself no
    longer makes that routing decision.

    Uses the turn's aggregated effective_classification (ADR-0034) rather
    than a static constant, and forces local-only inference (ADR-0035) when
    a source-restricted result (e.g. Confluence) was folded into context
    this turn - see tool_call_node.
    """
    context = _build_context_block(state)
    system = SystemMessage(
        content=(
            "You are Tekos, Zuno's technical consultant assistant for OpenShift, "
            "Kubernetes and the surrounding Red Hat ecosystem. Answer precisely and "
            "concisely, grounded strictly in the provided context. If the context does "
            "not contain the answer, say so explicitly rather than inventing details."
        )
    )
    human = HumanMessage(content=f"Context:\n{context}\n\nQuestion: {state['message']}")

    classification = state.get("effective_classification", TEKOS_BASE_CLASSIFICATION)
    local_only = state.get("local_only_required", False)
    try:
        result, provider = await _model_router.invoke_with_fallback(
            classification=classification,
            messages=[system, human],
            bearer_token=state["bearer_token"],
            local_only=local_only,
        )
    except ModelRouterError as exc:
        logger.error("all model providers failed: %s", exc)
        return {
            "reply": (
                "I could not reach any approved model provider to answer this question "
                "right now. Please try again shortly."
            ),
            "provider_used": None,
            "errors": state.get("errors", []) + [f"reason: {exc}"],
        }

    reply_text = result.content if hasattr(result, "content") else str(result)
    return {"reply": reply_text, "provider_used": provider.name}


async def respond_node(state: AgentState) -> Dict[str, Any]:
    """Assembles the final `{reply, citations}` contract from retrieved
    docs and any live tool results, de-duplicated.
    """
    citations = [
        {"source": doc["source"], "title": doc["title"]} for doc in state.get("retrieved_docs", [])
    ]
    confluence = state.get("tool_results", {}).get("search_confluence")
    if confluence:
        for item in confluence.get("result", {}).get("results", []):
            citations.append({"source": item.get("url", "confluence"), "title": item["title"]})

    seen = set()
    deduped = []
    for citation in citations:
        key = (citation["source"], citation["title"])
        if key not in seen:
            seen.add(key)
            deduped.append(citation)

    return {"citations": deduped}
