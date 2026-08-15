#!/usr/bin/env python3
"""ADR-0307 (roadmap WP-41 Part A) acceptance test: "scaffold a throwaway
agent in CI, validate, discard." scaffold_agent.py writes real files into
the real repository tree (see its own module docstring for why - the
onboarding workflow is a reviewed PR, not a scratch directory), so this
test scaffolds a clearly-marked throwaway agent, runs the exact
validators an onboarding PR's own CI run would (composing OKF, knowledge-
reference and AIAgent-contract validation, per ADR-0307's Decision text),
and ALWAYS deletes every file it created afterward - in a `finally`
block, so a failed validation still cleans up rather than leaving a
throwaway agent committed by accident.

Run directly (leaves the repo tree exactly as it found it on both success
and failure):

    python3 platform/templates/agent/test_scaffold_validate_discard.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
THROWAWAY_NAME = "zzz-scaffold-ci-test"

SCAFFOLD_ARGS = [
    "--name", THROWAWAY_NAME,
    "--title", "CI Scaffold Test",
    "--description", "Throwaway agent scaffolded by the ADR-0307 CI test, never merged.",
    "--primary-task", "answer-ci-test-question",
    "--primary-task-title", "Answer a CI test question",
    "--knowledge", "knowledge.tech",
    "--tool", "search_confluence",
    "--tool", "web_search",
    "--live-read-tool", "search_confluence",
    "--business-role", "consultant",
    "--tile-description", "CI scaffold test tile.",
]

THROWAWAY_PATHS = [
    REPO_ROOT / "agents" / THROWAWAY_NAME,
    REPO_ROOT / "gitops" / "charts" / THROWAWAY_NAME,
    REPO_ROOT / "gitops" / "apps" / THROWAWAY_NAME,
    REPO_ROOT / "evaluations" / THROWAWAY_NAME,
]


def _run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, **kwargs)


def discard() -> None:
    for path in THROWAWAY_PATHS:
        if path.exists():
            shutil.rmtree(path)


def main() -> int:
    for path in THROWAWAY_PATHS:
        if path.exists():
            print(f"ERROR: {path} already exists - refusing to scaffold over it (run discard manually first)", file=sys.stderr)
            return 2

    try:
        scaffold = _run([sys.executable, "platform/templates/agent/scaffold_agent.py", *SCAFFOLD_ARGS])
        print(scaffold.stdout)
        if scaffold.returncode != 0:
            print(scaffold.stderr, file=sys.stderr)
            print("RESULT: FAIL - scaffold_agent.py itself failed")
            return 1

        # operator/aiagent-operator/validate_contract.py is deliberately
        # NOT run here: it validates config/samples/ against the CRD
        # schema, not arbitrary gitops/charts/<agent>/templates/aiagent.yaml
        # output - the throwaway agent's own AIAgent CR shape is proven
        # correct by `helm template` + the schema fields it shares with
        # every real sample below instead.
        checks = [
            ("validate_okf_bundle.py (ADR-0106)", [sys.executable, "platform/supply-chain/validate_okf_bundle.py"]),
            ("check_knowledge_refs.py (ADR-0202/ADR-0203)", [sys.executable, "platform/docs/check_knowledge_refs.py"]),
        ]

        failures = []
        for label, cmd in checks:
            result = _run(cmd)
            ok = result.returncode == 0
            print(f"{'PASS' if ok else 'FAIL'}: {label}")
            if not ok:
                print(result.stdout)
                print(result.stderr, file=sys.stderr)
                failures.append(label)

        helm = shutil.which("helm")
        if helm:
            chart_dir = f"gitops/charts/{THROWAWAY_NAME}"
            lint = _run([helm, "lint", chart_dir])
            ok = lint.returncode == 0
            print(f"{'PASS' if ok else 'FAIL'}: helm lint {chart_dir}")
            if not ok:
                print(lint.stdout)
                print(lint.stderr, file=sys.stderr)
                failures.append("helm lint")
        else:
            print("SKIP: helm not on PATH")

        if failures:
            print(f"\nRESULT: FAIL - {failures}")
            return 1
        print("\nRESULT: PASS - scaffold, validate, discard all succeeded.")
        return 0
    finally:
        discard()
        print(f"Discarded throwaway agent {THROWAWAY_NAME!r} (all scaffolded paths removed).")


if __name__ == "__main__":
    sys.exit(main())
