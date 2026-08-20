"""ADR-0303 (WP-39): per-agent/task adapter declarations -
policies/model-routing/model-routing-policy.yaml, baked into this image
(components/ai-gateway/Dockerfile), same convention as
policies/knowledge/knowledge-policy.yaml and policies/tools/tool-policy.yaml
in their own consuming services. Mechanism only: which request gets AN
adapter, never which adapter is BEST (ADR-0304/WP-40's job, which extends
this same policy file with objectives blocks rather than a second file).

ADR-0412 extends the same file with `preferences:` - a per-(agent,task)
ordered provider-name list app/routing.py uses to REORDER the candidates
that survived classification/local-only filtering. Reorder only: it never
widens eligibility (ADR-0021/0035 stay the hard constraints), and it is
on the ADR-0309 optimizer's code-level denylist.

ADR-0417 adds an optional `strict: true` field to a `preferences:` entry:
narrows that reorder into an exclusion (app/routing.py's
`_apply_preference` returns only the listed, still-eligible names, no
unlisted survivor appended) - for a request path where silently
substituting a different model on failure would be the wrong behavior.
Defaults false for every existing entry, unchanged from today's reorder-
only semantics.

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
from typing import Dict, List, Optional, Tuple

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
        self._entries, self._preferences, self._strict = self._load()

    def _load(
        self,
    ) -> Tuple[
        Dict[Tuple[str, str], AdapterDeclaration],
        Dict[Tuple[str, str], List[str]],
        Dict[Tuple[str, str], bool],
    ]:
        try:
            with open(self._policy_path, "r", encoding="utf-8") as fh:
                config = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            logger.info(
                "no model-routing policy found at %s; every request uses the base model (ADR-0303 default)",
                self._policy_path,
            )
            return {}, {}, {}
        except Exception as exc:
            logger.error("failed to parse model-routing policy %s: %s", self._policy_path, exc)
            return {}, {}, {}

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

        preferences: Dict[Tuple[str, str], List[str]] = {}
        strict: Dict[Tuple[str, str], bool] = {}
        for raw in config.get("preferences", []) or []:
            agent = raw.get("agent")
            task = raw.get("task")
            prefer = raw.get("prefer")
            names = [n for n in prefer if isinstance(n, str) and n] if isinstance(prefer, list) else []
            if not agent or not task or not names:
                logger.warning(
                    "skipping malformed model-routing preference entry (needs agent/task and a non-empty prefer list): %r",
                    raw,
                )
                continue
            preferences[(agent, task)] = names
            strict[(agent, task)] = bool(raw.get("strict", False))

        logger.info(
            "loaded model-routing policy from %s (%d adapter declaration(s), %d preference(s))",
            self._policy_path, len(entries), len(preferences),
        )
        return entries, preferences, strict

    def reload(self) -> None:
        self._entries, self._preferences, self._strict = self._load()

    def adapter_for(self, agent_name: str, task_name: str) -> Optional[AdapterDeclaration]:
        if not agent_name or not task_name:
            return None
        return self._entries.get((agent_name, task_name))

    def preference_for(self, agent_name: str, task_name: str) -> Optional[List[str]]:
        """ADR-0412: ordered provider names for this (agent, task), or None
        for today's default order. Returns a copy - the loaded policy is
        never handed out mutably."""
        if not agent_name or not task_name:
            return None
        names = self._preferences.get((agent_name, task_name))
        return list(names) if names else None

    def strict_for(self, agent_name: str, task_name: str) -> bool:
        """ADR-0417: whether this (agent, task)'s preference is exclusive -
        only the listed, still-eligible providers are candidates, no
        unlisted survivor is appended. Defaults False (today's reorder-only
        behavior, unchanged) for every entry that doesn't set
        `strict: true`, and for any (agent, task) with no preference entry
        at all."""
        if not agent_name or not task_name:
            return False
        return self._strict.get((agent_name, task_name), False)
