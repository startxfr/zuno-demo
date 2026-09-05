#!/usr/bin/env python3
"""Shared release-ledger read/write logic (ADR-0549/WP-134).

Extracted from `pin_release.py`'s original `_update_ledger` (behavior
unchanged) so `tag_local_release.py --record-release` can append entries
too, without pulling in `pin_release.py`'s values.yaml-rewriting
machinery - the two scripts now write structurally different but
schema-compatible entries:

- `pin_release.py` (ADR-0115/WP-04, mothballed for the in-cluster flow -
  see its own dated note): historical entries from the one real
  Quay-published release; `digest` may be `null`, no `signed` key.
- `tag_local_release.py --record-release` (ADR-0549/WP-134, current
  mechanism): always sets a real `digest` plus `signed`/`signed_at`,
  since the whole point of this flow is a release that is provably
  immutable AND signed, entirely in-cluster.

Import only - this module has no `__main__` and makes no cluster calls.
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / "platform" / "supply-chain" / "pinned-releases.yaml"

LEDGER_HEADER = (
    "# ADR-0115/ADR-0549 release ledger - append-only. Two writers:\n"
    "#  - pin_release.py (ADR-0115/WP-04, mothballed for day-to-day use -\n"
    "#    see its own dated note): rewrote values.yaml tag fields for the\n"
    "#    one real Quay-published release. Entries may have digest: null\n"
    "#    and no 'signed' key.\n"
    "#  - tag_local_release.py --record-release (ADR-0549/WP-134, current\n"
    "#    mechanism): builds + RHTAS-signs a component in-cluster at\n"
    "#    <component>:<release_tag>, never touches values.yaml/\n"
    "#    targetRevision. Entries always set a real digest and\n"
    "#    signed/signed_at.\n"
    "# This is evidence for ADR-0111/ADR-0549's completion criterion (a\n"
    "# real release proves build -> sign -> immutable-reference\n"
    "# traceability, entirely in-cluster) - never a mechanism consumed by\n"
    "# any deployment, never hand-edit.\n\n"
)


def load_ledger() -> Dict[str, Any]:
    if LEDGER_PATH.exists():
        return yaml.safe_load(LEDGER_PATH.read_text()) or {"releases": []}
    return {"releases": []}


def append_entry(
    release_tag: Any,
    pins: List[Dict[str, Any]],
    skipped: Optional[List[Dict[str, Any]]] = None,
) -> None:
    ledger = load_ledger()
    entry: Dict[str, Any] = {
        "release_tag": release_tag,
        "pinned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pins": pins,
    }
    if skipped:
        entry["skipped"] = skipped
    ledger.setdefault("releases", []).append(entry)
    LEDGER_PATH.write_text(LEDGER_HEADER + yaml.dump(ledger, sort_keys=False, default_flow_style=False))
