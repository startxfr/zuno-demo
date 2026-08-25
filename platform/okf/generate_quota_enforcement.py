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
     `.Values.quotaEnforcement.route.enabled` (default false), rendered
     only by the Day2 `zuno-connectivity-link-quota-d1` Application once
     the HTTPRoute it targets exists (its backend, tekos-frontend, is a
     Day2 resource - see the chart README's WP-54 section for the
     placement decision and the Day1/Day2 split rationale).
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
import re
import sys
from typing import Dict, List

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "policies" / "quotas" / "quota-policy.yaml"
RLP_PATH = REPO_ROOT / "gitops" / "charts" / "connectivity-link" / "templates" / "quota-ratelimitpolicies.yaml"
BUDGETS_PATH = REPO_ROOT / "components" / "ai-gateway" / "app" / "quota_budgets.yaml"
# Not generated - hand-authored, because it carries the demo route's own
# Gateway/JWKS wiring and the rationale comments for it. But its AuthPolicy
# has to publish exactly the identity properties the generated counters
# below dereference, so _check_identity_filter() below asserts that
# correspondence rather than leaving it to survive on care alone.
AUTHPOLICY_PATH = REPO_ROOT / "gitops" / "charts" / "connectivity-link" / "templates" / "quota-demo-route.yaml"

REGEN_CMD = "python3 platform/okf/generate_quota_enforcement.py"

CLASS_HEADER = "x-zuno-quota-class"
PROJECT_HEADER = "x-zuno-project-id"

COUNTER_EXPRESSIONS = {
    "user": "auth.identity.sub",
    # auth.identity mirrors the raw JWT claims - a JSON array claim like
    # `groups` deserializes as a CEL list, not a string (confirmed by the
    # live has()-bracket rejection above being the same class of "CEL
    # environment is stricter than assumed" issue) - no .split() needed,
    # only .join() to turn the list into one counter key. Separator must be
    # single-quoted: Kuadrant compiles this expression verbatim into a
    # double-quoted descriptors[0]["<expression>"] CEL string on the
    # Limitador side, so a double-quoted "|" here breaks that string and
    # Limitador refuses to load the limits file (confirmed live, 2026-08-19
    # CrashLoopBackOff - "Couldn't parse: .[1].variables").
    "group": "auth.identity.groups.join('|')",
    "project": f"request.headers['{PROJECT_HEADER}']",
}


def _class_predicate(cls_name: str) -> str:
    # CEL's has() macro rejects bracket-index arguments (confirmed live:
    # "invalid argument to has() macro" on has(request.headers['...'])) -
    # hyphenated header names can't use has()'s dot-notation form either,
    # so map-key presence uses CEL's `in` operator instead.
    #
    # Every predicate is wrapped in a conditional rather than guarded with
    # `||` / `&&`. The CEL spec says a logical operator absorbs an error in
    # one operand when the other decides the result, so
    #   !('x' in request.headers) || request.headers['x'] == 'standard'
    # should be plain `true` for a request with no such header. The
    # wasm-shim's evaluator does not absorb it - confirmed live 2026-08-25,
    # one line per header-less request:
    #   kuadrant_wasm_shim: Failed to evaluate message builder:
    #   CelError::Resolve { NoSuchKey("x-zuno-quota-class") }
    #
    # And the blast radius is not just that predicate: a single failed
    # expression fails the whole message builder, so NO descriptor is sent
    # for the request at all and every limit - including ones whose own
    # predicates were fine - goes uncounted. That is what made the standard
    # class (header absent by design: "absent => standard" is the policy
    # file's documented default) return 200 forever while the intensive
    # class, which always carries the header, rate-limited correctly.
    #
    # The conditional operator has to evaluate lazily to mean anything, so
    # it is the safe construct here: the bracket lookup is only reached on
    # the branch where the key is known to exist.
    # The conditional MUST be wrapped in its own outer parentheses.
    # Kuadrant does not evaluate each limit's predicate separately - it
    # concatenates them all with `||` into one expression deciding whether
    # the actionSet applies at all. CEL binds `?:` looser than `||`, so an
    # unparenthesized ternary is destroyed by that concatenation:
    #   A ? B : false || C ? D : true || ...
    # parses as A ? B : ((false || C) ? D : (true || ...)). Confirmed live
    # 2026-08-25 from the shim's own error, which prints both the mangled
    # AST and the concatenated `source` it built. Wrapped, each term is a
    # self-contained boolean and the concatenation is well-formed.
    presence = f"'{CLASS_HEADER}' in request.headers"
    if cls_name == "standard":
        # Absent header => standard, per policies/quotas/quota-policy.yaml.
        return f"(({presence}) ? request.headers['{CLASS_HEADER}'] == 'standard' : true)"
    return f"(({presence}) ? request.headers['{CLASS_HEADER}'] == '{cls_name}' : false)"


