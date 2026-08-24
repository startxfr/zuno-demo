# ADR-0511: Define OKF quota policy enforced via Kuadrant

- **Status:** Partially implemented - Authorino Service CA trust fix merged and live-verified 2026-08-24 (WP-071); the ext_authz transport path through `zuno-agent-gateway` now works end to end (`401`, not `500`, zero `CERTIFICATE_VERIFY_FAILED`, Authorino's own log shows the request arriving). The remaining step is the actual 429-exceedance acceptance run with a real token (not blocked by any defect any more) — see the 2026-08-24 note below.
- **Target:** v0.5 (retargeted to v0.5 on 2026-08-24, superseding this same-day morning's move to v0.3 — grouped with ADR-0201/WP-27 under a dedicated "make MaaS live and used by agents" milestone rather than the generic v0.3 catch-all; at the time of this move, believed blocked on an upstream Kuadrant wasm-shim defect with no repo-side path to resolution — corrected later the same day by WP-071, see the 2026-08-24 implementation note. Originally OKF v0.1; moved out of that milestone alongside ADR-0512, its one hard dependent. Grouping stays valid regardless of the corrected root cause.)
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Implementation note (2026-08-24) — root cause corrected: an Authorino/Envoy TLS trust mismatch, not a wasm-shim binary defect (WP-071)

The 2026-08-21 note's conclusion below - "isolates the defect to the Kuadrant wasm-shim binary itself... not resolvable from this repository's chart/policy layer" - is **superseded and incorrect**. The raw-gRPC comparison in that note correctly proved Authorino itself is healthy (clean ALLOW/DENY via direct gRPC), but never tested the actual TLS identity Envoy validates for the `kuadrant-auth-service` cluster. A 2026-08-24 live diagnostic (see ADR-0201's 2026-08-24 part 5 note and `docs/roadmap/work-packages/wp-071-authorino-service-ca-trust-alignment.md` for the full trace) found that cluster's `trusted_ca` is OpenShift's `service-ca.crt`, while Authorino's listener certificate was issued by `vault-issuer-istio`. Envoy failed the TLS handshake with `CERTIFICATE_VERIFY_FAILED` before dispatching any gRPC `Check` call - the wasm-shim's "gRPC status code is not OK, ~1.3ms" symptom (too fast for a real evaluation, no Authorino log entry) is exactly the signature of a transport-level TLS rejection, not a request ever reaching Authorino's application logic. There is no defect in `kuadrant-operator-wasm` itself.

A second, distinct bug compounded this on `zuno-agent-gateway` specifically: Kuadrant's own generated `EnvoyFilter` never adds TLS to the `kuadrant-auth-service` cluster it creates, for any gateway - confirmed byte-identical to `maas-default-gateway`'s. `maas-default-gateway` only worked once its cert was fixed because RHOAI's `odh-model-controller` separately owns a second `EnvoyFilter` (`maas-default-gateway-authn-ssl`) that independently `ADD`s a TLS-wrapped version of the cluster at `priority: -1` - a piece of plumbing specific to RHOAI-managed gateways that `zuno-agent-gateway` never had. Fixed by `templates/quota-demo-gateway-authn-ssl.yaml`, a new `EnvoyFilter` mirroring RHOAI's exact pattern (not a hand-edit of Kuadrant's own generated filter).

**Fix (WP-071), both parts:** (1) Authorino's listener now serves an OpenShift service-serving certificate via a Service annotation patched by Ansible (`ansible/roles/connectivity_link/tasks/install.yml`), since both `maas-default-gateway` and `zuno-agent-gateway` share the same Authorino instance and the same trust requirement; (2) a new, hand-authored `EnvoyFilter` gives `zuno-agent-gateway` the TLS-wrapped ext_authz cluster it was otherwise missing. Verified live 2026-08-24 on `zuno-agent-gateway`: repeated `401` responses, zero `CERTIFICATE_VERIFY_FAILED`, `cx_connect_fail` delta `0`, Authorino's own log shows the request arriving (`oidc: malformed jwt` for the deliberately invalid test token — a real Authorino evaluation, not a transport failure).

The generated `RateLimitPolicy` design, the six previously-fixed CEL/`Overridden`/ingress/ownership/Limitador bugs, and the compiled Limitador descriptor flow are all unaffected by this correction. The 429-exceedance demo is now pending a normal acceptance run (real token, repeated requests past the `standard` class's limit), not blocked by any defect - "not fixable from this repo" is retracted. Identity propagation and RHOAI/RHCL 1.4 rate-limit identity behavior should still be validated separately, as already planned.

## Implementation note (2026-08-21)

> **Superseded by the 2026-08-24 note above:** the "Kuadrant wasm-shim binary" defect this note concludes with was a misdiagnosis - see above for the corrected root cause (an Authorino/Envoy TLS trust mismatch, plus a second missing-TLS gap specific to this gateway) and the fix (WP-071). Left intact below as an accurate record of the raw-gRPC-vs-wasm-shim comparison, which remains valid evidence that Authorino itself was always healthy.

With every previously-found bug fixed and the RateLimitPolicy/AuthPolicy
both `Enforced: True` live, the 429 demo still failed: every authenticated
request to the demo route returned `500`, not the expected pass-then-429
sequence. Root-caused via direct instrumentation (Envoy trace logging,
`pilot-agent request POST /logging`) and a reflection-driven raw gRPC
client (Python + `grpcio`, built from a throwaway pod against the
mirrored `ubi9-python-311` image, since no `grpcurl`/`openssl` was
available in-cluster):

- Envoy's wasm-shim (`kuadrant-wasm-shim`) dispatches the ext_authz
  `Check` call to Authorino's gRPC service (port 50051) and gets back
  gRPC status **14 (`UNAVAILABLE`) in ~1.3ms** for every single request —
  too fast to be a real evaluation, and Authorino logs nothing for any of
  these calls even at `debug` level.
- Calling Authorino's `envoy.service.auth.v3.Authorization/Check` gRPC
  method **directly**, bypassing the wasm-shim entirely (via gRPC
  reflection to build a real `CheckRequest`, since Authorino's server has
  reflection enabled), proves Authorino itself is completely healthy: an
  expired token gets a clean, well-formed denial (`status.code: 16`,
  `X-Ext-Auth-Reason: oidc: token is expired`); a **freshly minted token
  gets a clean `ok_response {}`** — a proper ALLOW. The exact same fresh
  token sent through the real gateway route seconds later still 500s.
- This isolates the defect to the **Kuadrant wasm-shim binary itself**
  (`kuadrant-operator-wasm`, sha256-pinned in the generated `EnvoyFilter`)
  — not Authorino, not our `AuthPolicy`/`RateLimitPolicy` config, not our
  JWT/JWKS/TLS setup, all independently proven healthy. Both the
  `authorino-operator` and `rhcl-operator` CSVs are the same `rhcl-1
  1.4.2` release train, so this isn't cross-component version skew —
  most likely an internal proto-schema or serialization drift between the
  wasm-shim and Authorino builds bundled in this release.
- This is not resolvable from this repository's chart/policy layer — it's
  a defect in a binary Red Hat ships as part of Connectivity Link, the
  same class of finding as ADR-0201's RHOAI 3.5-EA2 `EnvoyFilter`/mTLS
  gap. Recorded here for whoever picks this up next: don't re-derive the
  "everything's healthy but still 500s" investigation from scratch — the
  wasm-shim is the confirmed fault boundary, and a raw-gRPC-vs-wasm-shim
  comparison (as above) is the fastest way to re-confirm it after any
  Connectivity Link version bump.
- **2026-08-23 update:** confirmed this is the *same* fault, not a similar
  one — ADR-0201/WP-27's independent investigation (a genuinely different
  bug, a port-9002 TLS filter-chain mismatch on the Inference Extension
  endpoint-picker) was fixed and, once out of the way, the authenticated
  MaaS request hit this exact wasm-shim symptom (`kuadrant-wasm-shim: gRPC
  status code is not OK`) behind `maas-default-gateway`, not just
  `zuno-agent-gateway`. This defect now blocks two independent features'
  live acceptance, both waiting on the same upstream Connectivity Link fix.

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
