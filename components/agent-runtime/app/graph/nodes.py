"""LangGraph nodes for the Tekos workflow: retrieve -> tool-call (conditional)
-> reason -> respond (ADR-0018).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from app.clients.mcp_client import McpClientError, invoke_tool
from app.clients.model_router import ModelRouter, ModelRouterError
from app.clients.rag_client import RagClientError, search
from app.graph.state import AgentState
from app.knowledge import KnowledgePolicyStore, evaluate_knowledge
from app.registry import AgentRegistry

logger = logging.getLogger("agent_runtime.graph")

# ADR-0039: this is the "GraphFactory" input for v0 - a single registry
# lookup replacing the hardcoded classification/RAG-top-k/prompt constants
# this module used to define directly. There is exactly one graph shape in
# v0 (see app/graph/build.py), so "selecting" a graph is degenerate today;
# what ADR-0039 actually buys is that every value below now comes from
# agents/tekos/{agent.okf.md,tasks/*.md,prompts/*.md} (ADR-0038) rather than
# Python source - changing the bundle changes runtime behavior with no code
# change (see components/agent-runtime/tests/test_registry.py).
_registry = AgentRegistry()
if _registry.load_errors:
    raise RuntimeError(f"agent-runtime: failed to load OKF bundles: {_registry.load_errors}")
_TEKOS = _registry.get("tekos")
if _TEKOS is None:
    raise RuntimeError("agent-runtime: no 'tekos' agent bundle found under AGENTS_DIR")
_ANSWER_TASK = _TEKOS.tasks.get("answer-technical-question")
if _ANSWER_TASK is None or not _ANSWER_TASK.prompt:
    raise RuntimeError(
        "agent-runtime: tekos's 'answer-technical-question' task or its prompt file is missing"
    )

# The chat endpoint (POST /v1/agents/tekos/chat) always executes this one
# task in v0 - Tekos's other two declared tasks (find-relevant-docs,
# check-my-drive-docs) have no dedicated route yet (v1 scope, see
# agents/tekos/tasks/*.md).
_TOOL_TRIGGER_PATTERN = re.compile(
    r"\b(confluence|latest|recent|current|up.?to.?date|internal doc(?:ument)?s?)\b",
    re.IGNORECASE,
)

# ADR-0205/WP-24: domains whose current-state-read freshness window is
# tight enough (knowledge/<domain>/domain.yaml's freshness.
# operation_classes.current-state-read.max_staleness) that ANY retrieval
# from them should prefer/add a live capability call, regardless of
# whether the specific chunk retrieved happens to be individually stale -
# "policy-marked freshness-sensitive source" (ADR-0205's live-read
# trigger). A human-maintained mirror of that descriptor field, the same
# pattern rag-ingestion's STALE_AFTER chart value already established
# (this runtime does not mount knowledge/ at runtime, only
# policies/knowledge/knowledge-policy.yaml - see app/knowledge.py).
_FRESHNESS_SENSITIVE_DOMAINS = {"knowledge.sales"}

# Mirrors policies/data-classification/classification.yaml's data_domains
# (Track B is the source of truth; these are not independently authored
# here - see that file's comments for the full policy). ADR-0034: the
# effective classification for a turn is the highest of every contributing
# source, never a static per-agent constant - retrieve_node seeds it at the
# agent's OKF-declared baseline (technical-docs, RAG's only domain today),
# and tool_call_node escalates it when a higher-classified source
# (Confluence) is touched. ADR-0035: Confluence is additionally
# source-restricted to local-only inference regardless of C2's own broader
# SaaS-eligibility - see policies/tools/tool-policy.yaml's
# external_model_policy field, echoed back by the MCP Gateway's invoke
# response rather than duplicated here.
TEKOS_BASE_CLASSIFICATION = _TEKOS.preferred_classification  # technical-docs, from agent.okf.md
CONFLUENCE_CLASSIFICATION = "C2"  # confluence - a data-domain classification, not an OKF field
RAG_TOP_K = _TEKOS.rag_top_k  # from agent.okf.md's zuno.rag.top_k

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
_knowledge_store = KnowledgePolicyStore()

# ADR-0046: "Similarity alone can return an incorrect OpenShift version
# even when the user names a version" - these deterministic pre-ranking
# filters (rag-service's app/search.py:_filter_clause) only trigger when
# the question actually names a product/version; order matters, since
# "OpenShift AI 3.5" must match the more specific pattern before the bare
# "OpenShift" one gets a chance to (it wouldn't anyway - "ai" isn't a
# digit - but checking the specific pattern first keeps that guarantee
# explicit rather than incidental).
_PRODUCT_VERSION_PATTERNS: Tuple[Tuple[Any, str], ...] = (
    (re.compile(r"\b(?:openshift\s*ai|rhoai)\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE), "openshift-ai"),
    (re.compile(r"\bopenshift\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE), "openshift"),
)


def _extract_product_version(message: str) -> Tuple[Optional[str], Optional[str]]:
    for pattern, product in _PRODUCT_VERSION_PATTERNS:
        match = pattern.search(message)
        if match:
            return product, match.group(1)
    return None, None


# A soft ranking preference (rag-service's app/search.py:_LANGUAGE_BOOST),
# not a hard filter - a light heuristic (accented characters or a handful
# of common French question words) is good enough for that; returning None
# rather than defaulting to "en" when uncertain avoids boosting English
# results for a genuinely ambiguous short message.
_FRENCH_INDICATOR_PATTERN = re.compile(
    r"[éèêàçôûîï]|\b(quel|quelle|comment|pourquoi|configurer|dimensionner|réseau)\b",
    re.IGNORECASE,
)


def _detect_language(message: str) -> Optional[str]:
    return "fr" if _FRENCH_INDICATOR_PATTERN.search(message) else None


async def retrieve_node(state: AgentState) -> Dict[str, Any]:
    """Calls rag-service for technical documents relevant to the question.

    ADR-0046: detects a named product/version in the question (a
    deterministic pre-ranking filter) and a French-language hint (a soft
    ranking preference), and forwards the caller's groups so rag-service
    can enforce ACL-restricted documents server-side rather than trusting
    an already-filtered response. effective_classification is now the
    highest classification among the retrieved docs themselves (ADR-0034),
    replacing the previous fixed C1 baseline - rag-service didn't carry
    per-document classification metadata before this ADR, so every
    retrieved doc really was C1 by construction; that's no longer true.

    ADR-0203: before calling rag-service at all, evaluates the fail-closed
    knowledge-domain intersection (agent ceiling x this task's own
    allowed_knowledge x caller groups x knowledge-policy.yaml) and only
    retrieves from the domains that pass. If nothing is authorized, this
    skips the rag-service call entirely rather than making an unscoped
    request - the same "no widening" posture tool_call_node already applies
    to search_confluence, one layer up (a full policy-evaluation function
    here, not just a local declaration check, since there is no MCP Gateway
    between this runtime and rag-service to enforce it centrally).
    """
    product, version = _extract_product_version(state["message"])
    language = _detect_language(state["message"])
    caller_groups = state.get("groups", [])

    decision = evaluate_knowledge(
        store=_knowledge_store,
        agent_declared=_TEKOS.declared_knowledge(),
        task_allowed=_ANSWER_TASK.allowed_knowledge,
        caller_groups=caller_groups,
    )
    if not decision.authorized_domains:
        logger.warning(
            "no knowledge domain authorized for this call, skipping retrieval: %s", decision.denied
        )
        return {
            "retrieved_docs": [],
            "effective_classification": TEKOS_BASE_CLASSIFICATION,
            "errors": state.get("errors", []) + [f"retrieve: no authorized knowledge domain ({decision.denied})"],
        }

    try:
        docs = await search(
            query=state["message"],
            top_k=RAG_TOP_K,
            product=product,
            version=version,
            language=language,
            caller_groups=caller_groups,
            domains=decision.authorized_domains,
            # ADR-0202/WP-22: _extract_product_version's values ("openshift",
            # "openshift-ai") ARE canonical technology_vocabulary entries
            # (knowledge/tech/domain.yaml), so the same detection doubles as
            # the cross-source technology filter that matches web AND
            # Confluence chunks - the per-source `product` vocabulary never
            # did (its deprecation as a filter key is flagged for v0.3).
            technology=product,
        )
    except RagClientError as exc:
        logger.warning("rag-service search failed, continuing without retrieved context: %s", exc)
        return {
            "retrieved_docs": [],
            "effective_classification": TEKOS_BASE_CLASSIFICATION,
            "errors": state.get("errors", []) + [f"retrieve: {exc}"],
        }

    effective_classification = TEKOS_BASE_CLASSIFICATION
    for doc in docs:
        effective_classification = _escalate(effective_classification, doc.get("classification", "C1"))

    return {"retrieved_docs": docs, "effective_classification": effective_classification}


def _live_read_trigger_reason(state: AgentState) -> Optional[str]:
    """ADR-0205/WP-24 live-read trigger: any ONE of (1) an explicit user
    current-state ask, (2) a policy-marked freshness-sensitive domain
    among the retrieved docs, or (3) a retrieved doc whose stale_after has
    already been exceeded, is enough to prefer/add a live capability call
    over indexed retrieval alone. Returns the reason (for tracing and
    "no silent substitution" - state.live_read_trigger_reason records
    this even when tool_call_node then finds no live capability actually
    available) or None when nothing triggers.
    """
    if _TOOL_TRIGGER_PATTERN.search(state.get("message", "")):
        return "explicit current-state question"
    for doc in state.get("retrieved_docs", []):
        domain = doc.get("domain")
        if domain in _FRESHNESS_SENSITIVE_DOMAINS:
            return f"retrieved from freshness-sensitive domain '{domain}'"
        if doc.get("stale"):
            return f"retrieved document '{doc.get('source')}' exceeded its freshness window"
    return None


def should_call_tools(state: AgentState) -> str:
    """Conditional edge selector: decides whether the tool_call node runs."""
    if _live_read_trigger_reason(state) is not None:
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

    ADR-0036: the MCP Gateway now enforces the agent_declaration and
    task_rights factors of the ADR-0011 intersection using the same OKF
    bundle this runtime resolves (agents/tekos/tasks/answer-technical-question.md
    declares search_confluence, see _ANSWER_TASK above) - invoke_tool below
    declares this call as agent=tekos, task=answer-technical-question so the
    gateway can check it. This node also checks its own copy of that same
    declaration first: if a future bundle edit ever drops search_confluence
    from the task, this degrades to "no tool context" locally instead of
    making a call the gateway would deny anyway.
    """
    # ADR-0205/WP-24: recorded regardless of what follows - "no silent
    # substitution" means the trace/state always shows WHY a live call was
    # attempted, even if (as below) it then turns out no live capability
    # is actually available for this turn.
    trigger_reason = _live_read_trigger_reason(state)

    if "search_confluence" not in _ANSWER_TASK.allowed_tools:
        logger.warning("search_confluence is not in tekos's answer-technical-question.allowed_tools; skipping tool call")
        return {"tool_results": {}, "live_read_trigger_reason": trigger_reason}

    escalated = _escalate(
        state.get("effective_classification", TEKOS_BASE_CLASSIFICATION), CONFLUENCE_CLASSIFICATION
    )
    try:
        result = await invoke_tool(
            tool_name="search_confluence",
            arguments={"query": state["message"]},
            bearer_token=state["bearer_token"],
            data_classification=escalated,
            agent_name=_TEKOS.name,
            task_name=_ANSWER_TASK.name,
        )
    except McpClientError as exc:
        logger.warning("MCP Gateway tool call failed, continuing without live tool context: %s", exc)
        return {
            "tool_results": {},
            "errors": state.get("errors", []) + [f"tool_call: {exc}"],
            "live_read_trigger_reason": trigger_reason,
        }

    allow_external_context = result.get("external_model_policy", {}).get("allow_context", True)
    update: Dict[str, Any] = {
        "tool_results": {"search_confluence": result},
        "effective_classification": escalated,
        "live_read_trigger_reason": trigger_reason,
    }
    if not allow_external_context:
        update["local_only_required"] = True
    return update


