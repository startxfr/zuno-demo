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
traffic at all, copying the exact ingress shape the two pre-existing
Gateways already use on this cluster (`data-science-gateway`,
`maas-default-gateway`) rather than Gateway API's own defaults:
- `ConfigMap` `zuno-agent-gateway-config` + Gateway
  `infrastructure.parametersRef` request a **`ClusterIP`** Service with
  `service.beta.openshift.io/serving-cert-secret-name` — OpenShift's
  service-serving-cert-signer auto-issues and rotates the listener's
  TLS secret, no cert-manager `Certificate` needed. **First attempt
  skipped this ConfigMap** and let the Gateway default to a
  `LoadBalancer` Service — which silently provisioned a genuinely
  separate AWS ELB with its own hostname, invisible to
  `*.apps.<cluster-domain>` DNS (confirmed live: the demo hostname
  503'd — it was hitting the OpenShift router, which had no `Route`
  for it, while the real traffic went to a different address
  entirely). Caught and fixed before running the actual quota demo.
- `Gateway` `zuno-agent-gateway` (namespace `openshift-ingress`, class
  `istio` — Sail/Istio already backs `GatewayClass istio` on this
  cluster). Neither pre-existing live Gateway was reusable as a
  parent: `data-science-gateway`'s `allowedRoutes` excludes
  `zuno-ai-run` and is ODH-operator-owned; `maas-default-gateway`
  already carries a conflicting deny-by-default
  `AuthPolicy`/`TokenRateLimitPolicy` for MaaS.
- `Route` `zuno-agent-gateway` (namespace `openshift-ingress`,
  `termination: reencrypt`) on the router's own
  `*.apps.<cluster-domain>` wildcard DNS, host
  `tekos-quota-demo.apps.<cluster-domain>` — a **dedicated hostname**,
  deliberately not the real `tekos.apps.<cluster-domain>` Route's, so
  the two ingress paths never contend for the same DNS name and the
  live Route/Service are never at risk.
- `HTTPRoute` `tekos-quota-demo` (namespace `zuno-ai-run`) backing that
  hostname inside the mesh, backend `tekos-frontend:8080` — the same
  Service the real Route already fronts.
- `AuthPolicy` `tekos-quota-demo-jwt` establishes JWT identity using
  `jwksUrl` — the internal Keycloak Service endpoint
  (`http://zuno-service.zuno-auth.svc:8080/realms/zuno/protocol/openid-connect/certs`),
  **not** `issuerUrl` (OIDC discovery against the external Route).
  First attempt used `issuerUrl` and Authorino 500'd every request:
  in-cluster OIDC discovery against the externally-issued Keycloak
  route cert failed with `x509: certificate signed by unknown
  authority` (Authorino doesn't trust that CA) — the same class of
  problem ADR-0347/ADR-0411 solve for other in-cluster consumers, and
  the same split-brain issuer/JWKS default every other Keycloak
  consumer chart in this repo already carries. The internal endpoint
  is plain HTTP, sidestepping TLS trust entirely. Once fixed,
  `auth.identity.sub`/`auth.identity.groups` resolve for the
  RateLimitPolicy.

**Pre-existing platform bug found and fixed (2026-08-18):** even after
the `jwksUrl` fix, every request 500'd with `server: istio-envoy`
logging `kuadrant-wasm-shim: gRPC status code is not OK` — Envoy's
ext_authz call to Authorino's gRPC listener itself, not an AuthConfig
problem. Root cause: `templates/certificate.yaml`'s
`authorino-server-tls` was issued via `vault-issuer` (the
general-purpose cert-manager PKI role), which
`gitops/charts/service-mesh/templates/clusterissuer-istio.yaml`'s own
design comment says is **deliberately** excluded from the mesh's trust
bundle ("isolates the mesh's SPIFFE trust root from general-purpose
TLS certs") — confirmed via `openssl s_client`: TLS handshake
succeeded, but `Verify return code: 21 (unable to verify the first
certificate)`. Since every gRPC ext_authz caller is an Envoy mesh
sidecar, and mesh sidecars trust only the SPIFFE root
(`vault-issuer-istio`, the same root `cert-manager-istio-csr` issues
mesh workload certs from), the fix is `certificate.yaml`'s
`issuerRef.name: vault-issuer-istio` instead. **This affected every
Kuadrant-protected route on the cluster already, not just this demo**
— confirmed by curling the pre-existing, unrelated MaaS endpoint
(`https://maas.apps.<cluster-domain>/v1/models`), which also 500'd
identically before this fix. Authorino's TLS listener was turned on
solely to satisfy a DataScienceCluster readiness precondition
(`authorino.yaml`'s own comment); this JWT AuthPolicy was very
plausibly the first time anything actually exercised it end-to-end.

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
