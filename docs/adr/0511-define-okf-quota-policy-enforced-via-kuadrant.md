# ADR-0511: Define OKF quota policy enforced via Kuadrant

- **Status:** Partially implemented (WP-54 repo work merged 2026-08-18: quota-policy.yaml + schema + lint + matrix column + generated Kuadrant RateLimitPolicies in the connectivity-link chart, values-gated off + AI Gateway token-budget enforcement with tests; remaining: operator attaches the agent chat HTTPRoute + AuthPolicy and enables quotaEnforcement, then the live quota-denial demo)
- **Target:** OKF v0.1
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

The authorization intersection answers *whether* a user may reach a tool,
a knowledge domain or a model — never *how much*. Nothing today limits a
single consultant from saturating Tekos, one business role from crowding
out another, or an engagement from consuming inference far beyond what it
funds; ADR-0029 instruments model usage costs but only observes them, and
ADR-0406 (v0.4) will limit *agent-to-agent* recursion, not human usage.
The platform already ships the enforcement machinery unused for this
purpose: Red Hat Connectivity Link (ADR-0317, `ansible/roles/
connectivity_link/`, `gitops/charts/connectivity-link/`) deploys the
`Kuadrant` operand — Authorino (authorization context) and Limitador
(rate-limit counters) — in `kuadrant-system`, currently serving only as
an OpenShift AI prerequisite. And the repo already has the policy-file
pattern quota needs: `policies/tools/tool-policy.yaml` and
`policies/knowledge/knowledge-policy.yaml` are the canonical,
GitOps-managed, multi-consumer authorization sources (ADR-0011/ADR-0203).

## Decision

1. **A new policy file, `policies/quotas/quota-policy.yaml`, declares all
   usage limits — part of the OKF package** (it moves to `zuno-okf` with
   the other policy files under ADR-0506). It follows the sibling files'
   shape: a documented header stating the enforcement formula, then
   entries declaring limits along three identity dimensions — **user**
   (JWT `sub`), **group** (business-role `groups` claim, ADR-0040) and
   **project** (the ADR-0512 verified project binding) — each as
   requests-per-window and, where the resource is model inference, token
   budget per window. Named **quota classes** (e.g. `standard`,
   `intensive`) bundle limits; an agent task opts into a class via an
   optional `zuno.quota_class` frontmatter key (absent = `standard`).
   Limits are declared in policy, never in component code or chart
   values.

2. **Precedence in project context: project, then user, then group.**
   When a conversation carries a verified project binding (ADR-0512),
   usage draws down the project's quota first; the user's personal quota
   applies once the project's is exhausted (or absent), and the group
   quota is the outermost ceiling. Outside project context the order is
   user, then group. Exhaustion at every applicable level fails the
   request with an explicit quota error — never silent degradation — and
   the precedence order is part of the policy file's documented header,
   not an implementation detail.

3. **Enforcement is generated from the policy file, never hand-authored
   per agent.** A generator in `platform/okf/` (colocated with the
   ADR-0503 matrix generator, same policy-as-code posture) translates
   `quota-policy.yaml` into: (a) **Kuadrant resources** — Limitador
   `RateLimitPolicy` counters keyed on the Authorino-extracted identity
   dimensions (`sub`, `groups`, project id) for request-per-window
   limits on the agent chat path; and (b) **AI Gateway configuration**
   for token budgets, which only the inference layer can meter —
   `components/ai-gateway` already tracks per-request token usage
   (ADR-0029) and gains a budget check against the same policy source.
   Generated resources land in `gitops/` through review like every other
   manifest (ADR-0022); a drift check fails CI when committed output
   differs from regeneration.

4. **Data-plane placement is an implementation-time cluster decision with
   a fixed contract.** Kuadrant policies attach to Gateway API
   resources, while agent traffic enters through OpenShift Routes today;
   WP-54 decides whether the chat path fronts a Connectivity Link
   gateway listener or the request-rate dimension is enforced by the BFF
   consulting Limitador's gRPC/HTTP API directly. Either way the
   contract holds: counters live in Limitador, identity context comes
   from validated tokens (ADR-0033), limits come only from
   `quota-policy.yaml`, and the token-budget dimension is enforced in
   AI Gateway regardless of placement.

5. **Quota joins the stated contract.** The ADR-0503 authorization
   matrix gains a quota column (the effective class and its limits per
   task), so each bundle states how much, beside who/what/for-what.

## Consequences

"How much" becomes declarative, reviewable and versioned with the rest of
the OKF package: a quota change is a policy-file PR, translated by the
generator, applied by GitOps. Authorino/Limitador acquire their first
first-class platform role beyond prerequisite status. AI Gateway becomes
a quota enforcement point for token budgets, which couples it to the
policy file — through its ADR-0508 adaptation hook once that lands.

## Security considerations

Quota is availability protection, not authorization: exceeding a limit
must produce an explicit, audited denial and must never bypass or relax
the ADR-0011/ADR-0036 intersection. Counter keys carry `sub`, group
names and project ids — identifier metadata, no message content — and
follow the existing observability data-handling posture (ADR-0029).
Identity dimensions are extracted only from validated tokens (ADR-0033)
or the verified project binding (ADR-0512), never from client-supplied
headers. A Limitador outage must fail closed for `intensive`-class
operations and may fail open for `standard`-class chat only if the
policy file explicitly says so, per class — the default is fail closed.

## Operational considerations

Limitador counter state is in-memory/Redis-backed per its deployment
mode; WP-54 records the chosen mode and its restart semantics. Quota
denials surface to users with the applicable limit and window, and to
operators as metrics per dimension (user/group/project), joining the
ADR-0029 cost dashboards. The generator's drift check runs in the same
lint job as the ADR-0503 matrix check.

## Acceptance criteria

- `policies/quotas/quota-policy.yaml` exists with the three identity
  dimensions, quota classes, the documented precedence order, and at
  least one real limit per dimension.
- The generator produces Kuadrant resources and AI Gateway budget config
  from it; committed output matches regeneration in CI.
- A demo user exceeding a request limit receives an explicit quota
  error; token-budget exhaustion at AI Gateway is observable in metrics;
  the ADR-0036 intersection is untouched by both.
- The ADR-0503 matrix renders the quota column.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
- [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md)
- [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0317](0317-install-connectivity-link-and-leaderworkerset-operators.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)
- [ADR-0506](0506-extract-okf-content-into-a-standalone-zuno-okf-repository.md)
- [ADR-0512](0512-introduce-project-bound-tasks-with-salesforce-verified-context.md)
