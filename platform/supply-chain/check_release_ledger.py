#!/usr/bin/env python3
"""ADR-0111/ADR-0549 policy-as-code check: validates the structural
integrity of `pinned-releases.yaml`, the append-only ledger
`tag_local_release.py --record-release` writes at the end of `make d3
release TAG=<tag>` (`ansible/playbooks/day3_release.yml`).

This is the enforcement mechanism for ADR-0111's last remaining
control-matrix gap ("deployable chart image tags are immutable"), now
redefined by ADR-0549: not "no chart's `values.yaml` ever says `latest`"
(permanently false by design for `main` - see ADR-0059), but "when a
named release is claimed, it is provably complete, digest-pinned and
signed, entirely in-cluster."

Deliberately does NOT compare ledger entries against the live chart set
`CHART_FIELD_COMPONENT`/`NOT_LOCALLY_BUILDABLE` describe today - older
entries are historical snapshots of whatever component set existed at
the time (e.g. the `v0.1.0` entry predates `mlops`/`diagram-render`
joining `COMPONENTS`) and must not be judged against a set they were
never meant to cover. It only checks each entry is internally
well-formed: does what it claims to have done.

A ledger with zero entries PASSES (with a note) - a cluster that simply
hasn't cut a release yet is not a compliance failure. This check exists
to make sure a *claimed* release record can never silently rot, not to
force a release to always exist.

No live cluster or registry needed - pure static YAML inspection, same
style as check_no_latest_tags.py and
platform/security/check_workload_hardening.py. Wired into `make d2 check
supply-chain` (`ansible/roles/supply_chain/tasks/check.yml`) - in-cluster
only, no GitHub Actions dependency (ADR-0549).

Run from the repository root:

    python3 platform/supply-chain/check_release_ledger.py
"""
from __future__ import annotations

import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / "platform" / "supply-chain" / "pinned-releases.yaml"

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUIRED_PIN_FIELDS = ("chart_values", "path", "tag")
REQUIRED_SKIP_FIELDS = ("chart_values", "path", "reason")


@dataclass
class Problem:
    release_tag: Any
    detail: str


def _check_pin(release_tag: Any, pin: Dict[str, Any], strict: bool, problems: List[Problem]) -> None:
    for field in REQUIRED_PIN_FIELDS:
        if field not in pin:
            problems.append(Problem(release_tag, f"pin missing required field '{field}': {pin!r}"))
            return
    if strict:
        # Only entries written by tag_local_release.py --record-release
        # (ADR-0549) are held to the digest+signed bar. Older
        # pin_release.py entries (ADR-0115/WP-04, digest optional, no
        # 'signed' key) stay valid history - see release_ledger.py.
        digest = pin.get("digest")
        if not digest or not DIGEST_RE.match(str(digest)):
            problems.append(Problem(release_tag, f"pin {pin['chart_values']}:{pin['path']} has no valid digest"))
        if not pin.get("signed"):
            problems.append(Problem(release_tag, f"pin {pin['chart_values']}:{pin['path']} is not marked signed"))
        if pin.get("tag") != release_tag:
            problems.append(
                Problem(release_tag, f"pin {pin['chart_values']}:{pin['path']} tag {pin.get('tag')!r} != release_tag {release_tag!r}")
            )


def _check_skip(release_tag: Any, skip: Dict[str, Any], problems: List[Problem]) -> None:
    for field in REQUIRED_SKIP_FIELDS:
        if field not in skip:
            problems.append(Problem(release_tag, f"skipped entry missing required field '{field}': {skip!r}"))


def check_release(entry: Dict[str, Any], problems: List[Problem]) -> None:
    release_tag = entry.get("release_tag")
    if not release_tag:
        problems.append(Problem(release_tag, "entry has no 'release_tag'"))
        return
    if not entry.get("pinned_at"):
        problems.append(Problem(release_tag, "entry has no 'pinned_at'"))

    pins = entry.get("pins")
    if not pins:
        problems.append(Problem(release_tag, "entry has no non-empty 'pins' list"))
        return

    # ADR-0549 entries (tag_local_release.py --record-release) always set
    # 'signed' on every pin; ADR-0115 historical entries never do. A
    # release is held to the digest+signed bar only if it looks like the
    # newer format (any pin sets 'signed' at all).
    strict = any("signed" in pin for pin in pins)
    for pin in pins:
        _check_pin(release_tag, pin, strict, problems)
    for skip in entry.get("skipped", []) or []:
        _check_skip(release_tag, skip, problems)


def main() -> int:
    if not LEDGER_PATH.exists():
        print(f"{LEDGER_PATH.relative_to(REPO_ROOT)} does not exist yet - no release has been cut.")
        print("\nRESULT: PASS - nothing to validate (make d3 release TAG=<tag> to cut the first one).")
        return 0

    ledger = yaml.safe_load(LEDGER_PATH.read_text()) or {}
    releases = ledger.get("releases") or []
    if not releases:
        print(f"{LEDGER_PATH.relative_to(REPO_ROOT)} has no recorded releases yet.")
        print("\nRESULT: PASS - nothing to validate (make d3 release TAG=<tag> to cut the first one).")
        return 0

    problems: List[Problem] = []
    for entry in releases:
        check_release(entry, problems)

    print(f"Validated {len(releases)} release ledger entry/entries.")
    if not problems:
        print("\nRESULT: PASS - every recorded release is structurally complete.")
        return 0

    print(f"\n{len(problems)} problem(s) found:")
    for p in problems:
        print(f"  ✗ release {p.release_tag!r}: {p.detail}")
    print("\nRESULT: FAIL - a claimed release record must be complete, digest-pinned and signed (ADR-0549).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
