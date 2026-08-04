"""Thin client for the AI Inference Gateway (ADR-0009, ADR-0020, ADR-0021).

Routing, fallback-across-providers and classification-eligibility now live
entirely in components/ai-gateway - this module only builds a
langchain_openai.ChatOpenAI pointed at the gateway's OpenAI-compatible
/v1/chat/completions endpoint. Using ChatOpenAI (rather than a raw httpx
client) means app/graph/nodes.py's reason_node and app/main.py's
_stream_chat need zero changes: LangGraph's astream_events(version="v2")
keeps emitting on_chat_model_stream events exactly as it did when this
module talked to providers directly - it's still a real LangChain chat
model object being invoked, only what's on the other end of the HTTP call
changed. See components/ai-gateway/README.md's "Why agent-runtime's
streaming needs no code changes" for the full reasoning.

Before this split, this module held five provider-specific factory
functions and the classification-eligibility/fallback loop itself (moved
verbatim to components/ai-gateway/app/{routing,providers}.py) - this file
no longer reads platform/ai-gateway/provider-routing.yaml at all, and
holds no provider API key.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

logger = logging.getLogger("agent_runtime.model_router")

AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai.svc:8080")


@dataclass
class ProviderCandidate:
    """Kept only so callers (app/graph/nodes.py:reason_node) can keep
    reading `provider.name` unchanged. Always "ai-gateway" now - this
    client genuinely doesn't know which downstream provider served a
    request anymore; that detail lives in the gateway's own OTel traces.
    """

    name: str


class ModelRouterError(RuntimeError):
    pass


class ModelRouter:
    def chat_model_for(self, classification: str) -> BaseChatModel:
        return ChatOpenAI(
            base_url=f"{AI_GATEWAY_URL}/v1",
            api_key="not-required",
            # Ignored by the gateway for v0 - routing is entirely
            # classification-driven (see the X-Zuno-Data-Classification
            # default_header below), not model-name-driven. Required by
            # the OpenAI wire schema regardless.
            model="zuno-auto",
            default_headers={"X-Zuno-Data-Classification": classification.upper()},
        )

    async def invoke_with_fallback(self, classification: str, messages: List[Any]):
        """Kept as async + same name/signature as before this split so
        app/graph/nodes.py:reason_node doesn't need to change. The
        multi-provider fallback loop this name used to describe runs
        server-side in the gateway now (app/main.py:_invoke_with_fallback
        there) - this is a single HTTP call.
        """
        model = self.chat_model_for(classification)
        try:
            result = await model.ainvoke(messages)
        except Exception as exc:
            logger.error(
                "AI Inference Gateway call failed for classification %s: %s", classification, exc
            )
            raise ModelRouterError(f"AI Inference Gateway call failed: {exc}") from exc
        return result, ProviderCandidate(name="ai-gateway")
