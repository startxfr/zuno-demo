#!/usr/bin/env python3
"""ADR-0107 tests for evaluations/quality_gate.py. Mocks
run_acceptance_gate() (the subprocess boundary to a real agent's
run_scenarios.py/security_checks.py, which need a live cluster - see
those scripts' own docstrings) to prove the config-driven threshold
comparison and fail-closed unknown-agent behavior in isolation.

Same plain-function/no-pytest style as components/rag-service/tests/
test_search_filters.py, still pytest-collectible (the WP-10 brief's
acceptance check runs `python3 -m pytest evaluations/ -q`).

Run directly:

    cd evaluations && python3 tests/test_quality_gate.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import quality_gate

import quality_gate  # noqa: E402


def _summary(scenario_rate: float, security_pass: bool = True, gate_checks_pass: bool = True):
    return {
        "scenarios": {"passed": round(scenario_rate * 20), "total": 20, "rate": scenario_rate},
        "security_checks": {"result": "PASS" if security_pass else "FAIL"},
        "gate_checks": {"result": "PASS" if gate_checks_pass else "FAIL"},
        "overall": "irrelevant - quality_gate.py re-derives this itself",
    }


def test_load_gate_config_reads_the_real_tekos_config() -> None:
    """Proves the real evaluations/tekos/gate_config.yaml this WP added
    parses correctly, not just a synthetic fixture."""
    config = quality_gate.load_gate_config("tekos")
    assert config["scenario_threshold"] == 0.75


def test_load_gate_config_fails_closed_for_an_unknown_agent() -> None:
    try:
        quality_gate.load_gate_config("no-such-agent")
        raise AssertionError("expected QualityGateError")
    except quality_gate.QualityGateError as exc:
        assert "unknown agent" in str(exc)


def test_evaluate_passes_when_rate_meets_threshold_and_mandatory_gates_pass() -> None:
    with mock.patch.object(quality_gate, "run_acceptance_gate", return_value=_summary(0.75)):
        result = quality_gate.evaluate("tekos")
    assert result["scenario_ok"] is True
    assert result["overall"] == "PASS"


def test_evaluate_fails_when_rate_is_below_threshold() -> None:
    with mock.patch.object(quality_gate, "run_acceptance_gate", return_value=_summary(0.70)):
        result = quality_gate.evaluate("tekos")
    assert result["scenario_ok"] is False
    assert result["overall"] == "FAIL"


def test_evaluate_fails_when_security_checks_regress_even_with_perfect_scenario_rate() -> None:
    """ADR-0107: "no per-scenario security check regresses" - 100% mandatory,
    not part of the configurable quality threshold. A candidate cannot buy
    its way past a security regression with a high scenario pass rate."""
    with mock.patch.object(quality_gate, "run_acceptance_gate", return_value=_summary(1.0, security_pass=False)):
        result = quality_gate.evaluate("tekos")
    assert result["scenario_ok"] is True
    assert result["security_ok"] is False
    assert result["overall"] == "FAIL"


def test_evaluate_fails_when_gate_checks_regress() -> None:
    with mock.patch.object(quality_gate, "run_acceptance_gate", return_value=_summary(1.0, gate_checks_pass=False)):
        result = quality_gate.evaluate("tekos")
    assert result["gate_checks_ok"] is False
    assert result["overall"] == "FAIL"


def test_evaluate_honors_a_stricter_per_agent_threshold() -> None:
    """Proves the threshold is genuinely config-driven (ADR-0107:
    "Thresholds are data... not code") - a rate that would pass tekos's
    75% must fail an agent configured with a stricter 90%."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = pathlib.Path(tmpdir) / "strict-agent"
        agent_dir.mkdir()
        (agent_dir / "gate_config.yaml").write_text("scenario_threshold: 0.90\n")
        (agent_dir / "run_acceptance_gate.py").write_text("# stub, never executed - run_acceptance_gate is mocked\n")

        with mock.patch.object(quality_gate, "EVALUATIONS_DIR", pathlib.Path(tmpdir)), \
             mock.patch.object(quality_gate, "run_acceptance_gate", return_value=_summary(0.80)):
            result = quality_gate.evaluate("strict-agent")
    assert result["scenario_threshold"] == 0.90
    assert result["scenario_ok"] is False
    assert result["overall"] == "FAIL"


def test_candidate_label_is_threaded_through_unchanged() -> None:
    with mock.patch.object(quality_gate, "run_acceptance_gate", return_value=_summary(0.75)):
        result = quality_gate.evaluate("tekos", candidate="qwen3.6-27b-instruct-v2")
    assert result["candidate"] == "qwen3.6-27b-instruct-v2"


def test_main_exits_2_for_an_unknown_agent() -> None:
    with mock.patch.object(sys, "argv", ["quality_gate.py", "--agent", "no-such-agent"]):
        exit_code = quality_gate.main()
    assert exit_code == 2


def test_main_exits_0_on_pass_and_1_on_fail() -> None:
    with mock.patch.object(sys, "argv", ["quality_gate.py", "--agent", "tekos"]), \
         mock.patch.object(quality_gate, "run_acceptance_gate", return_value=_summary(0.75)):
        assert quality_gate.main() == 0

    with mock.patch.object(sys, "argv", ["quality_gate.py", "--agent", "tekos"]), \
         mock.patch.object(quality_gate, "run_acceptance_gate", return_value=_summary(0.10)):
        assert quality_gate.main() == 1


def test_run_acceptance_gate_reports_unparseable_output_loudly() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = pathlib.Path(tmpdir) / "broken-agent"
        agent_dir.mkdir()
        (agent_dir / "run_acceptance_gate.py").write_text("print('not json')\n")

        with mock.patch.object(quality_gate, "EVALUATIONS_DIR", pathlib.Path(tmpdir)):
            try:
                quality_gate.run_acceptance_gate("broken-agent")
                raise AssertionError("expected QualityGateError")
            except quality_gate.QualityGateError as exc:
                assert "could not parse" in str(exc)


TESTS = [
    test_load_gate_config_reads_the_real_tekos_config,
    test_load_gate_config_fails_closed_for_an_unknown_agent,
    test_evaluate_passes_when_rate_meets_threshold_and_mandatory_gates_pass,
    test_evaluate_fails_when_rate_is_below_threshold,
    test_evaluate_fails_when_security_checks_regress_even_with_perfect_scenario_rate,
    test_evaluate_fails_when_gate_checks_regress,
    test_evaluate_honors_a_stricter_per_agent_threshold,
    test_candidate_label_is_threaded_through_unchanged,
    test_main_exits_2_for_an_unknown_agent,
    test_main_exits_0_on_pass_and_1_on_fail,
    test_run_acceptance_gate_reports_unparseable_output_loudly,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
