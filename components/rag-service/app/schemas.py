from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from app import config


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=config.DEFAULT_TOP_K, ge=1, le=config.MAX_TOP_K)


class SearchResult(BaseModel):
    id: str
    source: str
    title: str
    snippet: str
    score: float


class SearchResponse(BaseModel):
    results: List[SearchResult]
    vector_search_used: bool
