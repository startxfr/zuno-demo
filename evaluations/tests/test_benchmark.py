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


def _fake_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


def test_read_lm_eval_results_from_cluster_uses_exec_when_driver_pod_present() -> None:
    """ADR-0108: the CR's own status.results never populates (real,
    confirmed-live TrustyAI operator bug), so the primary path reads the
    driver pod's own results file directly via `oc exec` - never
    consulting the CR at all."""
    results_json = json.dumps({"results": {"mmlu_abstract_algebra": {"acc,none": 0.57}}})
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["oc", "get", "pvc"]:
            return _fake_run(0, "persistentvolumeclaims/job-pvc")
        if cmd[:3] == ["oc", "get", "pod"]:
            return _fake_run(0, "pod/job")
        if cmd[:2] == ["oc", "exec"]:
            return _fake_run(0, results_json)
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    with mock.patch("benchmark.subprocess.run", side_effect=run):
        results = benchmark.read_lm_eval_results_from_cluster("job", namespace="ns")
    assert results == {"mmlu_abstract_algebra": {"acc,none": 0.57}}
    assert any(cmd[:2] == ["oc", "exec"] for cmd in calls)
    assert not any(cmd[:2] == ["oc", "apply"] for cmd in calls)  # no reader-pod fallback needed


def test_read_lm_eval_results_from_cluster_falls_back_to_reader_pod_when_driver_pod_gone() -> None:
    results_json = json.dumps({"results": {"mmlu_abstract_algebra": {"acc,none": 0.57}}})

    def run(cmd, **kwargs):
        if cmd[:3] == ["oc", "get", "pvc"]:
            return _fake_run(0, "persistentvolumeclaims/job-pvc")
        if cmd[:3] == ["oc", "get", "pod"]:
            return _fake_run(1, "", "not found")
        if cmd[:3] == ["oc", "delete", "pod"]:
            return _fake_run(0)
        if cmd[:2] == ["oc", "apply"]:
            return _fake_run(0)
        if cmd[:2] == ["oc", "wait"]:
            return _fake_run(0)
        if cmd[:2] == ["oc", "logs"]:
            return _fake_run(0, results_json)
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    with mock.patch("benchmark.subprocess.run", side_effect=run):
        results = benchmark.read_lm_eval_results_from_cluster("job", namespace="ns")
    assert results == {"mmlu_abstract_algebra": {"acc,none": 0.57}}


def test_read_lm_eval_results_from_cluster_raises_when_no_output_pvc() -> None:
    def run(cmd, **kwargs):
        if cmd[:3] == ["oc", "get", "pvc"]:
            return _fake_run(1, "", "not found")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    with mock.patch("benchmark.subprocess.run", side_effect=run):
        try:
            benchmark.read_lm_eval_results_from_cluster("job", namespace="ns")
        except benchmark.BenchmarkError as exc:
            assert "no output PVC" in str(exc)
        else:
            raise AssertionError("expected BenchmarkError")


def test_read_results_via_exec_raises_when_no_results_file_found() -> None:
    def run(cmd, **kwargs):
        return _fake_run(1, "", "no results_*.json found under /opt/app-root/src/output")

    with mock.patch("benchmark.subprocess.run", side_effect=run):
        try:
            benchmark._read_results_via_exec("job", "ns")
        except benchmark.BenchmarkError as exc:
            assert "could not read results" in str(exc)
        else:
            raise AssertionError("expected BenchmarkError")


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
    test_read_lm_eval_results_from_cluster_uses_exec_when_driver_pod_present,
    test_read_lm_eval_results_from_cluster_falls_back_to_reader_pod_when_driver_pod_gone,
    test_read_lm_eval_results_from_cluster_raises_when_no_output_pvc,
    test_read_results_via_exec_raises_when_no_results_file_found,
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
