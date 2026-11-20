#!/usr/bin/env python3
"""Every Python test file of the repository is run by a CI workflow, or is listed with a reason in the baseline.

A test nobody runs rots silently. A test file counts as wired when a workflow step's `run` script names the file, or one of its
directories, as a path (relative to the repository root or to the step's `working-directory`). A directory named in a step that
also runs `pytest` or `unittest discover` covers every test below it.

Not wired and not in `platform/testing/tests-not-in-ci-baseline.txt` fails. A baseline line that no longer matches an unwired file
fails too: the baseline only shrinks.

    python3 platform/testing/check_tests_wired.py [--list]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import Iterable, List, Optional, Set

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
BASELINE = pathlib.Path(__file__).resolve().parent / "tests-not-in-ci-baseline.txt"
SKIP = {".git", ".claude", "node_modules", "__pycache__", ".venv", "venv"}
TOKEN = re.compile(r"[A-Za-z0-9_./-]+")


def test_files(repo: pathlib.Path = REPO) -> List[str]:
    out = []
    for path in repo.rglob("test_*.py"):
        parts = path.relative_to(repo).parts
        if not SKIP.intersection(parts):
            out.append("/".join(parts))
    return sorted(out)


def steps(workflow: dict) -> Iterable[tuple]:
    """(working directory, run script) of every step that has one."""
    for job in (workflow.get("jobs") or {}).values():
        default = ((job.get("defaults") or {}).get("run") or {}).get("working-directory", "")
        for step in job.get("steps") or []:
            if isinstance(step, dict) and step.get("run"):
                yield step.get("working-directory", default) or "", str(step["run"])


def wired_paths(workflows: pathlib.Path = WORKFLOWS) -> Set[str]:
    """Every file or directory path (repo-relative, no trailing slash) a workflow step names."""
    paths: Set[str] = set()
    for file in sorted(workflows.glob("*.y*ml")):
        document = yaml.safe_load(file.read_text()) or {}
        for wd, script in steps(document):
            for token in TOKEN.findall(script):
                token = token.strip("./") if token.startswith("./") else token
                token = token.rstrip("/")
                if not token or token.startswith("-"):
                    continue
                paths.add(token)
                if wd:
                    paths.add(f"{wd.strip('/')}/{token}")
            if wd:
                paths.add(wd.strip("/"))  # `pytest` alone in a working directory runs everything below it
    return paths


def is_wired(test: str, paths: Set[str]) -> bool:
    parts = test.split("/")
    return any("/".join(parts[:i]) in paths for i in range(1, len(parts) + 1))


def unwired(repo: pathlib.Path = REPO, workflows: pathlib.Path = WORKFLOWS) -> List[str]:
    paths = wired_paths(workflows)
    return [t for t in test_files(repo) if not is_wired(t, paths)]


def load_baseline(path: pathlib.Path = BASELINE) -> Set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="print every test file no workflow runs")
    args = ap.parse_args(argv)
    missing = unwired()
    baseline = load_baseline()
    new = [t for t in missing if t not in baseline]
    stale = sorted(baseline - set(missing))
    if args.list:
        print("\n".join(missing))
    for t in new:
        print(f"FAIL {t}: no CI workflow runs this test file (add it to a workflow, or to the baseline with a reason)", file=sys.stderr)
    for t in stale:
        print(f"FAIL baseline line is wired or gone, remove it: {t}", file=sys.stderr)
    print(f"RESULT: {'FAIL' if new or stale else 'PASS'} - {len(missing) - len(new)} baselined, {len(new)} new, {len(stale)} stale")
    return 1 if new or stale else 0


if __name__ == "__main__":
    sys.exit(main())
