"""ADR-0309 (WP-42): the bounded autonomous tuning controller - the
platform's ONLY autonomous-change surface, governed entirely by
policies/optimization/optimization-policy.yaml (baked into this image,
same lifecycle as the model-routing policy).

Scope, deliberately narrow (the ADR's own enumeration):
  - semantic-cache TTL, within the policy's declared [min, max] range
    (runtime override via app/semantic_cache.py's setter - never the env
    var, never a Git file);
  - routing choice between PRE-APPROVED EQUIVALENT candidates only (a
    runtime adapter override consulted by app/main.py strictly AFTER the
    Git-declared model-routing policy resolved, and only when the
    (incumbent, replacement) pair appears together in the policy's own
    pre_approved_equivalents list).

Hard structural guarantees, independent of the policy file's content:
  - _FORBIDDEN_PARAMETERS is a code-level denylist: classification and
    authorization are never auto-tunable even if a recommendation (or a
    mis-edited policy file) names them.
  - Runtime configuration only: nothing here writes to any file. A pod
    restart reverts everything (the audit log says what was applied).
  - Every applied change records an audit entry (parameter, old, new,
    the recommendation evidence verbatim, timestamps) and registers its
    own rollback closure.
  - report_outcome() reverts automatically on a rollback-trigger breach;
    kill() (or kill_switch: true in the policy) refuses every new action
    AND reverts everything currently applied, in one step.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from app import semantic_cache

logger = logging.getLogger("ai_gateway.optimizer")

OPTIMIZATION_POLICY_PATH = os.getenv(
    "OPTIMIZATION_POLICY_PATH", "/app/policies/optimization/optimization-policy.yaml"
)

# Code-level, not policy-level: these can never be tuned autonomously no
# matter what the policy file or a recommendation says (ADR-0309:
# "classification and authorization policies are never auto-tunable").
_FORBIDDEN_PARAMETERS = frozenset({
    "classification",
    "min_classification",
    "allowed_groups",
    "allowed_knowledge",
    "allowed_tools",
    "external_model_policy",
    "eligible_for",
    "entitlement",
    "authorization",
})


class OptimizationRefused(Exception):
    """Raised when a proposed action is outside the governed scope - the
    caller (an admin endpoint, a recommendation feed) must treat this as
    a definitive no, never retry-with-adjustment."""


@dataclass
class AuditEntry:
    parameter: str
    old_value: Any
    new_value: Any
    evidence: Dict[str, Any]
    applied_at: float
    status: str = "applied"  # applied | rolled_back | reverted_by_kill
    resolved_at: Optional[float] = None


@dataclass
class _AppliedAction:
    audit: AuditEntry
    rollback: Callable[[], None]
    window_ends_at: float


@dataclass
class OptimizationPolicy:
    enabled: bool = False
    kill_switch: bool = False
    evaluation_window_seconds: int = 3600
    max_error_rate: float = 0.05
    quality_floor: float = 0.75
    cache_ttl_enabled: bool = False
    cache_ttl_min: int = 300
    cache_ttl_max: int = 86400
    cache_enabled_scope: bool = False
    cache_enabled_models: List[str] = field(default_factory=list)
    routing_enabled: bool = False
    pre_approved_equivalents: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, policy_path: str = OPTIMIZATION_POLICY_PATH) -> "OptimizationPolicy":
        try:
            with open(policy_path, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            logger.info("no optimization policy at %s; autonomy stays fully disabled (ADR-0309 default)", policy_path)
            return cls()
        except Exception as exc:
            logger.error("failed to parse optimization policy %s: %s - autonomy stays fully disabled", policy_path, exc)
            return cls()

        scopes = raw.get("scopes", {}) or {}
        cache_ttl = scopes.get("cache_ttl", {}) or {}
        cache_enabled = scopes.get("cache_enabled", {}) or {}
        routing = scopes.get("routing", {}) or {}
        triggers = raw.get("rollback_triggers", {}) or {}
        return cls(
            enabled=bool(raw.get("enabled", False)),
            kill_switch=bool(raw.get("kill_switch", False)),
            evaluation_window_seconds=int(raw.get("evaluation_window_seconds", 3600)),
            max_error_rate=float(triggers.get("max_error_rate", 0.05)),
            quality_floor=float(triggers.get("quality_floor", 0.75)),
            cache_ttl_enabled=bool(cache_ttl.get("enabled", False)),
            cache_ttl_min=int(cache_ttl.get("min_seconds", 300)),
            cache_ttl_max=int(cache_ttl.get("max_seconds", 86400)),
            cache_enabled_scope=bool(cache_enabled.get("enabled", False)),
            cache_enabled_models=list(cache_enabled.get("models", []) or []),
            routing_enabled=bool(routing.get("enabled", False)),
            pre_approved_equivalents=list(routing.get("pre_approved_equivalents", []) or []),
        )


class TuningController:
    def __init__(self, policy: Optional[OptimizationPolicy] = None):
        self._policy = policy or OptimizationPolicy.load()
        self._applied: List[_AppliedAction] = []
        self._audit_log: List[AuditEntry] = []
        self._killed = False
        # Runtime adapter overrides: (agent, task) -> adapter name.
        self._adapter_overrides: Dict[Tuple[str, str], str] = {}

    # -- policy / state introspection -----------------------------------

    @property
    def policy(self) -> OptimizationPolicy:
        return self._policy

    def reload_policy(self, policy_path: str = OPTIMIZATION_POLICY_PATH) -> None:
        self._policy = OptimizationPolicy.load(policy_path)
        if self._policy.kill_switch:
            self.kill()

    def audit_log(self) -> List[Dict[str, Any]]:
        return [
            {
                "parameter": e.parameter,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "evidence": e.evidence,
                "applied_at": e.applied_at,
                "status": e.status,
                "resolved_at": e.resolved_at,
            }
            for e in self._audit_log
        ]

    def adapter_override(self, agent: str, task: str) -> Optional[str]:
        return self._adapter_overrides.get((agent, task))

    # -- guards ----------------------------------------------------------

    def _refuse_if_inactive(self) -> None:
        if self._killed or self._policy.kill_switch:
            raise OptimizationRefused("kill switch is engaged - all autonomy halted")
        if not self._policy.enabled:
            raise OptimizationRefused("autonomy is not enabled in policies/optimization/optimization-policy.yaml")

    @staticmethod
    def _refuse_forbidden(parameter: str) -> None:
        lowered = parameter.lower()
        for forbidden in _FORBIDDEN_PARAMETERS:
            if forbidden in lowered:
                raise OptimizationRefused(
                    f"parameter {parameter!r} touches classification/authorization - never auto-tunable (ADR-0309), "
                    "regardless of policy file content"
                )

    # -- actions ---------------------------------------------------------

    def apply_cache_ttl(self, ttl_seconds: int, evidence: Dict[str, Any]) -> AuditEntry:
        self._refuse_if_inactive()
        self._refuse_forbidden("cache_ttl")
        if not self._policy.cache_ttl_enabled:
            raise OptimizationRefused("cache_ttl scope is not enabled in the optimization policy")
        if not (self._policy.cache_ttl_min <= ttl_seconds <= self._policy.cache_ttl_max):
            raise OptimizationRefused(
                f"ttl {ttl_seconds}s outside the allowed range "
                f"[{self._policy.cache_ttl_min}, {self._policy.cache_ttl_max}] - refused, never clamped"
            )

        old = semantic_cache.effective_ttl_seconds()
        semantic_cache.set_runtime_ttl_override(ttl_seconds)
        entry = self._record("cache_ttl", old, ttl_seconds, evidence,
                             rollback=lambda: semantic_cache.set_runtime_ttl_override(None))
        logger.info("optimizer applied cache_ttl=%ss (was %ss)", ttl_seconds, old)
        return entry

    def apply_cache_enabled(self, model: str, enabled: bool, evidence: Dict[str, Any]) -> AuditEntry:
        """ADR-0309's "enablement per model": toggles the semantic cache
        for ONE provider-routing model name, but only if that name is in
        the policy's own cache_enabled.models allow-list - the tuner can
        never discover/spread to models a human didn't pre-approve for
        autonomous toggling. Substitutes for the per-model
        provider-routing flag only; the global deployment switch stays
        supreme (see semantic_cache.should_use_cache)."""
        self._refuse_if_inactive()
        self._refuse_forbidden(f"cache_enabled:{model}")
        if not self._policy.cache_enabled_scope:
            raise OptimizationRefused("cache_enabled scope is not enabled in the optimization policy")
        if model not in self._policy.cache_enabled_models:
            raise OptimizationRefused(
                f"model {model!r} is not in the cache_enabled scope's models allow-list - "
                "only a human-reviewed policy PR can add models (ADR-0309 boundary)"
            )

        old = semantic_cache._runtime_cache_enabled_overrides.get(model)
        semantic_cache.set_runtime_cache_enabled_override(model, enabled)

        def _rollback() -> None:
            semantic_cache.set_runtime_cache_enabled_override(model, old)

        entry = self._record(f"cache_enabled:{model}", old, enabled, evidence, rollback=_rollback)
        logger.info("optimizer applied cache_enabled[%s]=%s (was %s)", model, enabled, old)
        return entry

    def apply_routing_override(self, agent: str, task: str, adapter: str, evidence: Dict[str, Any]) -> AuditEntry:
        self._refuse_if_inactive()
        self._refuse_forbidden(f"routing:{agent}/{task}")
        if not self._policy.routing_enabled:
            raise OptimizationRefused("routing scope is not enabled in the optimization policy")

        approved = None
        for entry in self._policy.pre_approved_equivalents:
            if entry.get("agent") == agent and entry.get("task") == task:
                approved = entry.get("candidates", []) or []
                break
        if not approved or adapter not in approved:
            raise OptimizationRefused(
                f"adapter {adapter!r} for {agent}/{task} is not in the pre-approved equivalents list - "
                "only a human-reviewed policy PR can add candidates (ADR-0304/ADR-0309 boundary)"
            )

        key = (agent, task)
        old = self._adapter_overrides.get(key)
        self._adapter_overrides[key] = adapter

        def _rollback() -> None:
            if old is None:
                self._adapter_overrides.pop(key, None)
            else:
                self._adapter_overrides[key] = old

        entry = self._record(f"routing:{agent}/{task}", old, adapter, evidence, rollback=_rollback)
        logger.info("optimizer applied routing override %s/%s -> %s (was %s)", agent, task, adapter, old)
        return entry

    def _record(self, parameter: str, old: Any, new: Any, evidence: Dict[str, Any], rollback: Callable[[], None]) -> AuditEntry:
        now = time.time()
        entry = AuditEntry(parameter=parameter, old_value=old, new_value=new, evidence=evidence, applied_at=now)
        self._audit_log.append(entry)
        self._applied.append(_AppliedAction(
            audit=entry, rollback=rollback,
            window_ends_at=now + self._policy.evaluation_window_seconds,
        ))
        return entry

    # -- outcome monitoring / rollback -----------------------------------

    def report_outcome(self, error_rate: float, quality: Optional[float] = None) -> List[AuditEntry]:
        """Called with observed metrics for the current evaluation window
        (live: from the operator's monitoring feed; tests: directly).
        Reverts every still-open action if a rollback trigger breaches.
        Returns the entries that were rolled back (empty = all healthy)."""
        breached = error_rate > self._policy.max_error_rate or (
            quality is not None and quality < self._policy.quality_floor
        )
        if not breached:
            now = time.time()
            self._applied = [a for a in self._applied if a.window_ends_at > now]
            return []

        rolled_back = []
        for action in self._applied:
            action.rollback()
            action.audit.status = "rolled_back"
            action.audit.resolved_at = time.time()
            rolled_back.append(action.audit)
            logger.warning(
                "optimizer rolled back %s (%r -> %r): error_rate=%.3f quality=%s breached policy triggers",
                action.audit.parameter, action.audit.old_value, action.audit.new_value, error_rate, quality,
            )
        self._applied = []
        return rolled_back

    # -- kill switch ------------------------------------------------------

    def kill(self) -> List[AuditEntry]:
        """One call: refuse all future actions AND revert everything
        currently applied. Idempotent."""
        self._killed = True
        reverted = []
        for action in self._applied:
            action.rollback()
            action.audit.status = "reverted_by_kill"
            action.audit.resolved_at = time.time()
            reverted.append(action.audit)
        self._applied = []
        if reverted:
            logger.warning("optimizer kill switch engaged - reverted %d applied action(s)", len(reverted))
        else:
            logger.info("optimizer kill switch engaged - nothing was applied")
        return reverted
