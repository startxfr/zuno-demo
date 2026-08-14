"""ADR-0114 MaaS adapter prototype.

Zuno keeps every business/context decision it already makes - C1/C2/C3
eligibility, sovereignty, `X-Zuno-Local-Only` (ADR-0035) - entirely in
app/routing.py, unchanged. This module changes nothing about *whether* a
request is allowed to reach a candidate; it only changes *how* an
already-eligible candidate is reached, for providers that opt in.

Today every candidate is invoked directly: the "local" candidate hits its
KServe/vLLM predictor Service, each SaaS candidate hits its vendor API.
This module adds a second transport - the same OpenAI-compatible
`ChatOpenAI` client app/providers.py already uses for every candidate,
pointed at OpenShift AI MaaS's own OpenAI-compatible model-access endpoint
instead. It is:

- **additive**: no existing provider's behavior changes unless it opts in;
- **opt-in per provider**: a provider-routing.yaml entry must set
  `via_maas: true` (see platform/ai-gateway/provider-routing.yaml's schema
  comment - no shipped entry sets it yet, so out of the box nothing routes
  through it);
- **globally gated**: even an opted-in provider only actually uses this
  path when `MAAS_ADAPTER_ENABLED=true` (chart value
  `maasAdapter.enabled`, default `false`) - the operational "prototype
  ... before removing current gateway capabilities" step ADR-0114 requires.

See docs/roadmap/evidence/adr-0114-maas-coverage.md for the feature
comparison this prototype exists to inform.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from langchain_core.language_models.chat_models import BaseChatModel

MAAS_ADAPTER_ENABLED = os.getenv("MAAS_ADAPTER_ENABLED", "false").strip().lower() == "true"
MAAS_GATEWAY_ENDPOINT = os.getenv("MAAS_GATEWAY_ENDPOINT", "")
# Names the environment variable the MaaS API key is read from (populated
# by an ExternalSecret, same convention as every provider's *_API_KEY_ENV
# in provider-routing.yaml - never a literal value here, ADR-0024).
MAAS_GATEWAY_API_KEY_ENV = os.getenv("MAAS_GATEWAY_API_KEY_ENV", "MAAS_GATEWAY_API_KEY")


class MaasAdapterError(RuntimeError):
    pass


def enabled() -> bool:
    return MAAS_ADAPTER_ENABLED


def should_use_maas(cfg: Dict[str, Any]) -> bool:
    """True only when BOTH the global switch is on AND this specific
    provider's config opted in - the two-key gate that keeps this
    default-off and additive."""
    return MAAS_ADAPTER_ENABLED and bool(cfg.get("via_maas", False))


def chat_model_via_maas(cfg: Dict[str, Any]) -> BaseChatModel:
    """The exact same `ChatOpenAI` class every direct candidate in
    app/providers.py already uses, pointed at the MaaS gateway's
    OpenAI-compatible endpoint. `maas_model_ref` lets a provider-routing.yaml
    entry override the model identifier MaaS publishes it under, when that
    differs from the serving runtime's own internal model name
    (ADR-0114/ADR-0201 - MaaS model publication naming is not guaranteed to
    match `model`).
    """
    if not MAAS_GATEWAY_ENDPOINT:
        raise MaasAdapterError(
            "MAAS_ADAPTER_ENABLED is true but MAAS_GATEWAY_ENDPOINT is not set - "
            "the MaaS adapter has nothing to point at"
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url=MAAS_GATEWAY_ENDPOINT,
        api_key=os.getenv(MAAS_GATEWAY_API_KEY_ENV, "not-required"),
        model=cfg.get("maas_model_ref", cfg.get("model")),
        temperature=cfg.get("temperature", 0.2),
        timeout=cfg.get("timeout_seconds", 60),
    )
