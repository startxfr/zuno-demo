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

ADR-0419 adds an alternative to the single `prefer:` key: `preferred:`
and `fallback:`, two separate ordered lists expressing intent ("these
are genuinely wanted" vs "these are acceptable, only once the real
choices are gone") rather than one flat list where position alone
carries that meaning. Purely a schema change - `preferred + fallback`
is concatenated into the exact same ordered name list `prefer:` would
have produced, handed to the same `_apply_preference`/`strict:`
mechanism unchanged. An entry may use either key shape; `prefer:`
keeps working exactly as it does today for every entry that doesn't
opt into the new one.

Fails closed per malformed entry, not per file: a single bad entry (a
typo'd/missing field) is skipped and logged, never crashes the whole
gateway - the affected agent/task pair just falls back to the base model,
same graceful-degradation posture app/routing.py already has for a
missing provider-routing.yaml.

ADR-0550 adds an optional `local_only_for: [C2, C3]` field to a
`preferences:` entry: forces `local_only` for THIS (agent, task) pair
whenever the request's classification is one of the listed values, even
though the provider that would otherwise be preferred (e.g.
`ovhcloud-gpt-oss-120b`, `eligible_for: [C1, C2]` in provider-routing.yaml)
remains globally eligible at that classification for other agents/tasks.
Plain `prefer:`/`preferred:`/`fallback:` can only reorder/narrow candidates
that already survived classification/local-only filtering - it cannot
forbid a globally-eligible provider for a single task, which is exactly
what Arkos's `draft-architecture-testimonial` task needs at C2/C3
(ADR-0550 decision 3). `app/main.py` ORs this into the request's own
`X-Zuno-Local-Only` flag before calling `routing_table.candidates_for()`,
reusing that call's existing fail-closed `RoutingError` when no local
candidate survives - no new failure path.
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


def _name_list(value: object) -> List[str]:
    return [n for n in value if isinstance(n, str) and n] if isinstance(value, list) else []


def _preference_names(raw: Dict) -> List[str]:
    """ADR-0419: `preferred:`/`fallback:` take precedence when either is
    present on an entry - concatenated in that order, the same shape
    `prefer:` alone would have produced. Falls back to the single
    `prefer:` key otherwise, unchanged from pre-ADR-0419 behavior."""
    if "preferred" in raw or "fallback" in raw:
        return _name_list(raw.get("preferred")) + _name_list(raw.get("fallback"))
    return _name_list(raw.get("prefer"))


@dataclass
class AdapterDeclaration:
    adapter: str
    classification: str


class ModelRoutingPolicy:
    def __init__(self, policy_path: str = MODEL_ROUTING_POLICY_PATH):
        self._policy_path = policy_path
        self._entries, self._preferences, self._strict, self._local_only_for = self._load()

    def _load(
        self,
    ) -> Tuple[
        Dict[Tuple[str, str], AdapterDeclaration],
        Dict[Tuple[str, str], List[str]],
        Dict[Tuple[str, str], bool],
        Dict[Tuple[str, str], set],
    ]:
        try:
            with open(self._policy_path, "r", encoding="utf-8") as fh:
                config = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            logger.info(
                "no model-routing policy found at %s; every request uses the base model (ADR-0303 default)",
                self._policy_path,
            )
            return {}, {}, {}, {}
        except Exception as exc:
            logger.error("failed to parse model-routing policy %s: %s", self._policy_path, exc)
            return {}, {}, {}, {}

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
        local_only_for: Dict[Tuple[str, str], set] = {}
        for raw in config.get("preferences", []) or []:
            agent = raw.get("agent")
            task = raw.get("task")
            names = _preference_names(raw)
            if not agent or not task or not names:
                logger.warning(
                    "skipping malformed model-routing preference entry (needs agent/task and a "
                    "non-empty prefer list, or a non-empty preferred/fallback pair): %r",
                    raw,
                )
                continue
            preferences[(agent, task)] = names
            strict[(agent, task)] = bool(raw.get("strict", False))
            tiers = {str(c).upper() for c in _name_list(raw.get("local_only_for"))}
            if tiers:
                local_only_for[(agent, task)] = tiers

        logger.info(
            "loaded model-routing policy from %s (%d adapter declaration(s), %d preference(s))",
            self._policy_path, len(entries), len(preferences),
        )
        return entries, preferences, strict, local_only_for

    def reload(self) -> None:
        self._entries, self._preferences, self._strict, self._local_only_for = self._load()

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

    def local_only_for_classification(self, agent_name: str, task_name: str, classification: str) -> bool:
        """ADR-0550: True when this (agent, task) pair's `local_only_for`
        declaration includes `classification` - forces local-only for this
        request regardless of what any provider's own global `eligible_for`
        would otherwise allow. False for every (agent, task) that doesn't
        declare the field, which is every entry that predates ADR-0550."""
        if not agent_name or not task_name:
            return False
        tiers = self._local_only_for.get((agent_name, task_name))
        return bool(tiers) and classification.upper() in tiers

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
