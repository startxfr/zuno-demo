"""OpenAI-compatible request/response schemas for `POST /v1/chat/completions`,
plus the Zuno extensions documented in README.md.

Why OpenAI-compatible: `components/agent-runtime` keeps using
`langchain_openai.ChatOpenAI` pointed at this gateway instead of five
different provider-specific LangChain classes, which means LangGraph's
existing `astream_events` streaming mechanism keeps working with zero
changes to `app/graph/nodes.py` - only the request's destination changed,
not the client interface. See docs/adr/0009-*.md.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    # Optional (not "") because an assistant message that ONLY carries
    # tool_calls (no natural-language content yet) is a normal, valid
    # OpenAI wire shape.
    content: Optional[str] = None
    # ADR-0415: OpenAI wire-format tool calling, added so
    # components/agent-runtime's generate_image tool can be bound via
    # LangChain's model.bind_tools() (see app/providers.py's clients,
    # which are plain LangChain BaseChatModel objects with no gateway-side
    # tool-calling logic of their own - this schema and
    # _to_langchain_messages/_invoke_with_fallback/_stream_completion in
    # app/main.py are what let a tools= request pass through end to end).
    # Present only on an assistant message that chose to call a tool:
    # [{"id": ..., "type": "function", "function": {"name": ..., "arguments": "<json str>"}}].
    tool_calls: Optional[List[Dict[str, Any]]] = None
    # Present only on a role="tool" message (the tool's result being fed
    # back for a follow-up turn) - which tool_calls[].id this answers.
    tool_call_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    # Accepted for OpenAI wire-format compatibility; NOT used to select a
    # provider for v0 - routing is entirely classification-driven via the
    # X-Zuno-Data-Classification header (ADR-0021). A future version could
    # let a specific value pin/override the routing decision; tracked as
    # follow-up in README.md, not built now (out of the confirmed v0 scope).
    model: str = "zuno-auto"
    messages: List[ChatMessage]
    stream: bool = False
    # ADR-0415: raw OpenAI tool-schema passthrough
    # ([{"type": "function", "function": {"name", "description", "parameters"}}]),
    # bound onto whichever candidate model is selected via
    # BaseChatModel.bind_tools() - never inspected/validated by this
    # gateway itself, which stays tool-schema-agnostic.
    tools: Optional[List[Dict[str, Any]]] = None


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
    # carry an equivalent field/header - see README.md's streaming section
    # for why - check this gateway's OTel traces for provider attribution
    # on a streaming call instead.
    zuno_provider: str


class ImageGenerationRequest(BaseModel):
    """ADR-0415: OpenAI images-API-compatible request for
    POST /v1/images/generations. `model` is accepted for wire-format
    compatibility only, same as ChatCompletionRequest.model - routing is
    classification-driven (X-Zuno-Data-Classification), not model-name-driven.
    """

    model: str = "stable-diffusion-xl"
    prompt: str
    negative_prompt: Optional[str] = None


class ImageGenerationData(BaseModel):
    b64_json: str


class ImageGenerationResponse(BaseModel):
    created: int = Field(default_factory=lambda: int(time.time()))
    data: List[ImageGenerationData]
    # Zuno extension, mirrors ChatCompletionResponse.zuno_provider.
    zuno_provider: str
