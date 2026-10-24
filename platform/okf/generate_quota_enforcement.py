#!/usr/bin/env python3
"""ADR-0511 (roadmap WP-54 Part B) quota enforcement generator.

Translates policies/quotas/quota-policy.yaml of the admitted agents
release (ADR-0580; read through platform/okf/release_cache.py since
WP-165) - the single source of
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

  3. gitops/charts/connectivity-link/templates/quota-tokenratelimitpolicies.yaml
     (WP-157 step 5, ADR-0570 clause 2 as amended 2026-10-24, decisions
     D1-D5) The same token budgets as ONE Kuadrant `TokenRateLimitPolicy`
     (kuadrant.io/v1alpha1) attached to the MaaS Gateway, so a budget spans
     every model behind it (a MaaSSubscription is per model and
     single-select, inventory finding 5). Stacked ceilings (D2): each
     enforced dimension is its own limit and the first exhausted one denies;
     the project-then-user fallback of ADR-0511 clause 2 is not expressible
     in Limitador and is not attempted. Counters read the headers the
     ai-gateway attests on its MaaS calls (D5) and every limit applies only
     when the caller is the ai-gateway's own ServiceAccount, so a direct
     MaaS client cannot forge them. Only `standard` user/group are rendered
     by default (D3+D4); the project dimension and the non-standard classes
     are generated behind their own default-false values. The whole file is
     guarded by `.Values.quotaEnforcement.tokenRateLimits.enabled` (default
     false); the target Gateway is a value.

  4. components/ai-gateway/app/quota_fail_modes.yaml
     (WP-157 decision D6) class -> fail_mode, the only part of the policy
     the gateway still needs once the budgets move to Kuadrant (ADR-0570
     clause 7: the direct-Service sibling only for `open` classes).

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

    python3 platform/okf/generate_quota_enforcement.py           # regenerate every file
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
# The corp quota policy, relative to the admitted agents release: it left this
# tree with agents/ at WP-165 and is read from the release pinned in
# platform/okf/agents.lock (platform/okf/release_cache.py, or --release-dir).
POLICY_REL = pathlib.Path("policies") / "quotas" / "quota-policy.yaml"
RLP_PATH = REPO_ROOT / "gitops" / "charts" / "connectivity-link" / "templates" / "quota-ratelimitpolicies.yaml"
BUDGETS_PATH = REPO_ROOT / "components" / "ai-gateway" / "app" / "quota_budgets.yaml"
TRLP_PATH = REPO_ROOT / "gitops" / "charts" / "connectivity-link" / "templates" / "quota-tokenratelimitpolicies.yaml"
FAIL_MODES_PATH = REPO_ROOT / "components" / "ai-gateway" / "app" / "quota_fail_modes.yaml"
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

# WP-157 decision D5: the headers the ai-gateway attests on every MaaS call
# when it presents its own ServiceAccount (MAAS_GATEWAY_IDENTITY). The names
# are owned by components/ai-gateway/app/maas_adapter.py (ATTESTED_HEADERS);
# its test suite reads the generated TokenRateLimitPolicy and fails if the
# two sets drift. Lower-case: Envoy lower-cases header names, and CEL map
# keys are case-sensitive.
ATTESTED_USER_HEADER = "x-zuno-user-sub"
ATTESTED_GROUPS_HEADER = "x-zuno-groups"
ATTESTED_HEADERS = (ATTESTED_USER_HEADER, ATTESTED_GROUPS_HEADER, CLASS_HEADER, PROJECT_HEADER)

# Token counters key on the attested headers, never on auth.identity: the
# caller MaaS authenticates is the gateway's ServiceAccount, the same for
# every user. The group key is the gateway's sorted group set joined with
# '|' (app/quota.py's own group key), so the counter granularity matches the
# ledger it replaces.
TRLP_COUNTER_EXPRESSIONS = {
    "user": f"request.headers['{ATTESTED_USER_HEADER}']",
    "group": f"request.headers['{ATTESTED_GROUPS_HEADER}']",
    "project": f"request.headers['{PROJECT_HEADER}']",
}
TRLP_DIMENSION_HEADER = {
    "user": ATTESTED_USER_HEADER,
    "group": ATTESTED_GROUPS_HEADER,
    "project": PROJECT_HEADER,
}

# The identity property the gateway-identity predicate compares against the
# ai-gateway's ServiceAccount username. In a TokenRateLimitPolicy,
# auth.identity is not the raw TokenReview: it is the filter the MaaS
# AuthPolicy (maas-gateway-auth) publishes - groups, groups_str,
# selected_subscription(_key), subscription_error*, subscription_info and
# userid - and it has no `user` key. userid is apiKeyValidation.username,
# else preferred_username, else sub, else user.username, so for the
# ai-gateway it carries system:serviceaccount:zuno-ai-run:ai-gateway. Read
# live on demo333 2026-10-24 (inventory V1, docs/roadmap/evidence/
# wp-157-inventory.md section 4); every controller-generated limit counts on
# auth.identity.userid too. Guarded with has() in a conditional, because one
# unresolvable expression makes the wasm-shim drop EVERY descriptor of the
# request (see _class_predicate), which on the MaaS Gateway would also drop
# the controller's per-subscription limits merged with this policy.
GATEWAY_IDENTITY_PROPERTY = "auth.identity.userid"

# D3 + D4: what is enforced at MaaS today. Everything else in the policy is
# generated too, but rendered only behind its own default-false value, so the
# live object never carries a limit that nobody sends the input for.
ENFORCED_CLASSES = ("standard",)
ENFORCED_DIMENSIONS = ("user", "group")
FAIL_MODES = ("open", "closed")


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
    # So this renders ONE RateLimitPolicy PER quotaEnforcement.routes entry
    # (ADR-0555/WP-142 generalized this from Tekos-only to every
    # stresstest-covered agent - each agent needs its own targetRef, so it
    # needs its own CR), whose `limits` map holds every class's
    # per-dimension entries together; each entry already carries its own
    # `when` class-selector predicate, which is what actually differentiates
    # standard vs intensive (vs the new stresstest class) at request time.
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
        f"# GENERATED FILE (ADR-0511/WP-54, ADR-0555/WP-142) - do not edit.",
        f"# Source: policies/quotas/quota-policy.yaml. Regenerate with:",
        f"#   {REGEN_CMD}",
        f"# ONE RateLimitPolicy per quotaEnforcement.routes entry, each holding",
        f"# every quota class's per-dimension entries; request-rate dimension",
        f"# only (token budgets are enforced by AI Gateway - see",
        f"# components/ai-gateway/app/quota_budgets.yaml - and, for the",
        f"# dedicated stresstest class, RHOAI's own MaaS TokenRateLimitPolicy).",
        f"# Kuadrant allows only one policy per targetRef at this level, so",
        f"# per-class limits share one CR per route - each limit entry's own",
        f"# `when` predicate selects the class.",
        f"# Rendered only when .Values.quotaEnforcement.route.enabled is true",
        f"# AND the operator has supplied the agent chat HTTPRoutes this policy",
        f"# targets (see this chart's README, WP-54 section).",
        "{{- range .Values.quotaEnforcement.routes }}",
        "---",
        "apiVersion: kuadrant.io/v1",
        "kind: RateLimitPolicy",
        "metadata:",
        "  name: zuno-quota-{{ .name }}",
        "  namespace: {{ $.Values.quotaEnforcement.routeNamespace }}",
        "  labels:",
        "    app.kubernetes.io/part-of: zuno-quota-enforcement",
        "spec:",
        "  targetRef:",
        "    group: gateway.networking.k8s.io",
        "    kind: HTTPRoute",
        "    name: {{ .name }}",
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


def _gateway_identity_predicate_format() -> str:
    """A printf format (one %s: the ServiceAccount username) for the
    predicate that confines a limit to the ai-gateway's own calls.

    Built as nested conditionals with has() on every path segment, never as
    a bare comparison: on a caller whose identity lacks the property (a
    persona token, an API key) a bare `auth.identity.userid` fails to
    resolve, and the wasm-shim then sends no descriptor at all for the
    request - see _class_predicate for the live evidence of that failure.
    """
    root, _, rest = GATEWAY_IDENTITY_PROPERTY.partition("auth.identity.")
    if root or not rest:
        raise ValueError(f"GATEWAY_IDENTITY_PROPERTY must start with auth.identity.: {GATEWAY_IDENTITY_PROPERTY!r}")
    segments = rest.split(".")
    expr = f"{GATEWAY_IDENTITY_PROPERTY} == '%s'"
    for depth in range(len(segments), 0, -1):
        path = "auth.identity." + ".".join(segments[:depth])
        expr = f"(has({path}) ? {expr} : false)"
    return expr


def _render_trlp(classes: Dict[str, Dict]) -> str:
    """One gateway-level TokenRateLimitPolicy carrying the ADR-0511 token
    budgets (WP-157 step 5, D1-D5). See the module docstring, item 3."""
    lines: List[str] = [
        "{{- if .Values.quotaEnforcement.tokenRateLimits.enabled }}",
        "{{- $trl := .Values.quotaEnforcement.tokenRateLimits }}",
        "{{- if not (and $trl.targetGateway.name $trl.targetGateway.namespace) }}",
        '{{- fail "quotaEnforcement.tokenRateLimits.targetGateway.name and .namespace must be set when tokenRateLimits.enabled is true (the MaaS Gateway of this cluster)" }}',
        "{{- end }}",
        "{{- if not $trl.gatewayIdentity.username }}",
        '{{- fail "quotaEnforcement.tokenRateLimits.gatewayIdentity.username must be set when tokenRateLimits.enabled is true (the ai-gateway ServiceAccount username)" }}',
        "{{- end }}",
        '{{- if not (has $trl.attachment (list "defaults" "overrides")) }}',
        '{{- fail "quotaEnforcement.tokenRateLimits.attachment must be defaults or overrides" }}',
        "{{- end }}",
        "{{- $gatewayIdentity := printf "
        + _yaml_double_quoted(_gateway_identity_predicate_format())
        + " $trl.gatewayIdentity.username }}",
        "# GENERATED FILE (ADR-0511, WP-157 step 5) - do not edit.",
        "# Source: policies/quotas/quota-policy.yaml of the admitted agents release.",
        f"# Regenerate with: {REGEN_CMD}",
        "# ADR-0511's token budgets as ONE TokenRateLimitPolicy on the MaaS",
        "# Gateway (ADR-0570 clause 2 as amended 2026-10-24, WP-157 D1), so a",
        "# budget spans every model behind it. Stacked ceilings (D2): each limit",
        "# below is enforced on its own and the first exhausted one denies; the",
        "# policy file's project-then-user fallback is not expressible in",
        "# Limitador. Counters read the headers the ai-gateway attests (D5) and",
        "# every limit applies only to the ai-gateway's own ServiceAccount, so a",
        "# direct MaaS client cannot forge them; direct clients stay bounded by",
        "# their MaaSSubscription. Rendered: standard user and group (D3+D4).",
        "# The project dimension (enforceProjectDimension) and the intensive and",
        "# stresstest classes (enforceNonStandardClasses) are generated but NOT",
        "# rendered by default: no caller sends a verified project id or a",
        "# non-standard class until ADR-0563 clause 5 is settled, and a live",
        "# limit nobody can reach would read as enforcement that is not there.",
        "# Strategy merge keeps the maas-controller's per-route policies in",
        "# force beside this one (to prove live, inventory V10).",
        "apiVersion: kuadrant.io/v1alpha1",
        "kind: TokenRateLimitPolicy",
        "metadata:",
        "  name: zuno-token-quota",
        "  namespace: {{ $trl.targetGateway.namespace }}",
        "  labels:",
        "    app.kubernetes.io/part-of: zuno-quota-enforcement",
        "spec:",
        "  targetRef:",
        "    group: gateway.networking.k8s.io",
        "    kind: Gateway",
        "    name: {{ $trl.targetGateway.name }}",
        "  {{ $trl.attachment }}:",
        "    strategy: merge",
        "    limits:",
    ]
    for cls_name, cls in sorted(classes.items()):
        for dim in ("user", "group", "project"):
            tok = (cls.get("tokens") or {}).get(dim) or {}
            if not tok:
                continue
            guards = []
            if cls_name not in ENFORCED_CLASSES:
                guards.append("$trl.enforceNonStandardClasses")
            if dim not in ENFORCED_DIMENSIONS:
                guards.append("$trl.enforceProjectDimension")
            presence = f"'{TRLP_DIMENSION_HEADER[dim]}' in request.headers"
            if guards:
                cond = guards[0] if len(guards) == 1 else f"and {' '.join(guards)}"
                lines.append(f"    {{{{- if {cond} }}}}")
            lines += [
                f"      {cls_name}-{dim}:",
                "        rates:",
                f"          - limit: {tok.get('budget')}",
                f"            window: {tok.get('window')}",
                "        counters:",
                f"          - expression: {TRLP_COUNTER_EXPRESSIONS[dim]!r}",
                "        when:",
                "          - predicate: {{ $gatewayIdentity | quote }}",
                f"          - predicate: {_class_predicate(cls_name)!r}",
                f"          - predicate: {presence!r}",
            ]
            if guards:
                lines.append("    {{- end }}")
    lines.append("{{- end }}")
    lines.append("")
    return "\n".join(lines)


def _yaml_double_quoted(text: str) -> str:
    """A Go-template string literal (double-quoted, backslash escapes)."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _render_fail_modes(doc: Dict) -> str:
    modes = {}
    for name, cls in (doc.get("classes") or {}).items():
        mode = (cls or {}).get("fail_mode")
        if mode not in FAIL_MODES:
            raise ValueError(f"class {name!r}: fail_mode {mode!r} is not one of {', '.join(FAIL_MODES)}")
        modes[name] = mode
    header = (
        "# GENERATED FILE (ADR-0511, WP-157 decision D6) - do not edit. Source:\n"
        "# policies/quotas/quota-policy.yaml of the admitted agents release.\n"
        "# class -> fail_mode, read by app/quota_fail_modes.py (ADR-0570 clause 7:\n"
        "# the direct-Service sibling of a via_maas candidate serves only `open`\n"
        "# classes). A class absent here is `closed` (ADR-0511 default).\n"
        f"# Regenerate with: {REGEN_CMD}\n"
    )
    return header + yaml.safe_dump({"classes": modes}, sort_keys=False)


