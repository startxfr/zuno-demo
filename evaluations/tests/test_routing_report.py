#!/usr/bin/env python3
"""ADR-0304 tests for evaluations/routing_report.py. Pure in-memory
fixtures (no live metrics endpoint, no real benchmark artifacts needed) -
proves the WP's own two named acceptance cases: a regression produces a
downgrade recommendation, an improvement produces an upgrade one.

Run directly:

    cd evaluations && python3 tests/test_routing_report.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import routing_report  # noqa: E402


def _objective(**overrides) -> routing_report.Objective:
    base = dict(agent="comage", task="check-deal-status", quality_floor=0.75, cost_ceiling_usd_per_1k=0.01, latency_target_ms_p95=2000)
    base.update(overrides)
    return routing_report.Objective(**base)


def _artifact(candidate: str, agent: str, scenario_rate: float, overall: str = "PASS"):
    return {
        "candidate": candidate,
        "agent_gates": {agent: {"overall": overall, "scenario_rate": scenario_rate}},
    }


def test_clean_state_produces_no_recommendations() -> None:
    objectives = [_objective()]
    metrics = {"comage": {"check-deal-status": {"cost_usd_per_1k": 0.005, "latency_ms_p95": 1500}}}
    recs = routing_report.generate_report(objectives, metrics, artifacts=[], adapters={})
    assert recs == []


def test_cost_regression_produces_a_downgrade_recommendation() -> None:
    objectives = [_objective()]
    metrics = {"comage": {"check-deal-status": {"cost_usd_per_1k": 0.05, "latency_ms_p95": 1500}}}
    recs = routing_report.generate_report(objectives, metrics, artifacts=[], adapters={("comage", "check-deal-status"): "comage-lora-v1"})
    downgrades = [r for r in recs if r.kind == "downgrade"]
    assert len(downgrades) == 1
    assert downgrades[0].candidate == "comage-lora-v1"
    assert "cost" in downgrades[0].reason


def test_latency_regression_produces_a_downgrade_recommendation() -> None:
    objectives = [_objective()]
    metrics = {"comage": {"check-deal-status": {"cost_usd_per_1k": 0.005, "latency_ms_p95": 9000}}}
    recs = routing_report.generate_report(objectives, metrics, artifacts=[], adapters={})
    downgrades = [r for r in recs if r.kind == "downgrade"]
    assert len(downgrades) == 1
    assert downgrades[0].candidate == "(base model)"
    assert "latency" in downgrades[0].reason


def test_quality_improvement_produces_an_upgrade_recommendation() -> None:
    objectives = [_objective()]
    artifacts = [_artifact("comage-lora-v2", "comage", scenario_rate=0.9)]
    recs = routing_report.generate_report(objectives, metrics={}, artifacts=artifacts, adapters={})
    upgrades = [r for r in recs if r.kind == "upgrade"]
    assert len(upgrades) == 1
    assert upgrades[0].candidate == "comage-lora-v2"


def test_candidate_already_incumbent_is_never_recommended_as_an_upgrade() -> None:
    objectives = [_objective()]
    artifacts = [_artifact("comage-lora-v1", "comage", scenario_rate=0.95)]
    recs = routing_report.generate_report(
        objectives, metrics={}, artifacts=artifacts, adapters={("comage", "check-deal-status"): "comage-lora-v1"}
    )
    assert [r for r in recs if r.kind == "upgrade"] == []


def test_candidate_below_quality_floor_is_not_recommended() -> None:
    objectives = [_objective()]
    artifacts = [_artifact("comage-lora-weak", "comage", scenario_rate=0.5)]
    recs = routing_report.generate_report(objectives, metrics={}, artifacts=artifacts, adapters={})
    assert recs == []


def test_failing_artifact_is_never_recommended_regardless_of_scenario_rate() -> None:
    objectives = [_objective()]
    artifacts = [_artifact("comage-lora-broken", "comage", scenario_rate=0.99, overall="FAIL")]
    recs = routing_report.generate_report(objectives, metrics={}, artifacts=artifacts, adapters={})
    assert recs == []


def test_objective_with_no_quality_floor_skips_upgrade_scan() -> None:
    objectives = [_objective(quality_floor=None)]
    artifacts = [_artifact("comage-lora-v2", "comage", scenario_rate=0.99)]
    recs = routing_report.generate_report(objectives, metrics={}, artifacts=artifacts, adapters={})
    assert [r for r in recs if r.kind == "upgrade"] == []


def test_current_adapters_parses_policy_adapters_list() -> None:
    policy = {"adapters": [{"agent": "comage", "task": "check-deal-status", "adapter": "comage-lora-v1"}]}
    assert routing_report.current_adapters(policy) == {("comage", "check-deal-status"): "comage-lora-v1"}


def test_load_objectives_skips_entries_missing_agent_or_task() -> None:
    policy = {"objectives": [{"agent": "comage"}, {"agent": "comage", "task": "check-deal-status", "quality_floor": 0.8}]}
    objectives = routing_report.load_objectives(policy)
    assert len(objectives) == 1
    assert objectives[0].quality_floor == 0.8


TESTS = [
    test_clean_state_produces_no_recommendations,
    test_cost_regression_produces_a_downgrade_recommendation,
    test_latency_regression_produces_a_downgrade_recommendation,
    test_quality_improvement_produces_an_upgrade_recommendation,
    test_candidate_already_incumbent_is_never_recommended_as_an_upgrade,
    test_candidate_below_quality_floor_is_not_recommended,
    test_failing_artifact_is_never_recommended_regardless_of_scenario_rate,
    test_objective_with_no_quality_floor_skips_upgrade_scan,
    test_current_adapters_parses_policy_adapters_list,
    test_load_objectives_skips_entries_missing_agent_or_task,
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
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
