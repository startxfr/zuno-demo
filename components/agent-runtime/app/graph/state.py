"""LangGraph state schema (ADR-0018), shared across every graph shape
(ADR-0342) - Tekos's retrieve_reason_respond and Arkos's plan_draft_write
both read/write this one TypedDict, each populating only the fields its
own nodes use."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class RetrievedDoc(TypedDict, total=False):
    id: str
    source: str
    title: str
    snippet: str
    score: float
    # ADR-0046: per-document retrieval metadata rag-service now surfaces -
    # see that service's app/schemas.py:SearchResult. total=False because
    # legacy/mocked callers (e.g. tests) may not populate every field.
    classification: str
    language: Optional[str]
    product: Optional[str]
    version: Optional[str]
    stale: bool
    # ADR-0205/WP-24: which knowledge domain this doc came from - drives
    # the freshness-sensitive-domain live-read trigger
    # (app/graph/nodes.py:_live_read_trigger_reason). total=False because
    # legacy/mocked callers may not populate it.
    domain: str
    # ADR-0205/WP-24: True when this chunk predates ingestion's metadata
    # enforcement and its real freshness is unknown - rag-service already
    # ranks it last; the runtime surfaces the same signal rather than
    # silently trusting an untagged doc.
    freshness_untrusted: bool


class Citation(TypedDict):
    source: str
    title: str


class GeneratedImage(TypedDict):
    data_base64: str
    mime_type: str
    alt: str


class AgentState(TypedDict, total=False):
    # Request-scoped inputs
    session_id: str
    user_sub: str
    groups: List[str]
    bearer_token: str
    message: str
    # ADR-0201/WP-27: forwarded to ai-gateway (and, when routed via MaaS,
    # the MaaS adapter) as X-Zuno-Request-Id for usage/trace correlation -
    # see app/main.py's _request_id and app/clients/model_router.py.
    request_id: str
    # ADR-0209/WP-28: scopes this turn to a project's durable memory
    # (knowledge.project) - forwarded on every RAG call this turn makes
    # (app/clients/rag_client.py) and to the extraction endpoint at
    # session end. None/absent means no project memory involvement.
    project_id: Optional[str]

    # Node outputs, accumulated as the graph runs
    retrieved_docs: List[RetrievedDoc]
    tool_results: Dict[str, Any]
    reply: str
    citations: List[Citation]
    # ADR-0415: images generate_image produced this turn, accumulated
    # across the whole thread the same way ADR-0103's checkpointer already
    # persists every other state channel - no separate database/table.
    # Kept out of `history`/`summary` (app/graph/history.py substitutes a
    # short text placeholder for a past turn's images instead) so the
    # base64 payload is never re-injected into a later LLM call.
    generated_images: List[GeneratedImage]
    # Always "ai-gateway" now (ADR-0009 split) - this runtime no longer
    # knows which downstream provider actually served the request; that
    # detail lives in components/ai-gateway's own OTel traces.
    provider_used: Optional[str]
    errors: List[str]

    # ADR-0034: the highest classification of every context source
    # contributed so far (retrieved docs, tool results) - monotonically
    # non-decreasing, never downgraded once escalated. Drives the model
    # call's X-Zuno-Data-Classification header, replacing the old static
    # per-agent constant.
    effective_classification: str
    # ADR-0035: set True the moment any contributing source declares
    # external_model_policy.allow_context: false (e.g. Confluence results) -
    # forces the model call to local-only inference regardless of what
    # effective_classification's own SaaS-eligibility would otherwise allow.
    local_only_required: bool

    # ADR-0205/WP-24: why should_call_tools decided to trigger (or not) a
    # live capability call this turn - "no silent substitution": recorded
    # even when the trigger fired but no live capability was actually
    # available/successful (tool_call_node's own errors list still
    # explains that separately), so a trace/log always shows what was
    # attempted, not just what ultimately succeeded.
    live_read_trigger_reason: Optional[str]
    # ADR-0205/WP-24 acceptance: "traces show whether a response used
    # indexed knowledge, live verification, or both" - computed by
    # respond_node from what actually ended up in the final answer
    # (retrieved_docs / tool_results), never from what was merely
    # attempted. One of "indexed" | "live" | "both" | "none".
    source_mode: str

    # ADR-0342/WP-31: Arkos's plan_draft_write shape only - a short,
    # deterministic plan (document topic/title) produced by plan_node,
    # consumed by retrieve_node (topic-driven query) and draft_node
    # (document title). Absent/unused by retrieve_reason_respond. Named
    # `doc_plan` rather than `plan` - LangGraph reserves state-key names
    # matching a node name (the shape's own node IS literally named
    # "plan"), and the two collide if given the same string.
    doc_plan: Dict[str, Any]
    # The drafted document body, produced by draft_node and consumed by
    # write_node - None when drafting failed (see draft_node's own
    # provider-failure handling, mirroring reason_node's). Named
    # `document_draft` rather than `draft` for the same node-name-collision
    # reason as `doc_plan` above (the shape's own node is named "draft").
    document_draft: Optional[str]
    # The Drive document URL write_node persisted the draft to, when the
    # write succeeded - None if the write failed or wasn't attempted.
    drive_doc_url: Optional[str]

    # ADR-0215: conversation history carried into the next model call,
    # reconstructed from state that ADR-0103's checkpoints already persist
    # rather than from a wire field - callers still send only the newest
    # message (app/schemas.py's ChatRequest is unchanged). All three keys
    # below are explicitly managed, plain LastValue channels (no reducer):
    # app/graph/history.py's record_history node always returns a full
    # replacement list/string, the same explicit-rebuild style `errors`
    # above already uses, because compaction must be able to rewrite
    # `history` wholesale, not merely append to it. `_initial_state`
    # (app/main.py) never touches any of these three keys, so - exactly
    # like `local_only_required` above - they carry forward unchanged
    # across turns on the same thread_id; a checkpoint that predates this
    # ADR simply lacks them, and every reader below defaults via `.get`.

    # Recent turns, verbatim, newest last - `[{"role": "user"|"assistant",
    # "content": str}]`. Injected as proper HumanMessage/AIMessage pairs
    # (app/graph/nodes.py's reason_node, app/graph/arkos_nodes.py's
    # draft_node), never as this turn's own `Context:` RAG wrapper - a
    # prior turn's retrieved snippets would blow the token budget and
    # could contradict this turn's fresh retrieval.
    history: List[Dict[str, str]]
    # The running compacted summary of every turn folded out of `history`
    # once the token budget is exceeded (app/graph/history.py:compact) -
    # injected into the single system message as delimited background
    # information, never as instructions.
    summary: str
    # The monotonic maximum classification across EVERY turn seen so far
    # on this thread, escalated the same way `effective_classification`
    # above is (nodes.py's `_escalate`) but deliberately never reset -
    # `effective_classification` is recomputed from the agent's baseline
    # every turn by retrieve_node and can therefore downgrade turn to
    # turn; once history spans turns, the classification of the
    # accumulated conversation must not. Governs the compaction model
    # call's own routing (local-only for C2/C3, ADR-0034/ADR-0035),
    # mirroring app/memory.py's extract_memory.
    history_classification: str
