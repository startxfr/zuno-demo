from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    # Informational/correlation only (ADR-0033) - never an authorization
    # input. The authoritative subject always comes from the validated
    # bearer token (see app/main.py:_initial_state), regardless of this
    # field's value.
    user_sub: str = Field(min_length=1)
    message: str = Field(min_length=1)


class Citation(BaseModel):
    source: str
    title: str


class ChatResponse(BaseModel):
    reply: str
    citations: List[Citation]
