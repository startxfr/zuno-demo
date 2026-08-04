from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    user_sub: str = Field(min_length=1)
    message: str = Field(min_length=1)


class Citation(BaseModel):
    source: str
    title: str


class ChatResponse(BaseModel):
    reply: str
    citations: List[Citation]
