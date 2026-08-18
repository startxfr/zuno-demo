#!/usr/bin/env python3
"""ADR-0511 (roadmap WP-54 Part B) quota enforcement generator.

Translates policies/quotas/quota-policy.yaml - the single source of
every usage limit - into the two enforcement surfaces (ADR-0511
clause 3); enforcement config is generated, never hand-authored:

  1. gitops/charts/connectivity-link/templates/quota-ratelimitpolicies.yaml
     One Kuadrant `RateLimitPolicy` (kuadrant.io/v1) per quota class,
     carrying the request-per-window limits for the user/group/project
     dimensions as Limitador counters. Lives in the connectivity-link
     chart because that chart owns the Kuadrant plane (the operator
     compiles policy CRs into the Limitador operand - the same flow the
     MaaS token limits already use in-cluster); guarded by
     `.Values.quotaEnforcement.enabled` (default false) until the
     operator attaches the agent chat path to a gateway HTTPRoute
     (see the chart README's WP-54 section for the placement decision).
     Field shapes verified against the live CRDs via `oc explain`
     (rates: limit+window; counters: expression; when: predicate).

  2. components/ai-gateway/app/quota_budgets.yaml
     Token budgets per class/dimension plus precedence orders and fail
     modes - the slice AI Gateway's budget check (app/quota.py) needs;
     only the inference layer can meter tokens (ADR-0029).

Dimension key expressions (recorded simplifications):
  - user:    auth.identity.sub (validated JWT, ADR-0033)
  - group:   the caller's full sorted business-role group set joined
             with '|' - one counter per distinct group COMBINATION, not
             per group; good enough for the demo's small fixed role
             sets and avoids multi-counter fan-out.
  - project: the x-zuno-project-id request header, counted only when
             present - which is only ever set from an ADR-0512 verified
             binding by the platform's own callers, never trusted from
             end users (the BFF strips inbound copies).
Class selection rides the x-zuno-quota-class header (absent = standard),
set by the platform per the task's zuno.quota_class (WP-55 wiring).

Usage (from the repository root):

    python3 platform/okf/generate_quota_enforcement.py           # regenerate both files
    python3 platform/okf/generate_quota_enforcement.py --check   # CI drift gate
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Dict, List

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "policies" / "quotas" / "quota-policy.yaml"
RLP_PATH = REPO_ROOT / "gitops" / "charts" / "connectivity-link" / "templates" / "quota-ratelimitpolicies.yaml"
BUDGETS_PATH = REPO_ROOT / "components" / "ai-gateway" / "app" / "quota_budgets.yaml"

REGEN_CMD = "python3 platform/okf/generate_quota_enforcement.py"

CLASS_HEADER = "x-zuno-quota-class"
PROJECT_HEADER = "x-zuno-project-id"

COUNTER_EXPRESSIONS = {
    "user": "auth.identity.sub",
    "group": 'auth.identity.groups.split(",").join("|")',
    "project": f"request.headers['{PROJECT_HEADER}']",
}


def _class_predicate(cls_name: str) -> str:
    if cls_name == "standard":
        return (f"!has(request.headers['{CLASS_HEADER}']) || "
                f"request.headers['{CLASS_HEADER}'] == 'standard'")
    return f"request.headers['{CLASS_HEADER}'] == '{cls_name}'"


def _render_rlp(classes: Dict[str, Dict]) -> str:
    lines: List[str] = [
        "{{- if .Values.quotaEnforcement.enabled }}",
        f"# GENERATED FILE (ADR-0511/WP-54) - do not edit. Source:",
        f"# policies/quotas/quota-policy.yaml. Regenerate with:",
        f"#   {REGEN_CMD}",
        f"# One RateLimitPolicy per quota class; request-rate dimension only",
        f"# (token budgets are enforced by AI Gateway - see",
        f"# components/ai-gateway/app/quota_budgets.yaml). Rendered only when",
        f"# .Values.quotaEnforcement.enabled is true AND the operator has",
        f"# supplied the agent chat HTTPRoute this policy targets (see this",
        f"# chart's README, WP-54 section).",
    ]
    for cls_name, cls in sorted(classes.items()):
        lines += [
            "---",
            "apiVersion: kuadrant.io/v1",
            "kind: RateLimitPolicy",
            "metadata:",
            f"  name: zuno-quota-{cls_name}",
            "  namespace: {{ .Values.quotaEnforcement.routeNamespace }}",
            "  labels:",
            "    app.kubernetes.io/part-of: zuno-quota-enforcement",
            "spec:",
            "  targetRef:",
            "    group: gateway.networking.k8s.io",
            "    kind: HTTPRoute",
            "    name: {{ .Values.quotaEnforcement.routeName }}",
            "  limits:",
        ]
        for dim in ("user", "group", "project"):
            req = (cls.get("requests") or {}).get(dim) or {}
            predicates = [_class_predicate(cls_name)]
            if dim == "project":
                predicates.append(f"has(request.headers['{PROJECT_HEADER}'])")
            lines += [
                f"    {cls_name}-{dim}:",
                "      rates:",
                f"        - limit: {req.get('limit')}",
                f"          window: {req.get('window')}",
                "      counters:",
                f"        - expression: {COUNTER_EXPRESSIONS[dim]!r}",
                "      when:",
            ]
            lines += [f"        - predicate: {p!r}" for p in predicates]
    lines.append("{{- end }}")
    lines.append("")
    return "\n".join(lines)


def _render_budgets(doc: Dict) -> str:
    slim = {
        "classes": {
            name: {
                "fail_mode": cls.get("fail_mode"),
                "tokens": cls.get("tokens"),
            }
            for name, cls in (doc.get("classes") or {}).items()
        },
        "precedence": doc.get("precedence"),
        "project_binding": doc.get("project_binding"),
    }
    header = (
        f"# GENERATED FILE (ADR-0511/WP-54) - do not edit. Source:\n"
        f"# policies/quotas/quota-policy.yaml (token-budget slice + precedence\n"
        f"# + fail modes - what app/quota.py needs; request rates are enforced\n"
        f"# by Kuadrant, not here). Regenerate with:\n"
        f"#   {REGEN_CMD}\n"
    )
    return header + yaml.safe_dump(slim, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-0511 quota enforcement generator")
    parser.add_argument("--check", action="store_true",
                        help="verify committed outputs match regeneration; never writes")
    args = parser.parse_args()

    doc = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")) or {}
    expected = {
        RLP_PATH: _render_rlp(doc.get("classes") or {}),
        BUDGETS_PATH: _render_budgets(doc),
    }

    failures: List[str] = []
    written: List[str] = []
    for path, content in expected.items():
        rel = path.relative_to(REPO_ROOT)
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if args.check:
            if current != content:
                failures.append(f"{rel}: {'missing' if current is None else 'differs from regeneration'}")
            continue
        if current != content:
            path.write_text(content, encoding="utf-8")
            written.append(str(rel))

    if args.check:
        if failures:
            print(f"{len(failures)} quota-enforcement drift issue(s):")
            for f in failures:
                print(f"  ✗ {f} (run: {REGEN_CMD})")
            print("\nRESULT: FAIL - enforcement must match quota-policy.yaml (ADR-0511).")
            return 1
        print("RESULT: PASS - generated quota enforcement matches quota-policy.yaml.")
        return 0

    print(f"Regenerated {len(written)} file(s): {', '.join(written) or '(none - all current)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
