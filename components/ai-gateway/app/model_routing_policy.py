"""ADR-0303 (WP-39): per-agent/task adapter declarations -
policies/model-routing/model-routing-policy.yaml, baked into this image
(components/ai-gateway/Dockerfile), same convention as
policies/knowledge/knowledge-policy.yaml and policies/tools/tool-policy.yaml
in their own consuming services. Mechanism only: which request gets AN
adapter, never which adapter is BEST (ADR-0304/WP-40's job, which extends
this same policy file with objectives blocks rather than a second file).

Fails closed per malformed entry, not per file: a single bad entry (a
typo'd/missing field) is skipped and logged, never crashes the whole
gateway - the affected agent/task pair just falls back to the base model,
same graceful-degradation posture app/routing.py already has for a
missing provider-routing.yaml.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import yaml

logger = logging.getLogger("ai_gateway.model_routing_policy")

MODEL_ROUTING_POLICY_PATH = os.getenv(
    "MODEL_ROUTING_POLICY_PATH", "/app/policies/model-routing/model-routing-policy.yaml"
)


@dataclass
class AdapterDeclaration:
    adapter: str
    classification: str


class ModelRoutingPolicy:
    def __init__(self, policy_path: str = MODEL_ROUTING_POLICY_PATH):
        self._policy_path = policy_path
        self._entries = self._load()

    def _load(self) -> Dict[Tuple[str, str], AdapterDeclaration]:
        try:
            with open(self._policy_path, "r", encoding="utf-8") as fh:
                config = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            logger.info(
                "no model-routing policy found at %s; every request uses the base model (ADR-0303 default)",
                self._policy_path,
            )
            return {}
        except Exception as exc:
            logger.error("failed to parse model-routing policy %s: %s", self._policy_path, exc)
            return {}

        entries: Dict[Tuple[str, str], AdapterDeclaration] = {}
        for raw in config.get("adapters", []) or []:
            agent = raw.get("agent")
            task = raw.get("task")
            adapter = raw.get("adapter")
            if not agent or not task or not adapter:
                logger.warning(
                    "skipping malformed model-routing policy entry (needs agent/task/adapter): %r", raw
                )
                continue
            entries[(agent, task)] = AdapterDeclaration(
                adapter=adapter, classification=str(raw.get("classification", "C1")).upper()
            )
        logger.info("loaded model-routing policy from %s (%d adapter declaration(s))", self._policy_path, len(entries))
        return entries

    def reload(self) -> None:
        self._entries = self._load()

    def adapter_for(self, agent_name: str, task_name: str) -> Optional[AdapterDeclaration]:
        if not agent_name or not task_name:
            return None
        return self._entries.get((agent_name, task_name))
