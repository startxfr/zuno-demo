#!/usr/bin/env python3
"""ADR-0058 decision 1 (contract layer): runs
platform/okf/run_agent_contract_tests.py once - it has no per-agent CLI
hook, always scanning every agents/*/tests/ in one invocation - and
parses its per-agent-prefixed stdout lines into
platform/testing/day2_report.py::Day2Result rows, one call, not one per
agent. Needs no cluster access (same as the script it wraps), so this
runs directly from the control node, not inside any Day 2 Job.

Prints one JSON array of Day2Result-shaped dicts to stdout.

Run from the repository root:

    python3 platform/testing/day2_contract_attribution.py
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
from dataclasses import asdict

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_RUNNER = REPO_ROOT / "platform" / "okf" / "run_agent_contract_tests.py"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from day2_report import Day2Result  # noqa: E402

# Mirrors run_agent_contract_tests.py's own two print shapes exactly:
#   f"  {agent_dir.name}: structure present, no suites yet"
#   f"  {agent_dir.name}: {suite.relative_to(tests_dir)} ... {status}"
_COVERAGE_RE = re.compile(r"^  (?P<agent>\S+): structure present, no suites yet$")
_SUITE_RE = re.compile(r"^  (?P<agent>\S+): (?P<suite>\S+) \.\.\. (?P<status>ok|FAIL)$")


def run() -> "list[Day2Result]":
    proc = subprocess.run(
        [sys.executable, str(CONTRACT_RUNNER)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    results: "list[Day2Result]" = []
    for line in proc.stdout.splitlines():
        coverage_match = _COVERAGE_RE.match(line)
        if coverage_match:
            results.append(Day2Result(
                coverage_match["agent"], "contract", "n/a", "coverage", True,
                "structure present, no suites yet",
            ))
            continue
        suite_match = _SUITE_RE.match(line)
        if suite_match:
            passed = suite_match["status"] == "ok"
            results.append(Day2Result(
                suite_match["agent"], "contract", suite_match["suite"], "contract", passed,
                "" if passed else f"{suite_match['suite']} exited non-zero",
            ))
    # A repo-side structure violation (agents/*/tests/ missing a required
    # subdir/README) never prints per-agent per-suite lines for that
    # agent, so it wouldn't otherwise surface as a row - fall back to one
    # whole-run failure row when the runner failed but produced no
    # per-agent lines this parser recognized.
    if proc.returncode != 0 and not results:
        results.append(Day2Result(
            "all", "contract", "n/a", "structure", False,
            "run_agent_contract_tests.py failed - see its own output for the structure violation",
        ))
    return results


def main() -> int:
    results = run()
    print(json.dumps([asdict(r) for r in results]))
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
