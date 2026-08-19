# Platform: networking

Routes, DNS, NetworkPolicies and controlled egress.

## Connectivity Link (Kuadrant)

`ansible/roles/connectivity_link` (chart `gitops/charts/connectivity-link`)
installs the Red Hat Connectivity Link operator - a Kuadrant-based Gateway
API policy layer (rate limiting, auth, DNS/TLS policies for
Gateway-fronted traffic) - plus a `Kuadrant` operand CR (ADR-0317). The
chart now also stands up a real Gateway API `Gateway` (`zuno-agent-gateway`,
`gitops/charts/connectivity-link/templates/quota-demo-gateway.yaml`), one
`HTTPRoute` (`tekos-quota-demo`), and its `AuthPolicy`/`RateLimitPolicy` for
the quota-enforcement demo path (d1 only, gated behind
`quotaEnforcement.enabled`/`kuadrant.enabled`). `openshift-ai`'s own
`maas-default-gateway` (`gitops/charts/openshift-ai/templates/maas-gateway.yaml`)
is a separate Gateway outside this chart's scope. This project's own MCP
Gateway (`components/mcp-gateway`) and AI Inference Gateway
(`components/ai-gateway`) remain the primary policy enforcement points for
everything not yet covered by the two Gateway API gateways above
(ADR-0009/ADR-0010/ADR-0011) - see `ansible/roles/connectivity_link/README.md`
and `platform/openshift-ai/README.md` for the full disposition.
