"""Provider-routing config loading and classification-eligibility
resolution (ADR-0020, ADR-0021) - moved here from
components/agent-runtime's ModelRouter as part of ADR-0009's Agent
Runtime / AI Inference Gateway split; the loading/eligibility logic itself
is unchanged.

Reads `platform/ai-gateway/provider-routing.yaml` (mounted read-only at
`PROVIDER_ROUTING_PATH`, default `/app/config/provider-routing.yaml`) -
see `ansible/roles/llm` for how that ConfigMap is deployed and how each
external provider's API key reaches this pod's environment via a
Vault-backed `ExternalSecret` (ADR-0024).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List

import yaml

logger = logging.getLogger("ai_gateway.routing")

PROVIDER_ROUTING_PATH = os.getenv("PROVIDER_ROUTING_PATH", "/app/config/provider-routing.yaml")
CLASSIFICATION_RANK = {"C1": 1, "C2": 2, "C3": 3}


@dataclass
class ProviderCandidate:
    name: str
    kind: str  # "local" | "saas"


class RoutingError(RuntimeError):
    pass


class RoutingTable:
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

    @property
    def loaded(self) -> bool:
        return bool(self._config)

    def reload(self) -> None:
        self._config = self._load()

    def provider_config(self, name: str) -> Dict[str, Any]:
        if not self._config.get("providers"):
            return {}
        return next(p for p in self._config["providers"] if p["name"] == name)

    def candidates_for(self, classification: str) -> List[ProviderCandidate]:
        classification = classification.upper()
        if classification not in CLASSIFICATION_RANK:
            raise RoutingError(f"unknown classification '{classification}'")

        providers = self._config.get("providers", [])
        if not providers:
            return [ProviderCandidate(name="local", kind="local")]

        candidates = [
            ProviderCandidate(name=p["name"], kind=p.get("kind", "saas"))
            for p in providers
            if classification in p.get("eligible_for", [])
        ]
        if not candidates:
            raise RoutingError(
                f"no provider in {self._routing_path} is eligible for classification "
                f"{classification}; failing closed per ADR-0021 rather than risk violating "
                "data-handling policy"
            )
        return candidates
