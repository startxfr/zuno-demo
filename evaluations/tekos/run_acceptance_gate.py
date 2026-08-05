#!/usr/bin/env python3
"""ADR-0053: the single entrypoint `make check` invokes (via the
acceptance-gate Job - ansible/roles/agents/tasks/check.yml). Combines three
independently-runnable layers into one gate with one exit code:

  - run_scenarios.py   - the 20 fixed Tekos acceptance scenarios (ADR-0027),
                          a 75% pass-rate quality threshold (ADR-0028).
  - security_checks.py - security-negative checks (ADR-0032/0033/0034/0035/
                          0037/0040), 100% mandatory.
  - gate_checks.py      - remaining ADR-0053 capability checks not covered
                          by the two above (currently: permitted SaaS
                          fallback), 100% mandatory.

Per ADR-0053's Operational considerations ("Return machine-readable results
and non-zero exit status when mandatory gates fail. Preserve the 75%
quality threshold while making security checks 100% mandatory."): overall
result is PASS only if the scenario pass rate is >= 75% AND every
security_checks/gate_checks check passes. A final line of JSON is always
printed after the human-readable tables so a caller (this repository's own
ansible task, or any future CI consumer) can parse the result without
scraping text.
"""
from __future__ import annotations

import json
import sys

import gate_checks
import run_scenarios
import security_checks

SCENARIO_THRESHOLD = 0.75


def main() -> int:
    scenario_results = run_scenarios.run()
    security_results = security_checks.run()
    gate_results = gate_checks.run()

    scenario_passed = sum(1 for r in scenario_results if r.passed)
    scenario_total = len(scenario_results)
    scenario_rate = scenario_passed / scenario_total if scenario_total else 0.0
    scenario_ok = scenario_rate >= SCENARIO_THRESHOLD

    security_passed = sum(1 for r in security_results if r.passed)
    security_total = len(security_results)
    security_ok = security_passed == security_total

    gate_passed = sum(1 for r in gate_results if r.passed)
    gate_total = len(gate_results)
    gate_ok = gate_passed == gate_total

    overall_ok = scenario_ok and security_ok and gate_ok

    print("=== Layer 1/3: Tekos acceptance scenarios (ADR-0027/0028, 75% threshold) ===")
    print(f"{'ID':<4}{'PASS':<6}{'TITLE'}")
    for r in scenario_results:
        print(f"{r.id:<4}{'✓' if r.passed else '✗':<6}{r.title}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")
    print(f"{scenario_passed}/{scenario_total} passed ({scenario_rate:.0%}) - threshold {SCENARIO_THRESHOLD:.0%}\n")

    print("=== Layer 2/3: Security-negative checks (100% mandatory) ===")
    print(f"{'PASS':<6}{'CHECK'}")
    for r in security_results:
        print(f"{'✓' if r.passed else '✗':<6}{r.name}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")
    print(f"{security_passed}/{security_total} passed\n")

    print("=== Layer 3/3: Additional capability gates (100% mandatory) ===")
    print(f"{'PASS':<6}{'CHECK'}")
    for r in gate_results:
        print(f"{'✓' if r.passed else '✗':<6}{r.name}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")
    print(f"{gate_passed}/{gate_total} passed\n")

    print(f"OVERALL RESULT: {'PASS' if overall_ok else 'FAIL'}")

    summary = {
        "scenarios": {
            "passed": scenario_passed,
            "total": scenario_total,
            "rate": round(scenario_rate, 4),
            "threshold": SCENARIO_THRESHOLD,
            "gate": "quality",
            "result": "PASS" if scenario_ok else "FAIL",
        },
        "security_checks": {
            "passed": security_passed,
            "total": security_total,
            "gate": "mandatory",
            "result": "PASS" if security_ok else "FAIL",
        },
        "gate_checks": {
            "passed": gate_passed,
            "total": gate_total,
            "gate": "mandatory",
            "result": "PASS" if gate_ok else "FAIL",
        },
        "overall": "PASS" if overall_ok else "FAIL",
    }
    print(json.dumps(summary))

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
