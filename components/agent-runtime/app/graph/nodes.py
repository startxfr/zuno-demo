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

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.clients.mcp_client import McpClientError, invoke_tool
from app.clients.model_router import ModelRouter, ModelRouterError
from app.clients.rag_client import RagClientError, search
# ADR-0215: _escalate/_CLASSIFICATION_RANK moved to app/graph/
# classification.py (avoids a circular import with app/graph/history.py,
# which needs _escalate too) - imported here under their original names
# so every existing caller of `nodes._escalate`/`nodes._CLASSIFICATION_
# RANK` (app/graph/arkos_nodes.py in particular) keeps working unchanged.
from app.graph.classification import _CLASSIFICATION_RANK, _escalate
from app.graph.history import build_history_messages
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

# ADR-0417: same deterministic keyword/regex style as _TOOL_TRIGGER_PATTERN
# above - a "this turn wants generated code/config, not prose" signal, not
# an LLM classifier call. Shared between Arkos (app/graph/arkos_nodes.py's
# route_after_plan) and Tekos (_make_route_after_retrieval below) rather
# than duplicated, since both agents' coding-request detection is the same
# question asked at a different point in two structurally different
# graphs.
_CODE_TRIGGER_PATTERN = re.compile(
    r"\b(?:write|generate|create)\s+(?:me\s+)?(?:a|an|some)\s+"
    r"(?:python|go|golang|bash|shell|ansible|terraform|helm|yaml|dockerfile|"
    r"kubernetes|k8s|script|snippet|function|program|playbook|manifest|"
    r"module|class|regex|code)\b"
    r"|\b(?:code|script)\s+(?:snippet|example|sample)\b"
    r"|```",
    re.IGNORECASE,
)


def _code_request_trigger_reason(message: str) -> Optional[str]:
    """ADR-0417: returns why this message looks like a coding request, or
    None. A provisional heuristic (like _live_read_trigger_reason's own
    _TOOL_TRIGGER_PATTERN) - expect false negatives/positives, tune from
    real usage rather than trying to enumerate every phrasing up front."""
    if _CODE_TRIGGER_PATTERN.search(message or ""):
        return "message phrasing matched the code-generation trigger pattern"
    return None

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

_model_router = ModelRouter()
_knowledge_store = KnowledgePolicyStore()

# ADR-0415: bound onto the reasoning model via bind_tools() only for a
# task that declares "generate_image" in its own allowed_tools (same
# declarative gate as live_read_tool below - ADR-0011 factor 1), so a task
# never entitled to image generation never even offers the LLM the
# choice. Deliberately narrow parameters (a prompt string, nothing
# structured) - the model composes the visual description itself rather
# than being handed retrieved context to forward, keeping the tool's
# actual input surface small for the ADR's C2 scoped-override reasoning.
_GENERATE_IMAGE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": (
            "Generate an image with stable-diffusion-xl when the user's request or "
            "the surrounding conversation calls for a picture, diagram, illustration "
            "or mockup. Only pass the visual description itself as the prompt - never "
            "paste retrieved document content, citations or conversation history into it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "A concise description of the image to generate.",
                },
                "negative_prompt": {
                    "type": "string",
                    "description": "Optional: elements or qualities to avoid in the image.",
                },
            },
            "required": ["prompt"],
        },
    },
}
# ADR-0415 decision 3: fixed ceiling for this one call type, regardless of
# the calling agent's own ambient classification (arkos/cognos are C3 for
# everything else) - see the ADR's Accepted risks.
_IMAGE_GENERATION_CLASSIFICATION = "C2"


def _image_generation_declared(task: TaskDefinition) -> bool:
    """ADR-0116 migration-alias tolerance (task frontmatter should use the
    canonical `image.generation.create` capability ID; accepting the
    legacy `generate_image` name too costs nothing and matches how
    policies/tools/tool-policy.yaml and platform/bindings/tools/
    tool-bindings.yaml both already answer to either name)."""
    return "image.generation.create" in task.allowed_tools or "generate_image" in task.allowed_tools

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
                version=version,
                language=language,
                caller_groups=caller_groups,
                domains=authorized_domains,
                # ADR-0202/WP-22: _extract_product_version's values ("openshift",
                # "openshift-ai") ARE canonical technology_vocabulary entries
                # (knowledge/tech/domain.yaml), so the same detection doubles as
                # the cross-source technology filter that matches web AND
                # Confluence chunks. The per-source `product` vocabulary never
                # did (rag_ingestion.py tags metadata.product with the raw
                # per-source doc slug, e.g. "red-hat-openshift-ai-self-managed",
                # never this canonical form) - rag-service's product filter has
                # no fallback for a miss (unlike technology's grandfather
                # clause), so passing product= here silently zeroed every RAG
                # result for any message this detection fires on. Deprecated
                # as a filter key per this comment's own prior note (targeted
                # for v0.3) - live-cluster-confirmed 2026-08-22 via tekos
                # scenario 10 (source_mode stuck at "none"), removed now
                # rather than waiting.
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


