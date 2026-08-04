"""LangGraph state schema for the Tekos workflow (ADR-0018)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class RetrievedDoc(TypedDict):
    id: str
    source: str
    title: str
    snippet: str
    score: float


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
    provider_used: Optional[str]
    errors: List[str]
