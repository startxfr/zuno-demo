#!/usr/bin/env python3
"""ADR-0058: per-agent Day 2 stresstest entrypoint, run inside the
generalized per-agent Job (ansible/roles/day2/tasks/stresstest_job.yml).
The Job is recreated once per agent (not looped internally) - AGENT names
which one this particular run is for, set by the Ansible task loop the
same way evaluations/<agent>/run_scenarios.py's thin wrappers already set
it (ADR-0342/WP-31).

Best-effort runs whichever of these layers apply to AGENT, normalizing
every result into platform/testing/day2_report.py::Day2Result:
  - run_scenarios.py    - every agent (the shared, AGENT-parameterized
                           acceptance-scenario runner).
  - security_checks.py  - every agent, dynamically loaded the same way
                           evaluations/tekos/run_acceptance_gate.py's own
                           _load_security_checks() already does (a static
                           top-level import would only ever resolve to
                           whichever agent's module sys.path finds first).
  - gate_checks.py       - Tekos only (no other agent has this file or a
                           wrapper for it - see ADR-0058's Context).
  - stress_test.py       - Tekos only (same reason).
An agent missing a given layer's file gets one explicit "coverage" row
instead of a failure - ADR-0058 decision 1's informational, non-blocking
posture.

Prints one JSON array of Day2Result-shaped dicts to stdout. The calling
Ansible task fetches this Job's pod log and folds it into the overall
cross-agent report, rendered on the control node by
platform/testing/day2_report.py - the same split
ansible/tasks/day2_availability_check.yml and
ansible/roles/day2/tasks/platform_health_check.yml already use.

Contract tests (platform/okf/run_agent_contract_tests.py) are
deliberately NOT run here: that script has no per-agent hook and needs no
cluster access at all, so it runs once, directly from the control node
(platform/testing/day2_contract_attribution.py) - running it once per
agent inside this Job would just repeat the same whole-repo scan six
times for no benefit.

Bulk-interaction load mode (ADR-0058 decision 3) is a separate script,
platform/testing/day2_bulk.py, invoked by the same Job when
BULK_INTERACTIONS is set and > 0 - kept separate so a plain stresstest
run (no bulk mode) never pays for it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
from dataclasses import asdict
from typing import List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from day2_report import Day2Result  # noqa: E402

AGENT = os.getenv("AGENT", "tekos")
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent


def _load_security_checks():
    """Mirrors evaluations/tekos/run_acceptance_gate.py's own
    _load_security_checks(): registers the module in sys.modules before
    exec_module() runs, since security_checks.py's @dataclass needs
    sys.modules[cls.__module__] to already resolve to something.
    """
    path = SCRIPT_DIR / AGENT / "security_checks.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("security_checks", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _safe_run(layer: str, fn) -> List[Day2Result]:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a layer erroring is one failed row, not a crashed script
        return [Day2Result(AGENT, layer, "error", "error", False, f"unhandled error: {exc}")]


def _scenario_results() -> List[Day2Result]:
    import run_scenarios

    return [
        Day2Result(AGENT, "scenario", str(r.id), "acceptance", r.passed, r.detail)
        for r in run_scenarios.run()
    ]


def _security_results() -> List[Day2Result]:
    module = _load_security_checks()
    if module is None:
        return [Day2Result(AGENT, "security", "n/a", "coverage", True, "no security_checks.py for this agent")]
    return [
        Day2Result(AGENT, "security", r.name, "security", r.passed, r.detail)
        for r in module.run()
    ]


def _gate_check_results() -> List[Day2Result]:
    if AGENT != "tekos":
        return [Day2Result(AGENT, "gate", "n/a", "coverage", True, "gate_checks.py is Tekos-only today")]
    import gate_checks

    return [
        Day2Result(AGENT, "gate", r.name, "gate", r.passed, r.detail)
        for r in gate_checks.run()
    ]


def _stress_test_results() -> List[Day2Result]:
    if AGENT != "tekos":
        return [Day2Result(AGENT, "stress_test", "n/a", "coverage", True, "stress_test.py is Tekos-only today")]
    import stress_test

    return [
        Day2Result(AGENT, "stress_test", r.id, r.category, r.passed, r.detail)
        for r in stress_test.run()
    ]


def main() -> int:
    results: List[Day2Result] = []
    results += _safe_run("scenario", _scenario_results)
    results += _safe_run("security", _security_results)
    results += _safe_run("gate", _gate_check_results)
    results += _safe_run("stress_test", _stress_test_results)

    print(json.dumps([asdict(r) for r in results]))
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
