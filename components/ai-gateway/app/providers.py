"""LangChain chat-model factory per provider (ADR-0020) - moved here from
components/agent-runtime's ModelRouter.chat_model_for() as part of
ADR-0009's split; the factory logic itself is unchanged. This module never
sees a hardcoded key: it only reads `os.environ` variable *names* declared
in the routing file, never a literal secret value (ADR-0024).

ADR-0114: a candidate whose provider-routing.yaml entry opts in
(`via_maas: true`) AND the global `MAAS_ADAPTER_ENABLED` switch is on is
built by app/maas_adapter.py instead of the direct client below - checked
first, before any candidate.kind branch, so it applies uniformly to the
local candidate or a SaaS one. This check runs strictly AFTER
app/routing.py's classification-eligibility filtering already happened
(candidates_for() is called before chat_model_for() in app/main.py) - the
MaaS adapter can change transport, never eligibility.

ADR-0303 (WP-39): `adapter`, when set, overrides the local candidate's
`model=` value with the adapter's own served name (vLLM multi-LoRA
request-level selection - the OpenAI-compatible `model` field IS the
adapter module name). Enforced here, not just by the caller: an `adapter`
passed alongside anything other than `candidate.kind == "local"` is
ignored (logged, never applied) - LoRA adapters are a local-vLLM-only
mechanism with no SaaS-provider equivalent, so this is the concrete
security boundary the "a C2/C3 adapter never reaches an external-eligible
serving path" acceptance test exercises directly against this function,
not just against app/main.py's own call-site discipline.

ADR-0544: `max_tokens` is the first per-REQUEST value this factory takes -
every other keyword (`temperature`, `timeout_seconds`, ...) reads from
`cfg`, provider-routing.yaml's per-candidate CONFIG, unchanged across every
call to that candidate. `max_tokens` instead arrives fresh per call
(app/main.py's `chat_completions` parses it from X-Zuno-Max-Tokens), so it
is an explicit function argument rather than a `cfg.get(...)` lookup -
mixing the two sources into one precedence rule was rejected in favor of
one producer, one path.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from langchain_core.language_models.chat_models import BaseChatModel

from app import maas_adapter
from app.routing import ProviderCandidate

logger = logging.getLogger("ai_gateway.providers")


class ProviderFactoryError(RuntimeError):
    pass


def chat_model_for(
    candidate: ProviderCandidate,
    cfg: Dict[str, Any],
    request_id: Optional[str] = None,
    adapter: Optional[str] = None,
    caller_bearer_token: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> BaseChatModel:
    via_maas = maas_adapter.should_use_maas(cfg, candidate.kind)
    if adapter and (candidate.kind != "local" or via_maas or not cfg.get("serves_adapters", False)):
        # LoRA adapters only serve on the direct local vLLM endpoint - not
        # a non-local candidate, not the local candidate when ADR-0114's
        # MaaS transport is in front of it (out of scope here;
        # gitops/charts/models' loraAdapters flags are a direct-vLLM
        # mechanism MaaS's own CR wrapping doesn't expose), and since
        # ADR-0412 not a local candidate whose provider entry lacks
        # `serves_adapters: true` either - with two local runtimes, only
        # the qwen one registers loraAdapters, and sending a LoRA module
        # name to a runtime that doesn't serve it would 404 every request.
        # Default-false means the config-less degraded mode (no
        # provider-routing.yaml loaded) also drops adapters now - the safe
        # direction.
        logger.warning(
            "ignoring adapter '%s' for candidate '%s' (kind=%s, via_maas=%s, serves_adapters=%s): LoRA adapters only serve on the direct qwen vLLM runtime (ADR-0303/ADR-0412)",
            adapter, candidate.name, candidate.kind, via_maas, cfg.get("serves_adapters", False),
        )
        adapter = None

    if via_maas:
        # ADR-0201 (WP-27): only the MaaS transport forwards request_id as
        # a header - direct providers already get it on their own
        # model_call_span (app/main.py), which is the only correlation
        # surface Zuno controls for those.
        # ADR-0544: MUST forward max_tokens - structure-demo's own
        # preferred candidate is local-maas (via_maas: true), so skipping
        # this branch would make max_tokens a silent no-op on its first
        # real usage.
        return maas_adapter.chat_model_via_maas(
            cfg, request_id=request_id, caller_bearer_token=caller_bearer_token,
            max_tokens=max_tokens,
        )

    if candidate.kind == "local":
        from langchain_openai import ChatOpenAI

        # 2026-08-21/ADR-0521: every local candidate's endpoint is https now
        # (both are LLMInferenceServices, which always terminate real TLS -
        # see provider-routing.yaml's own comments on the `local` and
        # `local-gpt-oss` entries). LOCAL_GPT_OSS_CA_BUNDLE, when set,
        # points at the namespace's openshift-service-ca.crt ConfigMap
        # (gitops/charts/ai-gateway's deployment.yaml) so that cert verifies
        # instead of failing closed - despite the env var's gpt-oss-specific
        # name, it applies to any local candidate reaching this branch.
        http_async_client = None
        ca_bundle = os.getenv("LOCAL_GPT_OSS_CA_BUNDLE")
        if ca_bundle:
            import httpx

            http_async_client = httpx.AsyncClient(verify=ca_bundle)

        return ChatOpenAI(
            base_url=cfg.get(
                "endpoint",
                os.getenv(
                    "LOCAL_MODEL_ENDPOINT",
                    "https://qwen36-27b-instruct-kserve-workload-svc.zuno-ai-run.svc:8000/v1",
                ),
            ),
            api_key=os.getenv("LOCAL_MODEL_API_KEY", "not-required"),
            # ADR-0303 (WP-39): a declared adapter overrides the base
            # model name outright - vLLM multi-LoRA selects the adapter
            # module by this exact field.
            model=adapter or cfg.get("model", os.getenv("LOCAL_MODEL_NAME", "qwen3.6-27b-instruct")),
            temperature=cfg.get("temperature", 0.2),
            timeout=cfg.get("timeout_seconds", 60),
            http_async_client=http_async_client,
            # ADR-0029: lets a streamed call's terminal chunk carry
            # usage_metadata (vLLM's OpenAI-compatible stream_options.
            # include_usage extension) - see app/main.py's _stream_completion,
            # which is the ONLY path real traffic ever takes (agent-runtime
            # always calls via LangGraph's astream_events). Harmless on the
            # non-streaming .ainvoke() path.
            stream_usage=True,
            max_tokens=max_tokens,
        )

    if candidate.name == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=cfg.get("model", "gpt-4o-mini"),
            api_key=os.getenv(cfg.get("api_key_env", "OPENAI_API_KEY")),
            temperature=cfg.get("temperature", 0.2),
            stream_usage=True,
            max_tokens=max_tokens,
        )
    if candidate.name == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=cfg.get("model", "gemini-1.5-pro"),
            google_api_key=os.getenv(cfg.get("api_key_env", "GEMINI_API_KEY")),
            temperature=cfg.get("temperature", 0.2),
            # ADR-0544: this class's parameter is max_output_tokens, not
            # max_tokens - the one real per-vendor translation this
            # factory needs.
            max_output_tokens=max_tokens,
        )
    if candidate.name == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=cfg.get("model", "claude-3-5-sonnet-latest"),
            api_key=os.getenv(cfg.get("api_key_env", "ANTHROPIC_API_KEY")),
            temperature=cfg.get("temperature", 0.2),
            # ADR-0544: ChatAnthropic supplies its own default when this is
            # None, so behavior is unchanged-but-not-byte-identical for a
            # candidate that never declares max_tokens - noted since every
            # other branch here is a true no-op on None.
            max_tokens=max_tokens,
        )
    if candidate.name == "mistral":
        from langchain_mistralai import ChatMistralAI

        return ChatMistralAI(
            model=cfg.get("model", "mistral-large-latest"),
            api_key=os.getenv(cfg.get("api_key_env", "MISTRAL_API_KEY")),
            temperature=cfg.get("temperature", 0.2),
            max_tokens=max_tokens,
        )
    if candidate.name == "mistral-codestral":
        from langchain_mistralai import ChatMistralAI

        # ADR-0417: same native Mistral API as the `mistral` branch above -
        # a dedicated credential (MISTRAL_CODESTRAL_API_KEY) only.
        return ChatMistralAI(
            model=cfg.get("model", "codestral-latest"),
            api_key=os.getenv(cfg.get("api_key_env", "MISTRAL_CODESTRAL_API_KEY")),
            temperature=cfg.get("temperature", 0.2),
            max_tokens=max_tokens,
        )
    if candidate.name == "ovhcloud-gpt-oss-120b":
        from langchain_openai import ChatOpenAI

        # ADR-0416: same OVHcloud AI Endpoints account as ADR-0415's
        # stable-diffusion-xl, OpenAI-compatible chat completions -
        # reuses ChatOpenAI with a custom base_url exactly like the
        # `local` candidate above.
        return ChatOpenAI(
            base_url=cfg.get("endpoint", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"),
            api_key=os.getenv(cfg.get("api_key_env", "OVHCLOUD_API_KEY")),
            model=cfg.get("model", "gpt-oss-120b"),
            temperature=cfg.get("temperature", 0.2),
            stream_usage=True,
            max_tokens=max_tokens,
        )

    raise ProviderFactoryError(f"no chat model factory registered for provider '{candidate.name}'")
