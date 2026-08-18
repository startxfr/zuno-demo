# connectivity-link chart

Deploys the Red Hat Connectivity Link operator (`-d0` Application) and
the `Kuadrant` operand (`-d1`) - see `ansible/roles/connectivity_link/`
for the lifecycle and the values.yaml header for the operator/project/
kuadrant blocks. This README documents only what is not obvious from
those: the WP-54 quota-enforcement surface.

## Quota enforcement (ADR-0511, WP-54)

`templates/quota-ratelimitpolicies.yaml` is a **generated file** — one
Kuadrant `RateLimitPolicy` per quota class declared in
`policies/quotas/quota-policy.yaml`, carrying the request-per-window
limits for the user/group/project identity dimensions. Regenerate with
`python3 platform/okf/generate_quota_enforcement.py`; drift fails the
lint chain. Token budgets are deliberately NOT here — AI Gateway
enforces them (`components/ai-gateway/app/quota.py`), because only the
inference layer can meter tokens (ADR-0029).

**Placement decision (WP-54, recorded 2026-08-18):** these policies live
in this chart because it owns the Kuadrant plane, and the supported
enforcement flow is policy-CR → Kuadrant operator → compiled Limitador
config — the exact flow the OpenShift AI MaaS token limits already use
on this cluster (visible as compiled descriptors in the `Limitador`
operand's `spec.limits`; that CR is operator-owned and must never be
co-edited by hand or by this chart). A BFF-side direct Limitador
consult was rejected: it would move declared policy into per-agent Go
code and bypass the compilation flow the platform already trusts.

**Why disabled by default:** a `RateLimitPolicy` targets a Gateway API
object, and agent chat traffic enters through OpenShift Routes today —
there is no agent HTTPRoute for the policies to attach to yet. Enabling
is an operator step:

1. Attach the agent chat path to a gateway listener (Connectivity Link
   gateway or equivalent) with an `HTTPRoute`, and establish JWT
   identity on that route with a Kuadrant `AuthPolicy` (Keycloak `zuno`
   realm issuer/JWKS) so the `auth.identity.*` counter expressions
   resolve.
2. Set `quotaEnforcement.enabled: true` and
   `quotaEnforcement.routeName/routeNamespace` to that HTTPRoute.
3. Verify: a demo user exceeding the per-user request limit receives an
   explicit 429 from the gateway; `oc get limitador -n kuadrant-system
   -o yaml` shows the compiled `zuno-quota-*` descriptors beside the
   MaaS ones.

Identity/key semantics (also in the generated file's header): user =
`auth.identity.sub`; group = the caller's sorted group set joined with
`|` (one counter per distinct combination — a recorded demo
simplification); project = the `x-zuno-project-id` header, counted only
when present and only ever set platform-side from an ADR-0512 verified
binding. Class selection rides `x-zuno-quota-class` (absent =
`standard`).
