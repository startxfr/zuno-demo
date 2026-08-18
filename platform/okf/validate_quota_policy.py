#!/usr/bin/env python3
"""ADR-0511 (roadmap WP-54) quota-policy lint.

Validates policies/quotas/quota-policy.yaml - the third policy file
beside tools/knowledge - and every task frontmatter's `zuno.quota_class`
reference into it. Static repository check, blocking in the lint chain
(same posture as validate_okf_bundle.py). Amounts are never validated
for "reasonableness" - that is a review judgment; this lint guards
structure: classes complete, windows parseable, fail modes explicit,
precedence orders well-formed, task references resolvable.

Run from the repository root:

    python3 platform/okf/validate_quota_policy.py
"""
from __future__ import annotations

import pathlib
import re
import sys
from typing import List

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "policies" / "quotas" / "quota-policy.yaml"
AGENTS_DIR = REPO_ROOT / "agents"

DIMENSIONS = ("user", "group", "project")
WINDOW_RE = re.compile(r"^[0-9]+(s|m|h|d)$")


def main() -> int:
    findings: List[str] = []
    doc = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")) or {}

    classes = doc.get("classes") or {}
    if "standard" not in classes:
        findings.append("classes must include `standard` (the implicit default every unmarked task runs under)")
    for cls_name, cls in classes.items():
        label = f"classes.{cls_name}"
        if cls.get("fail_mode") not in ("open", "closed"):
            findings.append(f"{label}.fail_mode must be `open` or `closed` (explicit, per ADR-0511)")
        for section, amount_key in (("requests", "limit"), ("tokens", "budget")):
            entries = cls.get(section) or {}
            for dim in DIMENSIONS:
                entry = entries.get(dim)
                if not entry:
                    findings.append(f"{label}.{section}.{dim} missing (all three dimensions are required)")
                    continue
                if not isinstance(entry.get(amount_key), int) or entry[amount_key] <= 0:
                    findings.append(f"{label}.{section}.{dim}.{amount_key} must be a positive integer")
                if not WINDOW_RE.match(str(entry.get("window", ""))):
                    findings.append(f"{label}.{section}.{dim}.window must match ^[0-9]+(s|m|h|d)$, got {entry.get('window')!r}")
            extra = set(entries) - set(DIMENSIONS)
            if extra:
                findings.append(f"{label}.{section} has unknown dimension(s): {', '.join(sorted(extra))}")

    precedence = doc.get("precedence") or {}
    for key, required_dims in (("in_project_context", {"project", "user", "group"}), ("default", {"user", "group"})):
        order = precedence.get(key)
        if not isinstance(order, list) or set(order) != required_dims or len(order) != len(required_dims):
            findings.append(f"precedence.{key} must be a permutation of {sorted(required_dims)}, got {order!r}")

    window = ((doc.get("project_binding") or {}).get("validity_window"))
    if not WINDOW_RE.match(str(window or "")):
        findings.append(f"project_binding.validity_window must match ^[0-9]+(s|m|h|d)$, got {window!r}")

    for task_path in sorted(AGENTS_DIR.glob("*/tasks/*.md")):
        parts = task_path.read_text(encoding="utf-8").split("---", 2)
        if len(parts) < 3:
            continue
        zuno = (yaml.safe_load(parts[1]) or {}).get("zuno") or {}
        cls_ref = zuno.get("quota_class")
        if cls_ref is not None and cls_ref not in classes:
            findings.append(f"{task_path.relative_to(REPO_ROOT)}: zuno.quota_class {cls_ref!r} not declared in quota-policy.yaml")

    print(f"Checked {POLICY_PATH.relative_to(REPO_ROOT)} ({len(classes)} class(es)) and every task's quota_class reference.")
    if findings:
        print(f"\n{len(findings)} quota-policy issue(s):")
        for f in findings:
            print(f"  ✗ {f}")
        print("\nRESULT: FAIL - fix policies/quotas/quota-policy.yaml or the task frontmatter (ADR-0511).")
        return 1
    print("\nRESULT: PASS - quota policy structurally valid; every task reference resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
