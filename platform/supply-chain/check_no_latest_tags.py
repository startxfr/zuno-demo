#!/usr/bin/env python3
"""ADR-0115 policy-as-code check: "Add CI checks rejecting `latest` for
deployable component images." Walks every `gitops/charts/*/values.yaml`
looking for an image `tag` field set to the literal string "latest" -
Kubernetes' most common non-reproducible-deployment mistake, and exactly
what ADR-0115's Context names ("component Helm values use `tag: latest`.
This makes a deployed environment non-reproducible").

No live cluster or registry needed - pure static YAML inspection, same
style as platform/security/check_workload_hardening.py. Currently a
correctly-failing check against this repository's actual state: 6 charts
still use `tag: latest` as of ADR-0115's landing, because the CI pipeline
that would publish real immutable tags for it to reference
(.github/workflows/build-publish.yml) has never actually run in this
sandbox (no live Quay credentials here) - see .github/README.md and
docs/adr/0051-*.md's Implementation state for the honest reason this
check isn't clean yet, rather than silently loosening the rule to make it
pass.

Run from the repository root:

    python3 platform/supply-chain/check_no_latest_tags.py

Note (2026-09-05, ADR-0549): no longer wired into any gate - removed
from `.github/workflows/lint.yml`, never added to any `make` verb. Its
literal premise ("a chart's tag must never say `latest`") now permanently
contradicts ADR-0059 by design: `main`'s `gitops/apps/*` charts keep
`tag: latest` forever, since that's what the `image.openshift.io/
triggers` auto-redeploy annotation watches. ADR-0111's control-matrix row
this check used to back is now enforced instead by
`check_release_ledger.py` (validates named-release provenance, not
`values.yaml` literals). This script is kept, unchanged, only because it
becomes meaningful again the day ADR-0353's still-unwritten external-
registry cutover is ever adopted (at which point `.repository` really
would move off the in-cluster mirror and `latest` really would become a
live bug again) - see `pin_release.py`'s matching dated note.
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass
from typing import Any, List

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FORBIDDEN_TAG_VALUES = {"latest", ""}


@dataclass
class Finding:
    file: str
    path: str
    value: str


def _walk(node: Any, path: str, findings: List[Finding], file_label: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key == "tag" and isinstance(value, str) and value in FORBIDDEN_TAG_VALUES:
                findings.append(Finding(file_label, child_path, value or "(empty)"))
            else:
                _walk(value, child_path, findings, file_label)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, f"{path}[{i}]", findings, file_label)


def check_values_file(path: pathlib.Path) -> List[Finding]:
    doc = yaml.safe_load(path.read_text()) or {}
    findings: List[Finding] = []
    _walk(doc, "", findings, str(path.relative_to(REPO_ROOT)))
    return findings


def main() -> int:
    values_files = sorted((REPO_ROOT / "gitops" / "charts").glob("*/values.yaml"))
    all_findings: List[Finding] = []
    for path in values_files:
        all_findings.extend(check_values_file(path))

    print(f"Scanned {len(values_files)} chart values.yaml file(s) under gitops/charts/.")
    if not all_findings:
        print("\nRESULT: PASS - no image tag is 'latest' or empty.")
        return 0

    print(f"\n{len(all_findings)} non-immutable image tag(s) found:")
    for f in all_findings:
        print(f"  ✗ {f.file}: {f.path} = {f.value!r}")
    print(
        "\nRESULT: FAIL - replace each with an immutable tag (git SHA or "
        "semver release tag) published by .github/workflows/build-publish.yml "
        "(ADR-0115)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