def _check_trlp_counters() -> List[str]:
    """The token counters may only read the attested headers.

    A counter on auth.identity would count the gateway's ServiceAccount,
    one bucket for every user; a counter on any other header would read
    something the gateway does not set, which the shim cannot resolve -
    the silent no-op _check_identity_filter guards for the RLP.
    """
    problems = []
    allowed = {f"request.headers['{h}']" for h in ATTESTED_HEADERS}
    for dim, expression in TRLP_COUNTER_EXPRESSIONS.items():
        if expression not in allowed:
            problems.append(
                f"TokenRateLimitPolicy counter {dim!r} reads {expression!r}, which is not "
                "one of the ai-gateway's attested headers (ATTESTED_HEADERS)"
            )
    return problems


# Both spellings, because CEL accepts both and this repo already needs the
# bracket form in places: `has()` rejects a bracket-index argument, and a
# hyphenated name cannot use dot notation at all (see COUNTER_EXPRESSIONS'
# note above). Matching only `auth.identity.<name>` would let a dimension
# written `auth.identity["model-id"]` contribute NO required property, so the
# lint below would find nothing missing and pass - on exactly the config that
# disables enforcement. A guard against a silent failure must not have a
# silent failure of its own.
_IDENTITY_REF = re.compile(
    r"auth\.identity(?:\.([A-Za-z_][A-Za-z0-9_]*)"
    r"|\[\s*(['\"])([A-Za-z_][A-Za-z0-9_.-]*)\2\s*\])"
)


