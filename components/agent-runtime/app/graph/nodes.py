"""LangGraph nodes for the retrieve_reason_respond shape: retrieve ->
tool-call (conditional) -> reason -> respond (ADR-0018).

ADR-0342/WP-33: `retrieve_node`/`tool_call_node`/`reason_node` are now
factory-produced closures parameterized by `(agent, task)` rather than
module-level functions hardcoded to Tekos - this is what lets a second
agent (Comage) genuinely REUSE this shape (not just its topology) with
its own OKF bundle, proving ADR-0342's "config-only switching" claim for
real. `should_call_tools`/`respond_node` and every helper below them were
already agent-agnostic and are unchanged. The module-level
`retrieve_node`/`tool_call_node`/`reason_node`/`_TEKOS`/`_ANSWER_TASK`/
`TEKOS_BASE_CLASSIFICATION`/`RAG_TOP_K` names below remain bound to Tekos
specifically, for backward compatibility with existing imports/tests -
app/graph/shapes/retrieve_reason_respond.py's `build()` calls the
`_make_*` factories directly with whichever agent/task it's building for.
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
from app.knowledge import KnowledgePolicyStore, resolve_authorized_domains
from app.registry import AgentDefinition, AgentRegistry, TaskDefinition

logger = logging.getLogger("agent_runtime.graph")

# ADR-0039: this is the "GraphFactory" input for v0 - a single registry
# lookup replacing the hardcoded classification/RAG-top-k/prompt constants
# this module used to define directly. What ADR-0039 buys is that every
# value below now comes from agents/tekos/{agent.okf.md,tasks/*.md,
# prompts/*.md} (ADR-0038) rather than Python source - changing the
# bundle changes runtime behavior with no code change (see
# components/agent-runtime/tests/test_registry.py).
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
# ADR-0326/WP-33: knowledge.sales is Comage's own freshness-sensitive
# domain, exercised for real by this shape now that Comage reuses it.
_FRESHNESS_SENSITIVE_DOMAINS = {"knowledge.sales"}

# Mirrors policies/data-classification/classification.yaml's data_domains
# (Track B is the source of truth; these are not independently authored
# here - see that file's comments for the full policy). ADR-0034: the
# effective classification for a turn is the highest of every contributing
# source, never a static per-agent constant - retrieve_node seeds it at the
# agent's OKF-declared baseline, and tool_call_node escalates it when a
# higher-classified source (Confluence, Salesforce, ...) is touched.
# ADR-0035: some live-read sources (Confluence) are additionally
# source-restricted to local-only inference regardless of C2's own broader
# SaaS-eligibility - see policies/tools/tool-policy.yaml's
# external_model_policy field, echoed back by the MCP Gateway's invoke
# response rather than duplicated here.
TEKOS_BASE_CLASSIFICATION = _TEKOS.preferred_classification  # technical-docs, from agent.okf.md
# ADR-0342/WP-33: every live-read tool_call_node might invoke today
# (Confluence, Salesforce) happens to be C2 in
# policies/data-classification/classification.yaml - a reasonable
# pre-escalation heuristic before the call, NOT the actual enforcement
# (tool-policy.yaml's own min_classification per capability is the real
# boundary, checked server-side by the MCP Gateway regardless of what this
# node assumes). A future live-read source classified C3 would need this
# revisited.
_LIVE_READ_CLASSIFICATION = "C2"
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


def _make_retrieve_node(agent: AgentDefinition, task: TaskDefinition):
    """Builds a retrieve_node closure bound to one agent/task pair. Calls
    rag-service for documents relevant to the question.

    ADR-0046: detects a named product/version in the question (a
    deterministic pre-ranking filter) and a French-language hint (a soft
    ranking preference), and forwards the caller's groups so rag-service
    can enforce ACL-restricted documents server-side rather than trusting
    an already-filtered response. effective_classification is the highest
    classification among the retrieved docs themselves (ADR-0034).

    ADR-0203: before calling rag-service at all, evaluates the fail-closed
    knowledge-domain intersection (agent ceiling x this task's own
    allowed_knowledge x caller groups x knowledge-policy.yaml) and only
    retrieves from the domains that pass. If nothing is authorized, this
    skips the rag-service call entirely rather than making an unscoped
    request - the same "no widening" posture tool_call_node already applies
    to search_confluence, one layer up.
    """
    base_classification = agent.preferred_classification
    rag_top_k = agent.rag_top_k

    async def retrieve_node(state: AgentState) -> Dict[str, Any]:
        product, version = _extract_product_version(state["message"])
        language = _detect_language(state["message"])
        caller_groups = state.get("groups", [])
        project_id = state.get("project_id")

        decision = resolve_authorized_domains(
            store=_knowledge_store,
            agent_declared=agent.declared_knowledge(),
            task_allowed=task.allowed_knowledge,
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
                "effective_classification": base_classification,
                "errors": state.get("errors", []) + [f"retrieve: no authorized knowledge domain ({decision.denied})"],
            }

        try:
            docs = await search(
                query=state["message"],
                top_k=rag_top_k,
                product=product,
                version=version,
                language=language,
                caller_groups=caller_groups,
                domains=authorized_domains,
                # ADR-0202/WP-22: _extract_product_version's values ("openshift",
                # "openshift-ai") ARE canonical technology_vocabulary entries
                # (knowledge/tech/domain.yaml), so the same detection doubles as
                # the cross-source technology filter that matches web AND
                # Confluence chunks - the per-source `product` vocabulary never
                # did (its deprecation as a filter key is flagged for v0.3).
                technology=product,
                project_id=project_id,
                caller_sub=state.get("user_sub"),
            )
        except RagClientError as exc:
            logger.warning("rag-service search failed, continuing without retrieved context: %s", exc)
            return {
                "retrieved_docs": [],
                "effective_classification": base_classification,
                "errors": state.get("errors", []) + [f"retrieve: {exc}"],
            }

        effective_classification = base_classification
        for doc in docs:
            effective_classification = _escalate(effective_classification, doc.get("classification", "C1"))

        return {"retrieved_docs": docs, "effective_classification": effective_classification}

    return retrieve_node


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
    """Conditional edge selector: decides whether the tool_call node runs.
    Agent-agnostic - reads only accumulated state, never a specific
    agent's declarations."""
    if _live_read_trigger_reason(state) is not None:
        return "tool_call"
    return "reason"


