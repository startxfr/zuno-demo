#!/usr/bin/env python3
"""A workload template of a chart must declare `resources` and a `securityContext` (best-practices audit, lot 2 / option B).

Static scan of gitops/charts/*/templates: every file that renders a Deployment, StatefulSet, DaemonSet, Job or CronJob must
contain the words `resources` and `securityContext` (a helper that renders them counts: the scan is deliberately lax, it
looks for the declaration, not for good values). The workloads that already lacked one when the check was written are
listed in workload-hygiene-baseline.txt, `<chart>/templates/<file> <rule>` per line. The check FAILS on a NEW offender and
on a baseline line that no longer applies (so the list only ever shrinks); it never asks for a change to an existing
workload, because changing a pod spec rolls the pod and needs a live check first.

    python3 platform/gitops/check_workload_hygiene.py            # check
    python3 platform/gitops/check_workload_hygiene.py --write    # rewrite the baseline (only to REMOVE lines)
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import Dict, List, Set, Tuple

REPO = pathlib.Path(__file__).resolve().parents[2]
CHARTS = REPO / "gitops" / "charts"
BASELINE = pathlib.Path(__file__).resolve().parent / "workload-hygiene-baseline.txt"
KIND = re.compile(r"^kind:\s*(Deployment|StatefulSet|DaemonSet|Job|CronJob)\s*$", re.M)
RULES = ("resources", "securityContext")


def offenders(charts: pathlib.Path = CHARTS) -> Set[Tuple[str, str]]:
    """{(chart/templates/file, rule)} for every workload template missing a declaration."""
    out: Set[Tuple[str, str]] = set()
    for path in sorted(charts.glob("*/templates/**/*.yaml")):
        text = path.read_text()
        if not KIND.search(text):
            continue
        rel = path.relative_to(charts).as_posix()
        out.update((rel, rule) for rule in RULES if rule not in text)
    return out


def read_baseline(path: pathlib.Path = BASELINE) -> Set[Tuple[str, str]]:
    entries = set()
    for line in path.read_text().splitlines() if path.exists() else []:
        line = line.strip()
        if line and not line.startswith("#"):
            name, rule = line.rsplit(None, 1)
            entries.add((name, rule))
    return entries


def compare(found: Set[Tuple[str, str]], baseline: Set[Tuple[str, str]]) -> Tuple[List[str], List[str]]:
    """(new offenders, baseline lines that no longer apply), as messages."""
    new = [f"{name} has no `{rule}`: declare it (a helper that renders it is fine), or say in the PR why this workload cannot"
           for name, rule in sorted(found - baseline)]
    stale = [f"{name} {rule} is in the baseline but the file now declares it (or is gone): delete the line from "
             f"platform/gitops/workload-hygiene-baseline.txt" for name, rule in sorted(baseline - found)]
    return new, stale


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="rewrite the baseline from the tree")
    args = ap.parse_args(argv)
    found = offenders()
    if args.write:
        lines = ["# Workload templates that lacked `resources` or a `securityContext` when platform/gitops/check_workload_hygiene.py",
                 "# was written (best-practices audit, lot 2). Delete a line when the workload gets the declaration; never add one."]
        lines += [f"{name} {rule}" for name, rule in sorted(found)]
        BASELINE.write_text("\n".join(lines) + "\n")
        print(f"wrote {len(found)} baseline line(s) to {BASELINE.relative_to(REPO)}")
        return 0
    new, stale = compare(found, read_baseline())
    for message in new + stale:
        print(f"  ✗ {message}")
    if new or stale:
        print(f"RESULT: FAIL - {len(new)} new, {len(stale)} stale")
        return 1
    print(f"RESULT: PASS - {len(found)} known offender(s) in the baseline, none new")
    return 0


if __name__ == "__main__":
    sys.exit(main())
