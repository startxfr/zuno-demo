from __future__ import annotations

from typing import List, Optional

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


class SearchResponse(BaseModel):
    results: List[SearchResult]
    vector_search_used: bool