def _make_tool_call_node(agent: AgentDefinition, task: TaskDefinition):
    """Builds a tool_call_node closure bound to one agent/task pair. Calls
    the MCP Gateway for `task.live_read_tool` (ADR-0342/WP-33: e.g.
    Tekos's confluence.page.search, Comage's Salesforce read - explicit
    per-task configuration, never inferred) when the question looks like
    it needs live/internal context beyond the static RAG corpus.

    The outgoing X-Zuno-Data-Classification is escalated to
    _LIVE_READ_CLASSIFICATION *before* the call - the tool's own
    min_classification (tool-policy.yaml) requires at least that, so a
    stale lower declaration would simply be denied. On success, this node
    also escalates effective_classification for every later step (the
    reason node's model call) and honors the gateway's
    external_model_policy.allow_context verdict by forcing local-only
    inference for the rest of this turn when it's false.

    ADR-0036: the MCP Gateway enforces the agent_declaration and
    task_rights factors of the ADR-0011 intersection using the same OKF
    bundle this runtime resolves - invoke_tool below declares this call as
    this agent/task so the gateway can check it. This node also checks its
    own copy of that same declaration first: if a future bundle edit ever
    drops the live-read tool from the task (or unsets live_read_tool
    entirely), this degrades to "no tool context" locally instead of
    making a call the gateway would deny anyway.
    """
    base_classification = agent.preferred_classification
    live_read_tool = task.live_read_tool

    async def tool_call_node(state: AgentState) -> Dict[str, Any]:
        # ADR-0205/WP-24: recorded regardless of what follows - "no silent
        # substitution" means the trace/state always shows WHY a live call was
        # attempted, even if (as below) it then turns out no live capability
        # is actually available for this turn.
        trigger_reason = _live_read_trigger_reason(state)

        if not live_read_tool or live_read_tool not in task.allowed_tools:
            logger.warning(
                "%s's %s declares no usable live_read_tool; skipping tool call", agent.name, task.name
            )
            return {"tool_results": {}, "live_read_trigger_reason": trigger_reason}

        escalated = _escalate(
            state.get("effective_classification", base_classification), _LIVE_READ_CLASSIFICATION
        )
        try:
            result = await invoke_tool(
                tool_name=live_read_tool,
                arguments={"query": state["message"]},
                bearer_token=state["bearer_token"],
                data_classification=escalated,
                agent_name=agent.name,
                task_name=task.name,
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
            "tool_results": {live_read_tool: result},
            "effective_classification": escalated,
            "live_read_trigger_reason": trigger_reason,
        }
        if not allow_external_context:
            update["local_only_required"] = True
        return update

    return tool_call_node


