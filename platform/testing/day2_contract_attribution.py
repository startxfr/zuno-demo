#!/usr/bin/env python3
"""ADR-0058 decision 1 (contract layer), since WP-165 from the admitted release.

The ADR-0504 contract suites (agents/<name>/tests/) moved with the agents
to startxfr/zuno-demo-agents (ADR-0576) and run in that repository's CI.
Their result reaches this platform as the signed
`https://zuno.startx.fr/okf/contract-tests/v1` attestation every released
artifact carries (ADR-0578 clause 3), which admission requires
(admit_okf_bundle.verify). The contract layer of a stresstest therefore
reports, per agent of the release pinned in platform/okf/agents.lock,
whether that release was verified with its attestations - one row per
agent, through platform/okf/release_cache.py (verification happens when a
digest is first extracted; a cached digest was verified then).

Needs no cluster access, so this runs directly from the control node, not
inside any Day 2 Job. Prints one JSON array of Day2Result-shaped dicts to
stdout.

Run from the repository root:

    python3 platform/testing/day2_contract_attribution.py
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import asdict

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from day2_report import Day2Result  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "platform" / "okf"))
import release_cache  # noqa: E402


def run() -> "list[Day2Result]":
    try:
        index = release_cache.read_index(release_cache.release_dir())
    except release_cache.ReleaseUnavailable as exc:
        return [Day2Result("all", "contract", "n/a", "contract", False,
                           f"the admitted agents release could not be verified: {exc}")]
    return [
        Day2Result(agent["name"], "contract", "contract-tests-attestation", "contract", True,
                   f"release {index['release']}: {agent['name']} {agent['version']} carries a verified "
                   f"contract-tests attestation (ADR-0578 clause 3)")
        for agent in index["agents"]
    ]


def main() -> int:
    results = run()
    print(json.dumps([asdict(r) for r in results]))
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
