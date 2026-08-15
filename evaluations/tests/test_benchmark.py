#!/usr/bin/env python3
"""ADR-0305 tests for evaluations/benchmark.py. Mocks
quality_gate.evaluate() (the subprocess boundary to a live cluster,
already proven independently by evaluations/tests/test_quality_gate.py)
to prove artifact construction, the LM-Eval file-input path, and the
"no artifact, no promotion" policy-enforcement check in isolation.

Run directly:

    cd evaluations && python3 tests/test_benchmark.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import benchmark  # noqa: E402


def _tmp_json(data) -> pathlib.Path:
    fd, path = tempfile.mkstemp(suffix=".json")
    with open(fd, "w") as fh:
        json.dump(data, fh)
    return pathlib.Path(path)


def _pass_gate(**overrides):
    base = {"agent": "comage", "candidate": "c", "scenario_rate": 0.85, "scenario_threshold": 0.75, "overall": "PASS"}
    base.update(overrides)
    return base


def test_build_artifact_overall_pass_requires_every_agent_gate_pass() -> None:
    gates = {"comage": _pass_gate(), "advantage": _pass_gate(agent="advantage")}
    artifact = benchmark.build_artifact("cand-1", {"mmlu": {"acc": 0.7}}, gates)
    assert artifact["overall"] == "PASS"


def test_build_artifact_overall_fail_if_any_agent_gate_fails() -> None:
    gates = {"comage": _pass_gate(), "advantage": _pass_gate(agent="advantage", overall="FAIL")}
    artifact = benchmark.build_artifact("cand-1", {}, gates)
    assert artifact["overall"] == "FAIL"


def test_build_artifact_overall_fail_when_no_agent_gates_requested() -> None:
    artifact = benchmark.build_artifact("cand-1", {"mmlu": {"acc": 0.9}}, {})
    assert artifact["overall"] == "FAIL"


def test_read_lm_eval_results_from_file() -> None:
    path = _tmp_json({"mmlu": {"acc": 0.71}})
    try:
        results = benchmark.read_lm_eval_results_from_file(str(path))
        assert results == {"mmlu": {"acc": 0.71}}
    finally:
        path.unlink()


def test_write_and_load_artifact_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = pathlib.Path(tmp)
        artifact = benchmark.build_artifact("cand-2", {}, {"tekos": _pass_gate(agent="tekos")})
        path = benchmark.write_artifact(artifact, out_dir)
        assert path.exists()
        loaded = benchmark.load_benchmark_artifact("cand-2", out_dir)
        assert loaded["candidate"] == "cand-2"
        assert loaded["overall"] == "PASS"


def test_load_benchmark_artifact_missing_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert benchmark.load_benchmark_artifact("no-such-candidate", pathlib.Path(tmp)) is None


def test_run_agent_gates_calls_quality_gate_evaluate_per_agent() -> None:
    with mock.patch("quality_gate.evaluate", side_effect=lambda agent, candidate: _pass_gate(agent=agent, candidate=candidate)) as evaluate:
        gates = benchmark.run_agent_gates(["comage", "tekos"], "cand-3")
    assert evaluate.call_count == 2
    assert set(gates.keys()) == {"comage", "tekos"}


def test_check_policy_artifacts_empty_adapters_list_is_clean() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        policy_path = pathlib.Path(tmp) / "policy.yaml"
        policy_path.write_text("adapters: []\n")
        violations = benchmark.check_policy_artifacts(policy_path, pathlib.Path(tmp) / "benchmarks")
        assert violations == []


def test_check_policy_artifacts_flags_a_declared_adapter_with_no_artifact() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        policy_path = pathlib.Path(tmp) / "policy.yaml"
        policy_path.write_text(
            "adapters:\n  - agent: comage\n    task: check-deal-status\n    adapter: comage-lora\n"
        )
        violations = benchmark.check_policy_artifacts(policy_path, pathlib.Path(tmp) / "benchmarks")
        assert len(violations) == 1
        assert "comage-lora" in violations[0]
        assert "no benchmark artifact" in violations[0]


def test_check_policy_artifacts_flags_a_failing_artifact() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        benchmarks_dir = pathlib.Path(tmp) / "benchmarks"
        benchmarks_dir.mkdir()
        artifact = benchmark.build_artifact("comage-lora", {}, {"comage": _pass_gate(overall="FAIL")})
        benchmark.write_artifact(artifact, benchmarks_dir)
        policy_path = pathlib.Path(tmp) / "policy.yaml"
        policy_path.write_text(
            "adapters:\n  - agent: comage\n    task: check-deal-status\n    adapter: comage-lora\n"
        )
        violations = benchmark.check_policy_artifacts(policy_path, benchmarks_dir)
        assert len(violations) == 1
        assert "not PASS" in violations[0]


def test_check_policy_artifacts_passes_when_artifact_exists_and_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        benchmarks_dir = pathlib.Path(tmp) / "benchmarks"
        benchmarks_dir.mkdir()
        artifact = benchmark.build_artifact("comage-lora", {}, {"comage": _pass_gate()})
        benchmark.write_artifact(artifact, benchmarks_dir)
        policy_path = pathlib.Path(tmp) / "policy.yaml"
        policy_path.write_text(
            "adapters:\n  - agent: comage\n    task: check-deal-status\n    adapter: comage-lora\n"
        )
        violations = benchmark.check_policy_artifacts(policy_path, benchmarks_dir)
        assert violations == []


def test_check_policy_artifacts_missing_policy_file_is_clean() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        violations = benchmark.check_policy_artifacts(pathlib.Path(tmp) / "nonexistent.yaml", pathlib.Path(tmp) / "benchmarks")
        assert violations == []


TESTS = [
    test_build_artifact_overall_pass_requires_every_agent_gate_pass,
    test_build_artifact_overall_fail_if_any_agent_gate_fails,
    test_build_artifact_overall_fail_when_no_agent_gates_requested,
    test_read_lm_eval_results_from_file,
    test_write_and_load_artifact_round_trip,
    test_load_benchmark_artifact_missing_returns_none,
    test_run_agent_gates_calls_quality_gate_evaluate_per_agent,
    test_check_policy_artifacts_empty_adapters_list_is_clean,
    test_check_policy_artifacts_flags_a_declared_adapter_with_no_artifact,
    test_check_policy_artifacts_flags_a_failing_artifact,
    test_check_policy_artifacts_passes_when_artifact_exists_and_passes,
    test_check_policy_artifacts_missing_policy_file_is_clean,
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