def _render_rlp(classes: Dict[str, Dict]) -> str:
    # Kuadrant allows exactly ONE policy of a given kind per targetRef at
    # the same level (Gateway API direct policy attachment) - two
    # RateLimitPolicy CRs both targeting the same HTTPRoute do not merge,
    # the second "overrides" the first (status Enforced=False,
    # reason=Overridden - confirmed live on this cluster, 2026-08-18).
    # So this renders ONE RateLimitPolicy whose `limits` map holds every
    # class's per-dimension entries together; each entry already carries
    # its own `when` class-selector predicate, which is what actually
    # differentiates standard vs intensive at request time.
    lines: List[str] = [
        # quotaEnforcement.route.enabled ALONE, not also kuadrant.enabled:
        # this file is rendered by its own dedicated Day2 Application
        # (zuno-connectivity-link-quota-d1, see
        # gitops/apps/connectivity-link-quota/application-d1.yaml) with no
        # d0/d1 split of its own, so there's no premature-operator-install
        # phase to guard against - and adding a kuadrant.enabled requirement
        # would force that Application to also set kuadrant.enabled: true,
        # which would re-render the Kuadrant operand CR and ServiceMonitors
        # (guarded by kuadrant.enabled alone) and fight
        # zuno-connectivity-link-d1 for ownership of those (ArgoCD
        # SharedResourceWarning, the same class of bug confirmed live
        # 2026-08-18 that the -d0/-d1 kuadrant.enabled guard elsewhere in
        # this chart already exists to prevent).
        "{{- if .Values.quotaEnforcement.route.enabled }}",
        f"# GENERATED FILE (ADR-0511/WP-54) - do not edit. Source:",
        f"# policies/quotas/quota-policy.yaml. Regenerate with:",
        f"#   {REGEN_CMD}",
        f"# ONE RateLimitPolicy for every quota class; request-rate dimension",
        f"# only (token budgets are enforced by AI Gateway - see",
        f"# components/ai-gateway/app/quota_budgets.yaml). Kuadrant allows only",
        f"# one policy per targetRef at this level, so per-class limits share",
        f"# one CR - each limit entry's own `when` predicate selects the class.",
        f"# Rendered only when .Values.quotaEnforcement.route.enabled is true",
        f"# AND the operator has supplied the agent chat HTTPRoute this policy",
        f"# targets (see this chart's README, WP-54 section).",
        "---",
        "apiVersion: kuadrant.io/v1",
        "kind: RateLimitPolicy",
        "metadata:",
        "  name: zuno-quota",
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
    for cls_name, cls in sorted(classes.items()):
        for dim in ("user", "group", "project"):
            req = (cls.get("requests") or {}).get(dim) or {}
            predicates = [_class_predicate(cls_name)]
            if dim == "project":
                predicates.append(f"'{PROJECT_HEADER}' in request.headers")
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


def _required_identity_properties() -> List[str]:
    """The `auth.identity.<name>` suffixes the generated counters read."""
    names = set()
    for expression in COUNTER_EXPRESSIONS.values():
        names.update(re.findall(r"auth\.identity\.([A-Za-z_][A-Za-z0-9_]*)", expression))
    return sorted(names)


def _check_identity_filter() -> List[str]:
    """Guards the one drift that fails silently and completely.

    Kuadrant's wasm-shim resolves each counter expression against the
    ext_authz dynamic metadata Authorino publishes. A property the
    AuthPolicy does not publish makes its expression unresolvable, and an
    unresolvable expression makes the shim skip the rate-limit call
    altogether - every request returns a clean 200, the RateLimitPolicy
    still reports Accepted+Enforced, and the limits are still compiled
    into Limitador. Nothing surfaces an error anywhere (confirmed live
    2026-08-25: 86 requests, zero 429s, zero 5xx, Limitador never dialled;
    the only trace was a wasm-shim CelError::Resolve NoSuchKey("identity")
    line on the gateway proxy itself).

    So this correspondence cannot be left implicit: adding a counter
    dimension whose expression reads a new auth.identity field, without
    also publishing that field, must fail the lint rather than quietly
    disable enforcement.
    """
    if not AUTHPOLICY_PATH.is_file():
        return [f"{AUTHPOLICY_PATH.relative_to(REPO_ROOT)}: missing"]
    text = AUTHPOLICY_PATH.read_text(encoding="utf-8")
    # A Helm template, so it is not parseable as YAML; the properties block
    # is plain literal text though, so match it directly. Comment lines are
    # dropped first - this file documents the failure mode in prose that
    # itself names the properties.
    body = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    match = re.search(r"filters:\s*\n\s*identity:\s*\n\s*json:\s*\n\s*properties:\s*\n(.*)", body, re.S)
    if match is None:
        return [
            f"{AUTHPOLICY_PATH.relative_to(REPO_ROOT)}: AuthPolicy publishes no "
            "response.success.filters.identity block, so every auth.identity.* "
            "counter silently disables rate limiting"
        ]
    published = set(re.findall(r"^\s{16}([A-Za-z_][A-Za-z0-9_]*):", match.group(1), re.M))
    missing = [n for n in _required_identity_properties() if n not in published]
    if missing:
        return [
            f"{AUTHPOLICY_PATH.relative_to(REPO_ROOT)}: identity filter does not "
            f"publish {', '.join(missing)} - counter expression(s) referencing "
            "them will not resolve and rate limiting will silently no-op "
            "(add them under spec.rules.response.success.filters.identity."
            "json.properties, one `<name>: {expression: auth.identity.<name>}` each)"
        ]
    return []


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

    # Runs in both modes: a regeneration that leaves enforcement silently
    # inert is not a success, so this is reported even when writing.
    failures: List[str] = _check_identity_filter()
    written: List[str] = []
    for path, content in expected.items():
        rel = path.relative_to(REPO_ROOT)
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if args.check:
            if current != content:
                # The hint is attached per-failure, not printed for every
                # entry below: _check_identity_filter()'s findings are not
                # regeneration drift and regenerating will not clear them.
                failures.append(
                    f"{rel}: {'missing' if current is None else 'differs from regeneration'}"
                    f" (run: {REGEN_CMD})"
                )
            continue
        if current != content:
            path.write_text(content, encoding="utf-8")
            written.append(str(rel))

    if args.check:
        if failures:
            print(f"{len(failures)} quota-enforcement drift issue(s):")
            for f in failures:
                print(f"  ✗ {f}")
            print("\nRESULT: FAIL - enforcement must match quota-policy.yaml (ADR-0511).")
            return 1
        print("RESULT: PASS - generated quota enforcement matches quota-policy.yaml.")
        return 0

    print(f"Regenerated {len(written)} file(s): {', '.join(written) or '(none - all current)'}")
    if failures:
        for f in failures:
            print(f"  ✗ {f}")
        print("\nRESULT: FAIL - see above (ADR-0511).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
