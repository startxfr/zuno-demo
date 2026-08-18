#!/usr/bin/env python3
"""ADR-0504 (roadmap WP-46) per-agent contract-test runner.

The contract layer sits between the two verification layers the platform
already has, duplicating neither:
  - schema/structural (platform-wide, agent-agnostic):
    platform/supply-chain/validate_okf_bundle.py, the JSON Schemas,
    check_knowledge_refs.py;
  - behavioral (per-agent, cluster-side, gate-scoped):
    evaluations/<name>/ under ADR-0027/ADR-0028, run by the shared
    ADR-0342 runner.
Contract tests are per-agent, repo-side, static: bundle
self-consistency, per-task assertions and prompt lint, living in
agents/<name>/tests/{contract,tasks,prompts}/ (ADR-0504 clause 1).

This runner does two things:
  - STRUCTURE (always): every agents/<name>/tests/ directory that
    exists must contain the three subdirectories and a README - a
    Stage-2/reserved-structure shape with a half-built tests/ dir is a
    structure violation (exit non-zero). Stage-1 agents have no tests/
    directory at all, by design (born at promotion - PROMOTION.md
    step 4); their absence is not a finding.
  - CONTENT (when present): each test_*.py found under those
    subdirectories is executed (exit code aggregated). Zero content is
    a valid state ("structure present, no suites yet") - filling the
    suites is promotion-time work, explicitly out of scope for WP-46.

Usage (from the repository root):

    python3 platform/okf/run_agent_contract_tests.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
from typing import List

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"
REQUIRED_SUBDIRS = ("contract", "tasks", "prompts")


def main() -> int:
    findings: List[str] = []
    for agent_dir in sorted(p for p in AGENTS_DIR.iterdir() if p.is_dir()):
        tests_dir = agent_dir / "tests"
        if not tests_dir.is_dir():
            continue  # Stage 1 (ADR-0502): tests/ is born at promotion.

        # The per-subdir READMEs double as the keep-files defining what
        # belongs in each suite - a missing one is a structure violation,
        # not an empty-content state.
        missing = [s for s in REQUIRED_SUBDIRS if not (tests_dir / s).is_dir()]
        missing += [f"{s}/README.md" for s in REQUIRED_SUBDIRS
                    if (tests_dir / s).is_dir() and not (tests_dir / s / "README.md").is_file()]
        if missing:
            findings.append(f"{agent_dir.name}: tests/ missing: {', '.join(missing)} (ADR-0504 clause 1)")
        if not (tests_dir / "README.md").is_file():
            findings.append(f"{agent_dir.name}: tests/README.md missing (ADR-0504 clause 1)")
        if missing or not (tests_dir / "README.md").is_file():
            continue

        suites = sorted(tests_dir.glob("*/test_*.py"))
        if not suites:
            print(f"  {agent_dir.name}: structure present, no suites yet")
            continue
        for suite in suites:
            result = subprocess.run([sys.executable, str(suite)], cwd=REPO_ROOT)
            status = "ok" if result.returncode == 0 else "FAIL"
            print(f"  {agent_dir.name}: {suite.relative_to(tests_dir)} ... {status}")
            if result.returncode != 0:
                findings.append(f"{agent_dir.name}: {suite.relative_to(REPO_ROOT)} exited {result.returncode}")

    if findings:
        print(f"\n{len(findings)} contract-test issue(s):")
        for f in findings:
            print(f"  ✗ {f}")
        print("\nRESULT: FAIL - fix the structure or the failing suites (ADR-0504).")
        return 1
    print("\nRESULT: PASS - agent contract-test structure valid; all present suites green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
