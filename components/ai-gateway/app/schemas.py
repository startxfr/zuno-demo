"""OpenAI-compatible request/response schemas for `POST /v1/chat/completions`,
plus the Zuno extensions documented in README.md.

Why OpenAI-compatible: `components/agent-runtime` keeps using
`langchain_openai.ChatOpenAI` pointed at this gateway instead of five
different provider-specific LangChain classes, which means LangGraph's
existing `astream_events` streaming mechanism keeps working with zero
changes to `app/graph/nodes.py` — only the request's destination changed,
not the client interface. See docs/adr/0009-*.md.
"""

from __future__ import annotations

import time
import uuid
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    # Accepted for OpenAI wire-format compatibility; NOT used to select a
    # provider for v0 — routing is entirely classification-driven via the
    # X-Zuno-Data-Classification header (ADR-0021). A future version could
    # let a specific value pin/override the routing decision; tracked as
    # follow-up in README.md, not built now (out of the confirmed v0 scope).
    model: str = "zuno-auto"
    messages: List[ChatMessage]
    stream: bool = False


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:24]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage
    # Zuno extension (not part of the OpenAI schema): which provider
    # actually served this request, after classification-eligibility
    # filtering and fallback (ADR-0020/0021). Streaming responses do not
    # carry an equivalent field/header — see README.md's streaming section
    # for why — check this gateway's OTel traces for provider attribution
    # on a streaming call instead.
    zuno_provider: str
