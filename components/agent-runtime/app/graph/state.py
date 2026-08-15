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
