# ADR-0622: Run Agent Router as an alternative AI gateway

- **Status:** Proposed
- **Target:** v0.17
- **Date:** 2026-11-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0619](0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md) (the frame for alternative AI gateways)

## Context

Agent Router, formerly Envoy AI Gateway, is the third alternative gateway in the owner's order (2026-11-17). It was
renamed without changing its CRDs (`AIGatewayRoute`, `aigateway.envoyproxy.io`, `aigw`).

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | Version 1.2 has provider fallback, a token `QuotaPolicy` keyed by request headers (windows 1 s to 1 d), usage-based rate limiting, and upstream authentication. | theagentrouter.ai `/docs/capabilities/`, `/docs/capabilities/traffic/quota-policy`, read 2026-11-17 |
| F2 | Its MCP gateway does OAuth with an external issuer (Keycloak in the example) and per-tool authorization rules on JWT scopes and claims or CEL. It has OpenTelemetry tracing. | theagentrouter.ai `/docs/capabilities/mcp/`, read 2026-11-17 |
| F3 | It runs on Envoy Gateway, a Gateway API controller of its own, next to OpenShift's Gateway API implementation (Istio) used by Kuadrant and MaaS. | Agent Router architecture page; `gitops/charts/connectivity-link` |

## Decision

**Agent Router is deployed under ADR-0619, once a cluster-infrastructure decision is taken.**

1. **Open: the controller.** Envoy Gateway is cluster-wide infrastructure. Before the work package starts, the owner
   decides whether it can run next to the OpenShift Gateway API controller: its own GatewayClass, its own namespace,
   no change to `openshift-ingress`.
2. **Identity** is the `zuno` JWT, checked by an Envoy Gateway `SecurityPolicy`. A claim is copied to a header so that
   `QuotaPolicy` can count per user.
3. **Its MCP gateway** is shown only as a comparison in the `multi-gateway` 15-minute scenario. The Zuno mcp-gateway
   stays the tools path (ADR-0571).

## Alternatives considered

None yet; to be written when the owner reopens it.

## Consequences

The heaviest of the four on the cluster: one more controller and its CRDs.

## Security considerations

A second Gateway API controller must not take over existing Gateways. It gets its own GatewayClass only.

## Operational considerations

To be written with the work package.

## Work packages

[WP-294](../roadmap/work-packages/wp-294-deploy-agent-router-as-an-alternative-gateway.md) (not started).