def _required_identity_properties() -> List[str]:
    """The identity properties the generated counters read, in either spelling."""
    names = set()
    for expression in COUNTER_EXPRESSIONS.values():
        for dotted, _quote, bracketed in _IDENTITY_REF.findall(expression):
            names.add(dotted or bracketed)
    return sorted(names)


def _published_identity_properties(block: str) -> set:
    """The property names an identity filter block publishes.

    Keys are taken at the block's own outermost indentation rather than at a
    fixed column, and a quoted key counts the same as a bare one. The previous
    form hardcoded sixteen spaces and refused quotes, so re-indenting the
    template - or quoting a key, which YAML requires for some names - made
    every property read as unpublished or, worse, made a genuinely missing one
    read as published.
    """
    key_re = re.compile(
        r"^([ \t]*)(?:(['\"])(?P<quoted>[A-Za-z_][A-Za-z0-9_.-]*)\2"
        r"|(?P<bare>[A-Za-z_][A-Za-z0-9_.-]*))\s*:",
        re.M,
    )
    hits = [
        (len(m.group(1)), m.group("quoted") or m.group("bare"))
        for m in key_re.finditer(block)
    ]
    if not hits:
        return set()
    outermost = min(indent for indent, _ in hits)
    return {name for indent, name in hits if indent == outermost}


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


