#!/usr/bin/env python3
"""ADR-0572 clause 4 policy-as-code check: UnifAI never installs a Foundation service on a Zuno cluster.

A `UnifaiStack` on a Zuno cluster uses `identity.external` against the Foundation's Keycloak (ADR-0562).
`identity.keycloak` would run a second Keycloak with its own admin user, an unreviewed identity silo, so it is
refused in the two places that can set it:

- `zuno_unifai_values.stack.identity` of every `ansible/clusters/*.yml`;
- the chart `gitops/charts/unifai/templates/` (which must also declare `external:`).

Run from the repository root:
    python3 platform/supply-chain/check_unifai_identity.py [ansible/clusters/<cluster>.yml ...]
"""
from __future__ import annotations

import pathlib
import re
import sys
from typing import List

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CLUSTERS_DIR = REPO_ROOT / "ansible" / "clusters"
CHART_TEMPLATES = REPO_ROOT / "gitops" / "charts" / "unifai" / "templates"
KEYCLOAK_KEY = re.compile(r"^\s*keycloak\s*:", re.M)
EXTERNAL_KEY = re.compile(r"^\s*external\s*:", re.M)


def check_cluster(name: str, doc: dict) -> List[str]:
    """Findings for one cluster's variables."""
    identity = (((doc.get("zuno_unifai_values") or {}).get("stack") or {}).get("identity")) or {}
    if "keycloak" in identity:
        return [f"{name}: zuno_unifai_values.stack.identity.keycloak is set; a Zuno cluster uses identity.external "
                f"(ADR-0572 clause 4)"]
    return []


def check_chart(templates: pathlib.Path) -> List[str]:
    """Findings for the chart's templates."""
    findings: List[str] = []
    stack = templates / "unifaistack.yaml"
    if not stack.is_file() or not EXTERNAL_KEY.search(stack.read_text(encoding="utf-8")):
        findings.append(f"{stack.relative_to(REPO_ROOT)} does not declare identity.external (ADR-0572 clause 4)")
    for path in sorted(templates.glob("*.yaml")):
        if KEYCLOAK_KEY.search(path.read_text(encoding="utf-8")):
            findings.append(f"{path.relative_to(REPO_ROOT)} declares a `keycloak:` key; identity.keycloak is forbidden "
                            f"on Zuno clusters (ADR-0572 clause 4)")
    return findings


def main(argv: List[str]) -> int:
    paths = [REPO_ROOT / a for a in argv] if argv else sorted(CLUSTERS_DIR.glob("*.yml"))
    findings: List[str] = []
    for path in paths:
        findings += check_cluster(path.stem, yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    findings += check_chart(CHART_TEMPLATES)
    print(f"Checked {len(paths)} cluster file(s) and the unifai chart templates.")
    for finding in findings:
        print(f"  ✗ {finding}")
    if findings:
        print("\nRESULT: FAIL - UnifAI must use identity.external on a Zuno cluster (ADR-0572 clause 4).")
        return 1
    print("\nRESULT: PASS - no UnifaiStack declares identity.keycloak.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