def _live_read_result(state: AgentState) -> Optional[Dict[str, Any]]:
    """`tool_call_node` stores at most one entry in `tool_results`, keyed
    by whichever tool `task.live_read_tool` names (`search_confluence` for
    Tekos, `salesforce.opportunity.read` for Comage - see that node) - so
    reading "the one value present, whatever its key" is what keeps this
    helper and its two callers below agent-agnostic without themselves
    needing an (agent, task) closure. Every live_read_tool binding returns
    the same search_pages-shaped contract (`{query, results: [{title,
    url, excerpt}], count}`, ADR-0326/WP-33) precisely so this holds."""
    tool_results = state.get("tool_results", {})
    return next(iter(tool_results.values()), None)


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

    live_result = _live_read_result(state)
    if live_result:
        for item in live_result.get("result", {}).get("results", []):
            parts.append(f"[Live: {item['title']}] ({item.get('url', '')})\n{item.get('excerpt', '')}")

    return "\n\n---\n\n".join(parts) if parts else "(no supporting context retrieved)"


def _make_reason_node(agent: AgentDefinition, task: TaskDefinition):
    """Builds a reason_node closure bound to one agent/task pair. Calls the
    AI Inference Gateway (components/ai-gateway, ADR-0009), which resolves
    the local vLLM model first, falling back through the approved SaaS
    providers per ADR-0020/0021 -- this node itself no longer makes that
    routing decision.

    Uses the turn's aggregated effective_classification (ADR-0034) rather
    than a static constant, and forces local-only inference (ADR-0035) when
    a source-restricted result (e.g. Confluence) was folded into context
    this turn - see tool_call_node.

    ADR-0039: the system prompt comes from this task's own prompt file
    (task.prompt, resolved by AgentRegistry) rather than a Python string
    literal - editing that file changes the agent's persona/instructions
    with no source change.
    """
    base_classification = agent.preferred_classification

    async def reason_node(state: AgentState) -> Dict[str, Any]:
        context = _build_context_block(state)
        system = SystemMessage(content=task.prompt)
        human = HumanMessage(content=f"Context:\n{context}\n\nQuestion: {state['message']}")

        classification = state.get("effective_classification", base_classification)
        local_only = state.get("local_only_required", False)
        try:
            result, provider = await _model_router.invoke_with_fallback(
                classification=classification,
                messages=[system, human],
                bearer_token=state["bearer_token"],
                local_only=local_only,
                request_id=state.get("request_id"),
                agent_name=agent.name,
                task_name=task.name,
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

    return reason_node


def _compute_source_mode(state: AgentState) -> str:
    """ADR-0205 acceptance: "traces show whether a response used indexed
    knowledge, live verification, or both" - computed from what actually
    ended up contributing to this answer (non-empty retrieved_docs /
    non-empty live tool results), never from whether a live call was
    merely attempted (state.live_read_trigger_reason covers that
    separately) - "no silent substitution" means the two must never be
    conflated. Agent-agnostic."""
    used_indexed = bool(state.get("retrieved_docs"))
    live_result = _live_read_result(state) or {}
    used_live = bool(live_result.get("result", {}).get("results"))
    if used_indexed and used_live:
        return "both"
    if used_live:
        return "live"
    if used_indexed:
        return "indexed"
    return "none"


async def respond_node(state: AgentState) -> Dict[str, Any]:
    """Assembles the final `{reply, citations, source_mode}` contract from
    retrieved docs and any live tool results, de-duplicated. Agent-agnostic
    - reads only accumulated state.
    """
    citations = [
        {"source": doc["source"], "title": doc["title"]} for doc in state.get("retrieved_docs", [])
    ]
    live_result = _live_read_result(state)
    if live_result:
        for item in live_result.get("result", {}).get("results", []):
            citations.append({"source": item.get("url") or "live-read", "title": item["title"]})

    seen = set()
    deduped = []
    for citation in citations:
        key = (citation["source"], citation["title"])
        if key not in seen:
            seen.add(key)
            deduped.append(citation)

    return {"citations": deduped, "source_mode": _compute_source_mode(state)}


# Backward-compatible module-level names, bound to Tekos specifically -
# app/graph/shapes/retrieve_reason_respond.py's build() calls the _make_*
# factories directly (with whichever agent/task it's building a graph
# for); these three names exist so any other existing import of
# `app.graph.nodes.retrieve_node` etc. (tests, tooling) keeps resolving to
# Tekos's own bound closures unchanged.
retrieve_node = _make_retrieve_node(_TEKOS, _ANSWER_TASK)
tool_call_node = _make_tool_call_node(_TEKOS, _ANSWER_TASK)
reason_node = _make_reason_node(_TEKOS, _ANSWER_TASK)
