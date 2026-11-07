#!/usr/bin/env python3
"""ADR-0604 WP-235: the chart pulls exactly the weights platform/world-model/models.lock.yaml pins.

The runtime's init container copies <prefix>/<repo>/<revision>/ from S3 (gitops/charts/world-model/files/fetch_models.py),
so a revision edited in one place and not the other would fetch nothing, or an unreviewed revision. Pure static check:

    python3 platform/world-model/tests/check_pins.py
"""
from __future__ import annotations

import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]


def main() -> int:
    lock = yaml.safe_load((ROOT / "platform/world-model/models.lock.yaml").read_text())
    values = yaml.safe_load((ROOT / "gitops/charts/world-model/values.yaml").read_text())
    pinned = {m["repo"]: m["revision"] for m in lock["models"]}
    chart = values["modelStorage"]["revisions"]
    problems = []
    for repo, revision in pinned.items():
        if chart.get(repo) != revision:
            problems.append(f"{repo}: lock pins {revision}, chart values say {chart.get(repo)}")
    for repo in chart.keys() - pinned.keys():
        problems.append(f"{repo}: the chart fetches it but the lock does not pin it")
    bucket, _, expected_prefix = lock["s3Prefix"].removeprefix("s3://").partition("/")
    if values["modelStorage"]["prefix"] != expected_prefix:
        problems.append(f"S3 prefix: lock says {expected_prefix}, chart says {values['modelStorage']['prefix']}")
    if values["modelStorage"]["bucket"] != bucket:
        problems.append(f"bucket: lock says {bucket}, chart says {values['modelStorage']['bucket']}")
    if problems:
        print("\n".join(f"FAIL {p}" for p in problems))
        return 1
    print(f"OK {len(pinned)} pinned repositories match the chart")
    return 0


if __name__ == "__main__":
    sys.exit(main())