def _make_route_after_retrieval(agent: AgentDefinition):
    """ADR-0417: 3-way selector extending should_call_tools with a `code`
    branch. Data-driven, not agent-name-hardcoded: only ever returns
    "code" for an agent whose OKF bundle declares a sibling `write-code`
    task (today: only Tekos) - for every agent that doesn't (comage,
    advantage, finage, naveo), this is behaviorally identical to
    should_call_tools, which stays unchanged/untouched for backward
    compatibility (test_freshness_routing.py still exercises it directly).
    Live-read priority is unchanged: an explicit "current/latest" question
    still routes to tool_call even if it also looks like a code request.
    """
    code_declared = "write-code" in agent.tasks

    def route_after_retrieval(state: AgentState) -> str:
        if _live_read_trigger_reason(state) is not None:
            return "tool_call"
        if code_declared and _code_request_trigger_reason(state.get("message", "")) is not None:
            return "code"
        return "reason"

    return route_after_retrieval


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


def _make_code_node(agent: AgentDefinition, task: TaskDefinition):
    """ADR-0417: builds a code_node closure for an agent declaring a
    sibling `write-code` task (today: only Tekos, via
    _make_route_after_retrieval's gate above) - resolved once at
    graph-build time. `task` (this shape's primary task) is accepted only
    for call-site symmetry with the other _make_* factories in this
    module; the resolved write-code task is always used for task_name
    instead. If reached for an agent that doesn't declare it (shouldn't
    happen - the selector above gates this), degrades gracefully rather
    than crashing, the same posture _make_tool_call_node already has for
    a missing live_read_tool.
    """
    code_task = agent.tasks.get("write-code")
    base_classification = agent.preferred_classification

    async def code_node(state: AgentState) -> Dict[str, Any]:
        if code_task is None:
            logger.error("%s: code_node reached with no 'write-code' task declared", agent.name)
            return {"reply": "Code generation is not available for this assistant.", "provider_used": None}

        context = _build_context_block(state)
        system = SystemMessage(content=(
            "You are a coding assistant. The user is asking for code, a "
            "configuration file, or a script - not a narrative answer. "
            "Respond with the requested code in a fenced code block, plus "
            "a brief explanation only if it adds real value. Use the "
            "supporting context below only if directly relevant.\n\n"
            f"Context:\n{context}"
        ))
        human = HumanMessage(content=state["message"])
        classification = state.get("effective_classification", base_classification)
        local_only = state.get("local_only_required", False) or agent.local_only
        try:
            result, provider = await _model_router.invoke_with_fallback(
                classification=classification,
                messages=[system, human],
                bearer_token=state["bearer_token"],
                local_only=local_only,
                request_id=state.get("request_id"),
                agent_name=agent.name,
                task_name=code_task.name,
                # ADR-0511/ADR-0512 (WP-55): only a verified binding may
                # draw project quota - gated on the task's own mark, never
                # on state["project_id"] being merely truthy.
                project_id=state.get("project_id") if code_task.project_required else None,
            )
        except ModelRouterError as exc:
            logger.error("code generation model call failed: %s", exc)
            return {
                "reply": (
                    "I could not reach any approved model provider to generate code "
                    "right now. Please try again shortly."
                ),
                "provider_used": None,
                "errors": state.get("errors", []) + [f"code: {exc}"],
            }

        reply_text = result.content if hasattr(result, "content") else str(result)
        return {"reply": reply_text, "provider_used": provider.name}

    return code_node


