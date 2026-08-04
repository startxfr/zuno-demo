"""Model routing per ADR-0020 (local + external providers) and ADR-0021
(route by C1/C2/C3 classification).

Reads `platform/ai-gateway/provider-routing.yaml` (mounted read-only at
`PROVIDER_ROUTING_PATH`, default `/app/config/provider-routing.yaml`) --
see `ansible/roles/llm` for how that ConfigMap is deployed and how each
external provider's API key reaches this pod's environment via a
Vault-backed `ExternalSecret` (ADR-0024). This module never sees a
hardcoded key: `chat_model_for()` only reads `os.environ` variable *names*
declared in the routing file, never a literal secret value.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml
from langchain_core.language_models.chat_models import BaseChatModel

from app.telemetry import model_call_span

logger = logging.getLogger("agent_runtime.model_router")

PROVIDER_ROUTING_PATH = os.getenv("PROVIDER_ROUTING_PATH", "/app/config/provider-routing.yaml")
CLASSIFICATION_RANK = {"C1": 1, "C2": 2, "C3": 3}


@dataclass
class ProviderCandidate:
    name: str
    kind: str  # "local" | "saas"


class ModelRouterError(RuntimeError):
    pass


class ModelRouter:
    def __init__(self, routing_path: str = PROVIDER_ROUTING_PATH):
        self._routing_path = routing_path
        self._config = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self._routing_path, "r", encoding="utf-8") as fh:
                config = yaml.safe_load(fh) or {}
                logger.info(
                    "loaded provider routing config from %s (%d providers)",
                    self._routing_path,
                    len(config.get("providers", [])),
                )
                return config
        except FileNotFoundError:
            logger.error(
                "provider routing config not found at %s (see "
                "platform/ai-gateway/provider-routing.yaml / "
                "ansible/roles/llm); falling back to a local-model-only "
                "default per ADR-0021's fail-closed posture",
                self._routing_path,
            )
            return {}
        except Exception as exc:
            logger.error("failed to parse provider routing config %s: %s", self._routing_path, exc)
            return {}

    def reload(self) -> None:
        self._config = self._load()

    def candidates_for(self, classification: str) -> List[ProviderCandidate]:
        classification = classification.upper()
        if classification not in CLASSIFICATION_RANK:
            raise ModelRouterError(f"unknown classification '{classification}'")

        providers = self._config.get("providers", [])
        if not providers:
            return [ProviderCandidate(name="local", kind="local")]

        candidates = [
            ProviderCandidate(name=p["name"], kind=p.get("kind", "saas"))
            for p in providers
            if classification in p.get("eligible_for", [])
        ]
        if not candidates:
            raise ModelRouterError(
                f"no provider in {self._routing_path} is eligible for classification "
                f"{classification}; failing closed per ADR-0021 rather than risk violating "
                "data-handling policy"
            )
        return candidates

    def _provider_config(self, name: str) -> Dict[str, Any]:
        return next(p for p in self._config.get("providers", []) if p["name"] == name)

    def chat_model_for(self, candidate: ProviderCandidate) -> BaseChatModel:
        cfg = self._provider_config(candidate.name) if self._config.get("providers") else {}

        if candidate.kind == "local":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                base_url=cfg.get(
                    "endpoint",
                    os.getenv(
                        "LOCAL_MODEL_ENDPOINT",
                        "http://qwen25-7b-instruct-predictor.zuno-datascience.svc:8080/v1",
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

        raise ModelRouterError(f"no chat model factory registered for provider '{candidate.name}'")

    async def invoke_with_fallback(self, classification: str, messages: List[Any]):
        """Tries each eligible provider in the routing file's declared
        fallback order (local first, then OpenAI -> Gemini -> Anthropic ->
        Mistral per ADR-0020/MEMORY.md section 6) until one succeeds.
        """
        errors: List[str] = []
        for candidate in self.candidates_for(classification):
            model_name = self._provider_config(candidate.name).get("model", candidate.name) if self._config.get("providers") else candidate.name
            try:
                with model_call_span(candidate.name, model_name, classification) as call:
                    model = self.chat_model_for(candidate)
                    result = await model.ainvoke(messages)
                    usage = getattr(result, "usage_metadata", None) or {}
                    call.record_usage(
                        prompt_tokens=usage.get("input_tokens", 0),
                        completion_tokens=usage.get("output_tokens", 0),
                    )
                return result, candidate
            except Exception as exc:
                logger.warning("provider '%s' failed, trying next fallback: %s", candidate.name, exc)
                errors.append(f"{candidate.name}: {exc}")
        raise ModelRouterError(
            f"all eligible providers failed for classification {classification}: {'; '.join(errors)}"
        )

    def streaming_model_for(self, classification: str) -> "tuple[BaseChatModel, ProviderCandidate]":
        """Returns the first eligible provider's chat model for token
        streaming (SSE path). Fallback-on-failure for streaming is handled
        by the caller catching a stream error and is out of scope for a v0
        demo (a mid-stream provider failure surfaces as an `error` SSE
        event rather than silently retrying on a different provider).
        """
        candidates = self.candidates_for(classification)
        candidate = candidates[0]
        return self.chat_model_for(candidate), candidate
