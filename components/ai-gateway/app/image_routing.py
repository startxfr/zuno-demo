"""Image-generation provider routing (ADR-0415). Mirrors app/routing.py's
RoutingTable/ProviderCandidate/candidates_for shape exactly (same
fail-closed posture, same classification-eligibility filtering) but reads
platform/ai-gateway/image-provider-routing.yaml instead of
provider-routing.yaml, and returns ImageProviderCandidate - kept as a
separate small module rather than generalizing RoutingTable, since a
second modality with its own file, its own (currently single-entry, so no
`prefer` reordering is meaningful yet) candidate list and its own provider
factory (app/image_providers.py) is a cleaner boundary than parameterizing
the existing chat-specific class.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List

import yaml

logger = logging.getLogger("ai_gateway.image_routing")

IMAGE_PROVIDER_ROUTING_PATH = os.getenv(
    "IMAGE_PROVIDER_ROUTING_PATH", "/app/config/image-provider-routing.yaml"
)
CLASSIFICATION_RANK = {"C1": 1, "C2": 2, "C3": 3}


@dataclass
class ImageProviderCandidate:
    name: str
    kind: str  # "saas-image" today; local image serving is not modeled yet


class ImageRoutingError(RuntimeError):
    pass


class ImageRoutingTable:
    def __init__(self, routing_path: str = IMAGE_PROVIDER_ROUTING_PATH):
        self._routing_path = routing_path
        self._config = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self._routing_path, "r", encoding="utf-8") as fh:
                config = yaml.safe_load(fh) or {}
                logger.info(
                    "loaded image provider routing config from %s (%d providers)",
                    self._routing_path,
                    len(config.get("image_providers", [])),
                )
                return config
        except FileNotFoundError:
            logger.error(
                "image provider routing config not found at %s (see "
                "platform/ai-gateway/image-provider-routing.yaml); no image "
                "provider is available until it is deployed",
                self._routing_path,
            )
            return {}
        except Exception as exc:
            logger.error("failed to parse image provider routing config %s: %s", self._routing_path, exc)
            return {}

    @property
    def loaded(self) -> bool:
        return bool(self._config)

    def reload(self) -> None:
        self._config = self._load()

    def provider_config(self, name: str) -> Dict[str, Any]:
        return next(p for p in self._config.get("image_providers", []) if p["name"] == name)

    def candidates_for(self, classification: str) -> List[ImageProviderCandidate]:
        classification = classification.upper()
        if classification not in CLASSIFICATION_RANK:
            raise ImageRoutingError(f"unknown classification '{classification}'")

        providers = self._config.get("image_providers", [])
        candidates = [
            ImageProviderCandidate(name=p["name"], kind=p.get("kind", "saas-image"))
            for p in providers
            if classification in p.get("eligible_for", [])
        ]
        if not candidates:
            raise ImageRoutingError(
                f"no image provider in {self._routing_path} is eligible for classification "
                f"{classification}; failing closed per ADR-0021's posture rather than risk "
                "violating data-handling policy"
            )
        return candidates
