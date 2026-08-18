# connectivity-link chart

Deploys the Red Hat Connectivity Link operator (`-d0` Application) and
the `Kuadrant` operand (`-d1`) - see `ansible/roles/connectivity_link/`
for the lifecycle and the values.yaml header for the operator/project/
kuadrant blocks. This README documents only what is not obvious from
those: the WP-54 quota-enforcement surface.

## Quota enforcement (ADR-0511, WP-54)

`templates/quota-ratelimitpolicies.yaml` is a **generated file** — a
single Kuadrant `RateLimitPolicy` (named `zuno-quota`) carrying every
quota class's request-per-window limits for the user/group/project
identity dimensions, declared in `policies/quotas/quota-policy.yaml`.
**One CR, not one per class**: Kuadrant allows only one policy of a
given kind per `targetRef` at the same level — two separate
`RateLimitPolicy` CRs both targeting the same `HTTPRoute` do not merge,
the second silently "overrides" the first (`status.conditions[Enforced]
= False, reason: Overridden` — hit live on this cluster, 2026-08-18,
fixed by merging all classes into one CR's `limits` map, where each
entry's own `when` predicate is what actually selects the class).
Regenerate with `python3 platform/okf/generate_quota_enforcement.py`;
drift fails the lint chain. Token budgets are deliberately NOT here —
AI Gateway enforces them (`components/ai-gateway/app/quota.py`),
because only the inference layer can meter tokens (ADR-0029).

**Placement decision (WP-54, recorded 2026-08-18):** these policies live
in this chart because it owns the Kuadrant plane, and the supported
enforcement flow is policy-CR → Kuadrant operator → compiled Limitador
config — the exact flow the OpenShift AI MaaS token limits already use
on this cluster (visible as compiled descriptors in the `Limitador`
operand's `spec.limits`; that CR is operator-owned and must never be
co-edited by hand or by this chart). A BFF-side direct Limitador
consult was rejected: it would move declared policy into per-agent Go
code and bypass the compilation flow the platform already trusts.

**Why a Gateway is required at all:** confirmed directly against the
installed CRD (`oc get crd ratelimitpolicies.kuadrant.io -o json` →
`x-kubernetes-validations`), not assumed — `targetRef.group` must be
`gateway.networking.k8s.io` and `targetRef.kind` must be one of
`HTTPRoute`/`GRPCRoute`/`Gateway`. A plain OpenShift `Route`
(`route.openshift.io/v1`), which is how every agent's real traffic is
served today, can never be a target. There is no way to attach
Kuadrant enforcement to a Route.

**Live demo state (WP-54, 2026-08-18):** `templates/quota-demo-gateway.yaml`
renders a dedicated demo path for Tekos, scoped to avoid touching real
traffic at all:
- `Gateway` `zuno-agent-gateway` (namespace `openshift-ingress`, class
  `istio` — Sail/Istio already backs `GatewayClass istio` on this
  cluster, confirmed live) reuses `router-certs-default`, the OpenShift
  Ingress Router's own wildcard cert (`CN=*.apps.<cluster-domain>`,
  confirmed via `openssl x509`) — same namespace as the Gateway, so no
  `ReferenceGrant` and no new cert-manager `Certificate` to provision.
  Neither pre-existing live Gateway (`data-science-gateway`,
  `maas-default-gateway`) was reusable: the former's `allowedRoutes`
  excludes `zuno-ai-run` and is ODH-operator-owned; the latter already
  carries a conflicting deny-by-default `AuthPolicy`/`TokenRateLimitPolicy`
  for MaaS.
- `HTTPRoute` `tekos-quota-demo` (namespace `zuno-ai-run`) on a
  **dedicated hostname**, `tekos-quota-demo.apps.<cluster-domain>` —
  deliberately not the real `tekos.apps.<cluster-domain>` Route's
  hostname, so the two ingress paths never contend for the same DNS
  name and the live Route/Service are never at risk. Backend:
  `tekos-frontend:8080`, the same Service the real Route already fronts.
- `AuthPolicy` `tekos-quota-demo-jwt` establishes JWT identity from the
  same Keycloak `zuno` realm issuer the frontend/BFF charts already
  use, so `auth.identity.sub`/`auth.identity.groups` resolve for the
  RateLimitPolicies.

**Rollback:** set `quotaEnforcement.enabled: false` and push — ArgoCD's
`selfHeal` removes all of it. Nothing outside this chart references any
object rendered here.

**Verification:** a demo persona's requests to
`https://tekos-quota-demo.apps.<cluster-domain>/` should be rate-limited
with an explicit `429` after the `standard` class's per-user limit (60
req/5m); `oc get limitador -n kuadrant-system -o yaml` should show the
compiled `zuno-quota-*` descriptors alongside the pre-existing MaaS
ones. (Evidence recorded in `docs/roadmap/work-packages/wp-54-quota-policy-and-kuadrant-translation.md`'s State log once run.)

Identity/key semantics (also in the generated file's header): user =
`auth.identity.sub`; group = the caller's sorted group set joined with
`|` (one counter per distinct combination — a recorded demo
simplification); project = the `x-zuno-project-id` header, counted only
when present and only ever set platform-side from an ADR-0512 verified
binding. Class selection rides `x-zuno-quota-class` (absent =
`standard`).
