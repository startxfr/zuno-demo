from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app import config


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=config.DEFAULT_TOP_K, ge=1, le=config.MAX_TOP_K)
    # ADR-0046: deterministic pre-ranking filters, set by the caller when
    # the user's question names a specific product/version - see
    # app/search.py's _filter_clause.
    product: Optional[str] = None
    version: Optional[str] = None
    # Soft ranking preference, not a hard filter - see
    # app/search.py's _LANGUAGE_BOOST.
    language: Optional[str] = None
    # ADR-0046 Security considerations: "Retrieval must never return
    # documents the user cannot access." Omitted/empty means the caller has
    # no groups - only ACL-unrestricted documents are returned (fail
    # closed, never fail open).
    caller_groups: List[str] = Field(default_factory=list)
    # ADR-0203: defense in depth. The caller (Agent Runtime) has already
    # evaluated the full agent/task/group/policy intersection
    # (app/knowledge.py:evaluate_knowledge()) and sends only the domains it
    # authorized; this service applies the list as an additional filter
    # rather than trusting the caller alone. Additive/optional: omitted or
    # empty means no domain filtering (pre-ADR-0202 rows have no `domain`
    # metadata key and are treated as knowledge.tech - see
    # app/search.py:_filter_clause).
    domains: List[str] = Field(default_factory=list)
    # ADR-0202: the one canonical cross-source key official web
    # documentation and Confluence chunks both use for knowledge.tech - a
    # hard filter like product/version, not a ranking preference.
    technology: Optional[str] = None
    # ADR-0209: required together whenever `domains` includes
    # knowledge.project - rag-service checks project_memberships
    # (data/rag/schema/005_project_memory.sql) for a row matching
    # caller_sub OR any of caller_groups before that domain's pool is
    # ever queried (fail closed, defense in depth around Agent Runtime's
    # own per-turn gate in app/graph/nodes.py:retrieve_node).
    project_id: Optional[str] = None
    caller_sub: Optional[str] = None


class SearchResult(BaseModel):
    id: str
    source: str
    title: str
    snippet: str
    score: float
    # ADR-0046: surfaced so the caller (Agent Runtime) can escalate
    # effective_classification (ADR-0034) and decide what to do with a
    # stale source, rather than this service silently deciding for it.
    classification: str = "C1"
    language: Optional[str] = None
    product: Optional[str] = None
    version: Optional[str] = None
    stale: bool = False
    # ADR-0202 Operational considerations: "each retrieved item must expose
    # domain/source/provenance/freshness metadata in traces and citations".
    # Untagged legacy rows default to knowledge.tech (see
    # app/search.py:_row_to_doc), the same convention the domain filter
    # itself uses.
    domain: str = "knowledge.tech"
    # ADR-0205/WP-24: true when an operational-domain chunk carries neither
    # `indexed_at` nor `stale_after` - it predates this WP's ingestion
    # metadata enforcement and its real freshness is unknown, never
    # trusted by default. Distinct from `stale` (a known, expired
    # freshness window) - this is "we don't know", not "we know it's old".
    freshness_untrusted: bool = False


class SearchResponse(BaseModel):
    results: List[SearchResult]
    vector_search_used: bool


class ProjectFact(BaseModel):
    """ADR-0209: one structured project_state row - a key fact, not a
    narrative chunk (e.g. key="openshift_version", value="4.22")."""

    key: str = Field(min_length=1)
    value: Any


class ProjectMemoryItem(BaseModel):
    """ADR-0209: one semantic memory chunk, embedded and stored in
    document_embeddings under knowledge.project."""

    text: str = Field(min_length=1)
    kind: str = Field(default="fact")  # fact | decision | constraint | action


class ProjectMemoryWriteRequest(BaseModel):
    project_id: str = Field(min_length=1)
    caller_sub: str = Field(min_length=1)
    caller_groups: List[str] = Field(default_factory=list)
    agent: str = Field(min_length=1)
    session_id: Optional[str] = None
    # ADR-0209: the conversation's own effective_classification, inherited
    # verbatim - this endpoint never derives or downgrades it.
    classification: str = "C2"
    facts: List[ProjectFact] = Field(default_factory=list)
    memories: List[ProjectMemoryItem] = Field(default_factory=list)


class ProjectMemoryWriteResponse(BaseModel):
    facts_written: int
    memories_written: int


class ProjectMembershipEntry(BaseModel):
    """ADR-0527: one projected grant. Exactly one of subject/group_name is
    set, mirroring project_memberships' own CHECK. The ROLE is deliberately
    absent: ADR-0209's membership check is binary, and projecting a role
    this service has no use for would invite it to start making
    authorization decisions ADR-0527 keeps in agent-runtime."""

    subject: Optional[str] = None
    group_name: Optional[str] = None


class ProjectMembershipsReplaceRequest(BaseModel):
    """ADR-0527 clause 8: replace-all for one project's membership
    projection. `revision` is agent-runtime's monotone
    projects.grants_revision - it makes this endpoint idempotent and
    non-rewindable, so a retry that arrives after a newer push is ignored
    rather than resurrecting a stale grant set."""

    revision: int = Field(ge=0)
    members: List[ProjectMembershipEntry] = Field(default_factory=list)


class ProjectMembershipsReplaceResponse(BaseModel):
    # False when a newer revision is already stored - a success, not an
    # error: the caller's push was simply superseded.
    applied: bool
    revision: int
    rows: int
