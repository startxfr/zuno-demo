"""LangChain chat-model factory per provider (ADR-0020) - moved here from
components/agent-runtime's ModelRouter.chat_model_for() as part of
ADR-0009's split; the factory logic itself is unchanged. This module never
sees a hardcoded key: it only reads `os.environ` variable *names* declared
in the routing file, never a literal secret value (ADR-0024).
"""

from __future__ import annotations

import os
from typing import Any, Dict

from langchain_core.language_models.chat_models import BaseChatModel

from app.routing import ProviderCandidate


class ProviderFactoryError(RuntimeError):
    pass


def chat_model_for(candidate: ProviderCandidate, cfg: Dict[str, Any]) -> BaseChatModel:
    if candidate.kind == "local":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            base_url=cfg.get(
                "endpoint",
                os.getenv(
                    "LOCAL_MODEL_ENDPOINT",
                    "http://qwen25-7b-instruct-predictor.zuno-ai.svc:8080/v1",
                ),
            ),
            api_key=os.getenv("LOCAL_MODEL_API_KEY", "not-required"),
            model=cfg.get("model", os.getenv("LOCAL_MODEL_NAME", "qwen2.5-7b-instruct")),
            temperature=cfg.get("temperature", 0.2),
            timeout=cfg.get("timeout_seconds", 60),
        )

    if candidate.name == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=cfg.get("model", "gpt-4o-mini"),
            api_key=os.getenv(cfg.get("api_key_env", "OPENAI_API_KEY")),
            temperature=cfg.get("temperature", 0.2),
        )
    if candidate.name == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=cfg.get("model", "gemini-1.5-pro"),
            google_api_key=os.getenv(cfg.get("api_key_env", "GEMINI_API_KEY")),
            temperature=cfg.get("temperature", 0.2),
        )
    if candidate.name == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=cfg.get("model", "claude-3-5-sonnet-latest"),
            api_key=os.getenv(cfg.get("api_key_env", "ANTHROPIC_API_KEY")),
            temperature=cfg.get("temperature", 0.2),
        )
    if candidate.name == "mistral":
        from langchain_mistralai import ChatMistralAI

        return ChatMistralAI(
            model=cfg.get("model", "mistral-large-latest"),
            api_key=os.getenv(cfg.get("api_key_env", "MISTRAL_API_KEY")),
            temperature=cfg.get("temperature", 0.2),
        )

    raise ProviderFactoryError(f"no chat model factory registered for provider '{candidate.name}'")
