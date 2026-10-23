#!/usr/bin/env python3
"""ADR-0307 (roadmap WP-41 Part A) acceptance test: "scaffold a throwaway
agent in CI, validate, discard." scaffold_agent.py writes real files into
the real repository tree (see its own module docstring for why - the
onboarding workflow is a reviewed PR, not a scratch directory), so this
test scaffolds a clearly-marked throwaway agent's evaluation skeleton
(the OKF bundle half moved to zuno-demo-agents with its validators in
WP-165; the AIAgent-contract validation and the chart left with the
AIAgent operator in WP-156), checks the generated files compile and parse
and that knowledge references still resolve,
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

# WP-165: the bundle half moved to zuno-demo-agents; only the evaluation
# skeleton is scaffolded here.
THROWAWAY_PATHS = [
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

        generated = sorted(str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "evaluations" / THROWAWAY_NAME).glob("*.py"))
        checks = [
            # The generated Python must at least compile; the scenarios and
            # gate config must parse.
            ("generated Python compiles", [sys.executable, "-m", "py_compile", *generated]),
            ("generated YAML parses", [sys.executable, "-c",
                                       "import sys, yaml; [yaml.safe_load(open(p)) for p in sys.argv[1:]]",
                                       f"evaluations/{THROWAWAY_NAME}/scenarios.yaml",
                                       f"evaluations/{THROWAWAY_NAME}/gate_config.yaml"]),
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
