"""ADR-0309 (WP-42) tests for app/optimizer.py - the WP's own named
acceptance cases: out-of-range recommendation refused; classification/
authorization parameters untouchable even if recommended; rollback fires
on simulated regression; kill switch halts pending actions (and reverts
applied ones); audit entries complete. Pure in-memory policy fixtures -
no live cluster, no file I/O beyond a temp policy file for the loader
tests.

Run from this directory:

    python3 tests/test_optimizer.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # noqa: E402

from app import semantic_cache  # noqa: E402
from app.optimizer import (  # noqa: E402
    OptimizationPolicy,
    OptimizationRefused,
    TuningController,
)


def _policy(**overrides) -> OptimizationPolicy:
    base = dict(
        enabled=True,
        kill_switch=False,
        evaluation_window_seconds=3600,
        max_error_rate=0.05,
        quality_floor=0.75,
        cache_ttl_enabled=True,
        cache_ttl_min=300,
        cache_ttl_max=86400,
        cache_enabled_scope=True,
        cache_enabled_models=["qwen2.5-7b-instruct"],
        routing_enabled=True,
        pre_approved_equivalents=[
            {"agent": "comage", "task": "check-deal-status", "candidates": ["comage-lora-v1", "comage-lora-v2"]},
        ],
    )
    base.update(overrides)
    return OptimizationPolicy(**base)


def _reset_cache_override() -> None:
    semantic_cache.set_runtime_ttl_override(None)
    semantic_cache._runtime_cache_enabled_overrides.clear()


def test_in_range_cache_ttl_is_applied_and_audited() -> None:
    _reset_cache_override()
    controller = TuningController(_policy())
    entry = controller.apply_cache_ttl(7200, evidence={"reason": "cost recommendation r-1"})
    assert semantic_cache.effective_ttl_seconds() == 7200
    assert entry.parameter == "cache_ttl"
    assert entry.new_value == 7200
    assert entry.status == "applied"
    assert entry.evidence == {"reason": "cost recommendation r-1"}
    assert entry.applied_at > 0
    _reset_cache_override()


def test_out_of_range_ttl_is_refused_never_clamped() -> None:
    _reset_cache_override()
    controller = TuningController(_policy())
    before = semantic_cache.effective_ttl_seconds()
    for bad in (10, 999999):
        try:
            controller.apply_cache_ttl(bad, evidence={})
            raise AssertionError(f"expected OptimizationRefused for ttl={bad}")
        except OptimizationRefused as exc:
            assert "outside the allowed range" in str(exc)
    assert semantic_cache.effective_ttl_seconds() == before, "a refused change must leave the value untouched"
    assert controller.audit_log() == [], "a refusal is not an applied change - nothing to audit as applied"


def test_autonomy_disabled_refuses_everything() -> None:
    controller = TuningController(_policy(enabled=False))
    try:
        controller.apply_cache_ttl(7200, evidence={})
        raise AssertionError("expected OptimizationRefused when autonomy is disabled")
    except OptimizationRefused as exc:
        assert "not enabled" in str(exc)


def test_classification_authorization_parameters_untouchable() -> None:
    """The code-level denylist fires regardless of policy content - the
    ADR's 'never auto-tunable' guarantee is structural, not
    configuration."""
    controller = TuningController(_policy())
    for forbidden in ("classification", "min_classification", "allowed_groups", "authorization_mode"):
        try:
            controller._refuse_forbidden(forbidden)
            raise AssertionError(f"expected OptimizationRefused for parameter {forbidden!r}")
        except OptimizationRefused as exc:
            assert "never auto-tunable" in str(exc)


def test_routing_override_only_between_pre_approved_equivalents() -> None:
    controller = TuningController(_policy())
    entry = controller.apply_routing_override("comage", "check-deal-status", "comage-lora-v2", evidence={"r": 1})
    assert controller.adapter_override("comage", "check-deal-status") == "comage-lora-v2"
    assert entry.parameter == "routing:comage/check-deal-status"

    try:
        controller.apply_routing_override("comage", "check-deal-status", "some-unapproved-adapter", evidence={})
        raise AssertionError("expected OptimizationRefused for a non-pre-approved candidate")
    except OptimizationRefused as exc:
        assert "pre-approved" in str(exc)

    try:
        controller.apply_routing_override("tekos", "answer-technical-question", "comage-lora-v2", evidence={})
        raise AssertionError("expected OptimizationRefused for an agent/task with no equivalents entry")
    except OptimizationRefused as exc:
        assert "pre-approved" in str(exc)


def test_cache_enabled_toggle_applied_for_an_allow_listed_model() -> None:
    """ADR-0309's "enablement per model": the toggle substitutes for the
    per-model provider-routing flag - proven end to end through
    should_use_cache(), with the global switch forced on."""
    _reset_cache_override()
    controller = TuningController(_policy())
    cfg = {"model": "qwen2.5-7b-instruct", "cache_enabled": True}
    orig_global = semantic_cache.SEMANTIC_CACHE_ENABLED
    semantic_cache.SEMANTIC_CACHE_ENABLED = True
    try:
        assert semantic_cache.should_use_cache(cfg) is True
        entry = controller.apply_cache_enabled("qwen2.5-7b-instruct", False, evidence={"reason": "low hit rate"})
        assert semantic_cache.should_use_cache(cfg) is False
        assert entry.parameter == "cache_enabled:qwen2.5-7b-instruct"
    finally:
        semantic_cache.SEMANTIC_CACHE_ENABLED = orig_global
        _reset_cache_override()


def test_cache_enabled_toggle_never_overrides_the_global_deployment_switch() -> None:
    """Autonomy tunes within the deployment's envelope, never widens it:
    enabling a model's cache while SEMANTIC_CACHE_ENABLED is false must
    still leave the cache off."""
    _reset_cache_override()
    controller = TuningController(_policy())
    cfg = {"model": "qwen2.5-7b-instruct", "cache_enabled": False}
    orig_global = semantic_cache.SEMANTIC_CACHE_ENABLED
    semantic_cache.SEMANTIC_CACHE_ENABLED = False
    try:
        controller.apply_cache_enabled("qwen2.5-7b-instruct", True, evidence={})
        assert semantic_cache.should_use_cache(cfg) is False, "global off must always win"
    finally:
        semantic_cache.SEMANTIC_CACHE_ENABLED = orig_global
        _reset_cache_override()


def test_cache_enabled_refused_for_a_model_not_in_the_allow_list() -> None:
    controller = TuningController(_policy())
    try:
        controller.apply_cache_enabled("some-other-model", False, evidence={})
        raise AssertionError("expected OptimizationRefused for a non-allow-listed model")
    except OptimizationRefused as exc:
        assert "allow-list" in str(exc)


def test_cache_enabled_toggle_reverts_on_rollback_and_kill() -> None:
    _reset_cache_override()
    controller = TuningController(_policy())
    controller.apply_cache_enabled("qwen2.5-7b-instruct", False, evidence={})
    assert semantic_cache._runtime_cache_enabled_overrides == {"qwen2.5-7b-instruct": False}
    rolled_back = controller.report_outcome(error_rate=0.9)
    assert len(rolled_back) == 1
    assert semantic_cache._runtime_cache_enabled_overrides == {}

    controller2 = TuningController(_policy())
    controller2.apply_cache_enabled("qwen2.5-7b-instruct", False, evidence={})
    reverted = controller2.kill()
    assert len(reverted) == 1
    assert semantic_cache._runtime_cache_enabled_overrides == {}


def test_rollback_fires_on_simulated_regression() -> None:
    _reset_cache_override()
    controller = TuningController(_policy())
    controller.apply_cache_ttl(7200, evidence={})
    controller.apply_routing_override("comage", "check-deal-status", "comage-lora-v1", evidence={})

    rolled_back = controller.report_outcome(error_rate=0.5)
    assert len(rolled_back) == 2
    assert semantic_cache.effective_ttl_seconds() == semantic_cache.SEMANTIC_CACHE_TTL_SECONDS
    assert controller.adapter_override("comage", "check-deal-status") is None
    assert all(e.status == "rolled_back" and e.resolved_at is not None for e in rolled_back)


def test_quality_floor_breach_also_triggers_rollback() -> None:
    _reset_cache_override()
    controller = TuningController(_policy())
    controller.apply_cache_ttl(7200, evidence={})
    rolled_back = controller.report_outcome(error_rate=0.0, quality=0.5)
    assert len(rolled_back) == 1
    assert semantic_cache.effective_ttl_seconds() == semantic_cache.SEMANTIC_CACHE_TTL_SECONDS


def test_healthy_outcome_rolls_nothing_back() -> None:
    _reset_cache_override()
    controller = TuningController(_policy())
    controller.apply_cache_ttl(7200, evidence={})
    assert controller.report_outcome(error_rate=0.01, quality=0.9) == []
    assert semantic_cache.effective_ttl_seconds() == 7200
    _reset_cache_override()


def test_kill_switch_halts_and_reverts_everything() -> None:
    _reset_cache_override()
    controller = TuningController(_policy())
    controller.apply_cache_ttl(7200, evidence={})
    controller.apply_routing_override("comage", "check-deal-status", "comage-lora-v2", evidence={})

    reverted = controller.kill()
    assert len(reverted) == 2
    assert semantic_cache.effective_ttl_seconds() == semantic_cache.SEMANTIC_CACHE_TTL_SECONDS
    assert controller.adapter_override("comage", "check-deal-status") is None
    assert all(e.status == "reverted_by_kill" for e in reverted)

    try:
        controller.apply_cache_ttl(7200, evidence={})
        raise AssertionError("expected OptimizationRefused after kill()")
    except OptimizationRefused as exc:
        assert "kill switch" in str(exc)


def test_kill_switch_in_policy_refuses_actions() -> None:
    controller = TuningController(_policy(kill_switch=True))
    try:
        controller.apply_cache_ttl(7200, evidence={})
        raise AssertionError("expected OptimizationRefused with kill_switch: true in policy")
    except OptimizationRefused as exc:
        assert "kill switch" in str(exc)


def test_audit_entries_are_complete() -> None:
    _reset_cache_override()
    controller = TuningController(_policy())
    controller.apply_cache_ttl(7200, evidence={"recommendation_id": "r-42", "reason": "latency"})
    log = controller.audit_log()
    assert len(log) == 1
    entry = log[0]
    for required in ("parameter", "old_value", "new_value", "evidence", "applied_at", "status"):
        assert entry[required] is not None, f"audit entry missing {required}"
    assert entry["evidence"]["recommendation_id"] == "r-42"
    _reset_cache_override()


def test_policy_loader_defaults_to_fully_disabled() -> None:
    policy = OptimizationPolicy.load("/nonexistent/optimization-policy.yaml")
    assert policy.enabled is False
    assert policy.kill_switch is False


def test_policy_loader_reads_the_real_repo_policy_file() -> None:
    repo_policy = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "policies", "optimization", "optimization-policy.yaml",
    )
    policy = OptimizationPolicy.load(repo_policy)
    assert policy.enabled is False, "shipped default must be autonomy off"
    assert policy.cache_ttl_enabled is True
    assert policy.pre_approved_equivalents == []


def test_reload_policy_with_kill_switch_engages_kill() -> None:
    _reset_cache_override()
    controller = TuningController(_policy())
    controller.apply_cache_ttl(7200, evidence={})

    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as fh:
        yaml.safe_dump({"enabled": True, "kill_switch": True}, fh)
    try:
        controller.reload_policy(path)
    finally:
        os.unlink(path)

    assert semantic_cache.effective_ttl_seconds() == semantic_cache.SEMANTIC_CACHE_TTL_SECONDS
    log = controller.audit_log()
    assert log[-1]["status"] == "reverted_by_kill"


TESTS = [
    test_in_range_cache_ttl_is_applied_and_audited,
    test_out_of_range_ttl_is_refused_never_clamped,
    test_autonomy_disabled_refuses_everything,
    test_classification_authorization_parameters_untouchable,
    test_routing_override_only_between_pre_approved_equivalents,
    test_cache_enabled_toggle_applied_for_an_allow_listed_model,
    test_cache_enabled_toggle_never_overrides_the_global_deployment_switch,
    test_cache_enabled_refused_for_a_model_not_in_the_allow_list,
    test_cache_enabled_toggle_reverts_on_rollback_and_kill,
    test_rollback_fires_on_simulated_regression,
    test_quality_floor_breach_also_triggers_rollback,
    test_healthy_outcome_rolls_nothing_back,
    test_kill_switch_halts_and_reverts_everything,
    test_kill_switch_in_policy_refuses_actions,
    test_audit_entries_are_complete,
    test_policy_loader_defaults_to_fully_disabled,
    test_policy_loader_reads_the_real_repo_policy_file,
    test_reload_policy_with_kill_switch_engages_kill,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    semantic_cache.set_runtime_ttl_override(None)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
