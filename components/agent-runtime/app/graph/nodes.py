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

# technical-docs is C1 per policies/data-classification/classification.yaml
# (Track B). Tekos's brief (MEMORY.md section 9) is grounded strictly in
# official/internal technical documentation, so C1 is the correct default
# for both the reasoning model call and the MCP tool call below.
TEKOS_DATA_CLASSIFICATION = "C1"
RAG_TOP_K = 5

_model_router = ModelRouter()


async def retrieve_node(state: AgentState) -> Dict[str, Any]:
    """Calls rag-service for technical documents relevant to the question."""
    try:
        docs = await search(query=state["message"], top_k=RAG_TOP_K)
    except RagClientError as exc:
        logger.warning("rag-service search failed, continuing without retrieved context: %s", exc)
        return {"retrieved_docs": [], "errors": state.get("errors", []) + [f"retrieve: {exc}"]}
    return {"retrieved_docs": docs}


def should_call_tools(state: AgentState) -> str:
    """Conditional edge selector: decides whether the tool_call node runs."""
    if _TOOL_TRIGGER_PATTERN.search(state.get("message", "")):
        return "tool_call"
    return "reason"


async def tool_call_node(state: AgentState) -> Dict[str, Any]:
    """Calls the MCP Gateway for search_confluence when the question looks
    like it needs live/internal context beyond the static RAG corpus.
    """
    try:
        result = await invoke_tool(
            tool_name="search_confluence",
            arguments={"query": state["message"]},
            bearer_token=state["bearer_token"],
            data_classification=TEKOS_DATA_CLASSIFICATION,
        )
        return {"tool_results": {"search_confluence": result}}
    except McpClientError as exc:
        logger.warning("MCP Gateway tool call failed, continuing without live tool context: %s", exc)
        return {"tool_results": {}, "errors": state.get("errors", []) + [f"tool_call: {exc}"]}


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
    """Calls the routed model (local vLLM InferenceService by default,
    falling back through the approved SaaS providers per ADR-0020/0021).
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

    try:
        result, provider = await _model_router.invoke_with_fallback(
            classification=TEKOS_DATA_CLASSIFICATION, messages=[system, human]
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
