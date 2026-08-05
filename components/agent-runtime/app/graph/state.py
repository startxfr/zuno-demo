"""LangGraph state schema for the Tekos workflow (ADR-0018)."""

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