def _self_test_identity_lint() -> List[str]:
    """Proves the identity lint can still fail, before trusting it to pass.

    `_check_identity_filter` guards a failure that is invisible in the
    cluster, so a version of it that always returns [] would look exactly
    like a clean repo - and that is not hypothetical: reading only
    `auth.identity.<name>` made it blind to the bracket spelling, and keying
    published properties off a hardcoded sixteen-space indent made it blind
    to a reformatted or quoted key. Either blindness turns this lint into a
    rubber stamp.

    So the mechanism is exercised against a dimension that must fail, on
    every run rather than in a test file nobody executes. Same reasoning as
    the wrong-path counter-test documented in the postgresql role: a check
    that reports the same thing either way is not reading anything.
    """
    problems: List[str] = []
    saved = dict(COUNTER_EXPRESSIONS)
    try:
        COUNTER_EXPRESSIONS["__selftest__"] = 'auth.identity["__never_published__"]'
        if "__never_published__" not in _required_identity_properties():
            problems.append(
                "identity lint self-test: a bracket-spelled auth.identity reference "
                "contributes no required property, so such a dimension could never "
                "be reported as unpublished"
            )
        elif not _check_identity_filter():
            problems.append(
                "identity lint self-test: an unpublished identity property was not "
                "reported - the lint cannot fail and therefore proves nothing"
            )
    finally:
        COUNTER_EXPRESSIONS.clear()
        COUNTER_EXPRESSIONS.update(saved)

    if _published_identity_properties(
        '        "quoted_key":\n          expression: auth.identity.sub\n'
    ) != {"quoted_key"}:
        problems.append(
            "identity lint self-test: a quoted property key is not recognised as "
            "published, so the lint would report a published property as missing"
        )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-0511 quota enforcement generator")
    parser.add_argument("--check", action="store_true",
                        help="verify committed outputs match regeneration; never writes")
    parser.add_argument("--release-dir", type=pathlib.Path,
                        help="an already extracted (and verified) agents release instead of the lock")
    args = parser.parse_args()

    release = args.release_dir
    if release is None:
        sys.path.insert(0, str(REPO_ROOT / "platform" / "okf"))
        import release_cache  # noqa: E402
        try:
            release = release_cache.release_dir()
        except release_cache.ReleaseUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    doc = yaml.safe_load((release / POLICY_REL).read_text(encoding="utf-8")) or {}
    try:
        expected = {
            RLP_PATH: _render_rlp(doc.get("classes") or {}),
            BUDGETS_PATH: _render_budgets(doc),
            TRLP_PATH: _render_trlp(doc.get("classes") or {}),
            FAIL_MODES_PATH: _render_fail_modes(doc),
        }
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Runs in both modes: a regeneration that leaves enforcement silently
    # inert is not a success, so this is reported even when writing.
    failures: List[str] = _self_test_identity_lint() + _check_identity_filter() + _check_trlp_counters()
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