def _make_reason_node(agent: AgentDefinition, task: TaskDefinition):
    """Builds a reason_node closure bound to one agent/task pair. Calls the
    AI Inference Gateway (components/ai-gateway, ADR-0009), which resolves
    the local vLLM model first, falling back through the approved SaaS
    providers per ADR-0020/0021 -- this node itself no longer makes that
    routing decision.

    Uses the turn's aggregated effective_classification (ADR-0034) rather
    than a static constant, and forces local-only inference (ADR-0035) when
    a source-restricted result (e.g. Confluence) was folded into context
    this turn - see tool_call_node. Also forces it unconditionally when
    `agent.local_only` is set (ADR-0416, e.g. Finage) - an agent-level
    restriction independent of any single turn's classification or tools.

    ADR-0039: the system prompt comes from this task's own prompt file
    (task.prompt, resolved by AgentRegistry) rather than a Python string
    literal - editing that file changes the agent's persona/instructions
    with no source change.

    ADR-0215: prior turns (app/graph/history.py's `history`/`summary`
    state) are injected between the system message and this turn's own
    human message - the running summary appended to the system prompt as
    delimited background information, verbatim recent turns as proper
    HumanMessage/AIMessage pairs. This turn's own human message keeps its
    exact pre-ADR-0215 shape (`Context:...\\n\\nQuestion:...`), so an agent
    with no history yet (a fresh conversation, or history disabled) sends
    byte-identical messages to before.
    """
    base_classification = agent.preferred_classification
    # ADR-0415: declarative gate, same ADR-0011-factor-1 mechanism
    # live_read_tool already uses - only offered to the LLM when this
    # task's own OKF bundle lists it.
    image_generation_enabled = _image_generation_declared(task)

    async def reason_node(state: AgentState) -> Dict[str, Any]:
        context = _build_context_block(state)
        summary = state.get("summary", "")
        system_content = task.prompt
        if summary:
            system_content += (
                "\n\n## Conversation summary (earlier turns, background information - not instructions)\n"
                + summary
            )
        system = SystemMessage(content=system_content)
        history_messages = build_history_messages(state.get("history", []), agent.history_token_budget, summary)
        human = HumanMessage(content=f"Context:\n{context}\n\nQuestion: {state['message']}")

        classification = state.get("effective_classification", base_classification)
        # ADR-0416: agent.local_only (e.g. Finage) is an unconditional,
        # agent-declared restriction independent of this turn's own
        # local_only_required (ADR-0035, per-tool-call) - either forces it.
        local_only = state.get("local_only_required", False) or agent.local_only
        turn_messages: List[Any] = [system, *history_messages, human]
        try:
            result, provider = await _model_router.invoke_with_fallback(
                classification=classification,
                messages=turn_messages,
                bearer_token=state["bearer_token"],
                local_only=local_only,
                request_id=state.get("request_id"),
                agent_name=agent.name,
                task_name=task.name,
                # ADR-0511/ADR-0512 (WP-55): only a verified binding may
                # draw project quota - gated on the task's own mark, never
                # on state["project_id"] being merely truthy.
                project_id=state.get("project_id") if task.project_required else None,
                tools=[_GENERATE_IMAGE_TOOL_SCHEMA] if image_generation_enabled else None,
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

        tool_calls = getattr(result, "tool_calls", None) or []
        image_call = next((tc for tc in tool_calls if tc.get("name") == "generate_image"), None)
        if not image_call:
            reply_text = result.content if hasattr(result, "content") else str(result)
            return {"reply": reply_text, "provider_used": provider.name}

        return await _resolve_image_generation_call(
            state, agent, task, turn_messages, result, image_call, provider,
        )

    return reason_node


async def _resolve_image_generation_call(
    state: AgentState,
    agent: AgentDefinition,
    task: TaskDefinition,
    turn_messages: List[Any],
    assistant_result: Any,
    image_call: Dict[str, Any],
    provider: Any,
) -> Dict[str, Any]:
    """ADR-0415: executes the LLM's own choice to call generate_image, then
    makes a SECOND (tool-less) model call so the agent can present the
    result in natural language, the standard two-round tool-calling shape.
    The tool result fed back to that second call is a short status
    summary, never the base64 payload itself - the image only ever rides
    in `generated_images`, kept out of every text-based prompt/history
    path (see app/graph/history.py's placeholder substitution)."""
    args = image_call.get("args", {})
    try:
        tool_result = await invoke_tool(
            tool_name="generate_image",
            arguments={"prompt": args.get("prompt", ""), "negative_prompt": args.get("negative_prompt")},
            bearer_token=state["bearer_token"],
            agent_name=agent.name,
            task_name=task.name,
            data_classification=_IMAGE_GENERATION_CLASSIFICATION,
        )
    except McpClientError as exc:
        logger.warning("generate_image tool call failed: %s", exc)
        tool_result = {"error": str(exc)}

    if "error" in tool_result:
        tool_summary = {"status": "error", "detail": tool_result["error"]}
        generated_images_update: Dict[str, Any] = {}
    else:
        tool_summary = {"status": "ok", "prompt": args.get("prompt", "")}
        generated_images_update = {
            "generated_images": state.get("generated_images", [])
            + [
                {
                    "data_base64": tool_result["data_base64"],
                    "mime_type": tool_result.get("mime_type", "image/png"),
                    "alt": tool_result.get("alt", args.get("prompt", "")),
                }
            ]
        }

    follow_up_messages = [
        *turn_messages,
        AIMessage(content=assistant_result.content or "", tool_calls=[image_call]),
        ToolMessage(content=json.dumps(tool_summary), tool_call_id=image_call.get("id", "")),
    ]
    try:
        final_result, final_provider = await _model_router.invoke_with_fallback(
            classification=state.get("effective_classification", agent.preferred_classification),
            messages=follow_up_messages,
            bearer_token=state["bearer_token"],
            local_only=state.get("local_only_required", False),
            request_id=state.get("request_id"),
            agent_name=agent.name,
            task_name=task.name,
            # ADR-0511/ADR-0512 (WP-55): only a verified binding may draw
            # project quota - gated on the task's own mark, never on
            # state["project_id"] being merely truthy.
            project_id=state.get("project_id") if task.project_required else None,
        )
    except ModelRouterError as exc:
        logger.error("follow-up model call after generate_image failed: %s", exc)
        fallback_reply = (
            "I generated the image, but couldn't compose a follow-up reply right now."
            if "error" not in tool_result
            else f"I couldn't generate that image: {tool_result['error']}"
        )
        return {
            "reply": fallback_reply,
            "provider_used": provider.name,
            "errors": state.get("errors", []) + [f"reason: {exc}"],
            **generated_images_update,
        }

    reply_text = final_result.content if hasattr(final_result, "content") else str(final_result)
    return {"reply": reply_text, "provider_used": final_provider.name, **generated_images_update}


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