def _build_context_block(state: AgentState) -> str:
    parts = []
    for doc in state.get("retrieved_docs", []):
        # ADR-0046: surface version/staleness in the context itself, not
        # just in the API response - the model needs this to actually
        # prefer the correct version's guidance (this ADR's whole point)
        # rather than silently blending conflicting-version snippets.
        tags = []
        if doc.get("version"):
            tags.append(f"version {doc['version']}")
        if doc.get("stale"):
            tags.append("stale/superseded - prefer a newer source if one is present")
        tag_suffix = f" [{', '.join(tags)}]" if tags else ""
        parts.append(f"[{doc['title']}]{tag_suffix} ({doc['source']})\n{doc.get('snippet', '')}")

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

    ADR-0039: the system prompt comes from
    agents/tekos/prompts/answer-technical-question.md (_ANSWER_TASK.prompt,
    resolved by AgentRegistry) rather than a Python string literal - editing
    that file changes Tekos's persona/instructions with no source change.
    """
    context = _build_context_block(state)
    system = SystemMessage(content=_ANSWER_TASK.prompt)
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


def _compute_source_mode(state: AgentState) -> str:
    """ADR-0205 acceptance: "traces show whether a response used indexed
    knowledge, live verification, or both" - computed from what actually
    ended up contributing to this answer (non-empty retrieved_docs /
    non-empty live tool results), never from whether a live call was
    merely attempted (state.live_read_trigger_reason covers that
    separately) - "no silent substitution" means the two must never be
    conflated."""
    used_indexed = bool(state.get("retrieved_docs"))
    confluence = state.get("tool_results", {}).get("search_confluence") or {}
    used_live = bool(confluence.get("result", {}).get("results"))
    if used_indexed and used_live:
        return "both"
    if used_live:
        return "live"
    if used_indexed:
        return "indexed"
    return "none"


async def respond_node(state: AgentState) -> Dict[str, Any]:
    """Assembles the final `{reply, citations, source_mode}` contract from
    retrieved docs and any live tool results, de-duplicated.
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

    return {"citations": deduped, "source_mode": _compute_source_mode(state)}
