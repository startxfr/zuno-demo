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
from typing import Any, Dict, List, Optional

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

    def candidates_for(
        self,
        classification: str,
        local_only: bool = False,
        prefer: Optional[List[str]] = None,
    ) -> List[ProviderCandidate]:
        """`local_only` (ADR-0035) is a source-level restriction independent
        of `classification`: when true, candidates are further filtered to
        `kind == "local"` regardless of which SaaS providers the
        classification alone would otherwise permit - set by the Agent
        Runtime when a contributing source (e.g. Confluence) declared
        `external_model_policy.allow_context: false`.

        `prefer` (ADR-0412) is an ordered provider-name list from the
        git-managed model-routing policy, applied strictly AFTER the
        eligibility/local-only filtering and the fail-closed empty check:
        a pure permutation of the surviving candidates. It structurally
        cannot resurrect a provider the hard constraints removed - same
        shape of guarantee as ADR-0114's "via_maas changes transport,
        never eligibility".
        """
        classification = classification.upper()
        if classification not in CLASSIFICATION_RANK:
            raise RoutingError(f"unknown classification '{classification}'")

        providers = self._config.get("providers", [])
        if not providers:
            # Fail-closed default (no config loaded) is already local-only;
            # a single candidate makes any preference a no-op.
            return [ProviderCandidate(name="local", kind="local")]

        candidates = [
            ProviderCandidate(name=p["name"], kind=p.get("kind", "saas"))
            for p in providers
            if classification in p.get("eligible_for", [])
        ]
        if local_only:
            candidates = [c for c in candidates if c.kind == "local"]
        if not candidates:
            reason = (
                f"no local-only provider in {self._routing_path} is eligible for "
                f"classification {classification}"
                if local_only
                else f"no provider in {self._routing_path} is eligible for classification {classification}"
            )
            raise RoutingError(f"{reason}; failing closed per ADR-0021 rather than risk violating data-handling policy")
        if prefer:
            candidates = self._apply_preference(candidates, prefer)
        return candidates

    def _apply_preference(
        self, candidates: List[ProviderCandidate], prefer: List[str]
    ) -> List[ProviderCandidate]:
        """Moves the preferred names that SURVIVED filtering to the front,
        in preference order; unlisted survivors keep their relative
        provider-routing.yaml order after them. Never adds, never removes.
        Unknown names (present in neither the provider list nor the
        survivors) are warned about and ignored - the policy file is baked
        into the image while provider-routing.yaml is a ConfigMap, so the
        two legitimately drift; preference is a hint, not a security
        control, and eligibility already failed closed above.
        """
        known = {p["name"] for p in self._config.get("providers", [])}
        deduped: List[str] = []
        for name in prefer:
            if name in deduped:
                continue
            if name not in known:
                logger.warning(
                    "ignoring unknown provider '%s' in a model-routing preference (not in %s)",
                    name, self._routing_path,
                )
                continue
            deduped.append(name)
        by_name = {c.name: c for c in candidates}
        preferred = [by_name[n] for n in deduped if n in by_name]
        listed = set(deduped)
        rest = [c for c in candidates if c.name not in listed]
        return preferred + rest
