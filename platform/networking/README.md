# Platform: networking

Routes, DNS, NetworkPolicies and controlled egress.

## Connectivity Link (Kuadrant)

`ansible/roles/connectivity_link` (chart `gitops/charts/connectivity-link`)
installs the Red Hat Connectivity Link operator - a Kuadrant-based Gateway
API policy layer (rate limiting, auth, DNS/TLS policies for
Gateway-fronted traffic) - plus a minimal, empty `Kuadrant` operand CR
(ADR-0317). Only the operator and that empty CR are installed: no
`Gateway`, `AuthPolicy`, `RateLimitPolicy` or `DNSPolicy` exists in this
repository yet, and this project's own MCP Gateway
(`components/mcp-gateway`) and AI Inference Gateway
(`components/ai-gateway`) remain its actual policy enforcement points
(ADR-0009/ADR-0010/ADR-0011). This is prerequisite installation ahead of a
future Gateway API-fronted inference policy use case, not a replacement
for either gateway today - see `ansible/roles/connectivity_link/README.md`
and `platform/openshift-ai/README.md` for the full disposition.
