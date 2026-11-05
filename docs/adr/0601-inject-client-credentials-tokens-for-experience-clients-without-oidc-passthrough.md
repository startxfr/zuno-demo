# ADR-0601: Inject client-credentials tokens for experience clients without OIDC passthrough

- **Status:** Implemented
- **Target:** v0.14
- **Date:** 2026-11-04
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0589](0589-serve-per-persona-openclaw-assistants-via-claw-operator-behind-a-token-injecting-egress-proxy.md), [ADR-0593](0593-key-the-per-user-quota-and-telemetry-by-persona-across-experiences.md), [ADR-0599](0599-serve-a-no-code-workflow-canvas-with-dify-as-an-experience-client.md), [ADR-0600](0600-govern-kubernetes-read-tools-in-the-mcp-gateway-and-admit-kagent-as-a-thin-operations-client.md)

## Context

ADR-0587 requires every model and tool call of an experience client to carry a `zuno` JWT. Open WebUI forwards the
signed-in user's token (ADR-0588). OpenClaw gets a refreshed client-credentials token from claw-operator's own egress
proxy (ADR-0589). Neither path is available to the two clients v0.14 adds:

- **Dify** (ADR-0599): its model providers, MCP tools and external knowledge bases take a **static** API key or static
  headers. Its Community Edition has no OIDC login, so there is no user token to forward.
- **kagent** (ADR-0600): `ModelConfig` takes `apiKeySecret` (a static Secret) or `apiKeyPassthrough` (the bearer of an
  incoming A2A call). `RemoteMCPServer.headersFrom` reads a Secret or ConfigMap. Its UI has no OIDC login.

A Keycloak access token lives minutes. A static Secret holding one expires silently, and one refreshed by a CronJob
depends on how and when each product reads its Secret.

## Decision

**A first-party token proxy, `components/zuno-token-proxy`, runs in the namespace of each experience client that cannot
forward a user token. It adds a fresh client-credentials token to every request it relays to the ai-gateway and the
mcp-gateway.**

1. **Interface.** A plain HTTP reverse proxy with one listener per upstream: `/v1` to the ai-gateway and `/mcp` to the
   mcp-gateway, each with streaming and SSE passthrough. The client points its base URL at the proxy Service. Any
   static key the product insists on is a dummy value, and the proxy drops it.
2. **Token.** `client_credentials` grant against the Keycloak **Route** (never the in-cluster `http` service, whose
   issuer differs). The token is cached and refreshed at 70 % of its lifetime. The client secret comes from Vault
   through ESO.
3. **Headers.** It overwrites `Authorization` and sets fixed headers from configuration: `X-Zuno-Agent` (the experience
   name), `X-Zuno-Task`, and `X-Zuno-Data-Classification` where the client's declaration fixes one. A header the client
   sends with the same name is replaced, never merged.
4. **Failure mode.** No valid token means `503`, never a pass-through without a token. A Keycloak outage is visible as
   proxy errors, not as gateway `401`s.
5. **Identity.** One Keycloak client per instance. Its service account carries a hardcoded `persona` claim, which makes
   the identity a demo persona as in ADR-0593, and the client is added to `PERSONA_CLAIM_CLIENTS`. Quotas, guardrail
   hits and metrics are therefore counted per persona, not per human user. That limit is stated in the demo script.
6. **Reach.** Ingress only from pods of the same namespace. Egress only to the two gateways and the Keycloak Route
   (NetworkPolicy plus the OVN EgressFirewall of ADR-0590).
7. **Supply chain.** Built and signed in-cluster like every zuno component, with its own tests.

## Alternatives considered

- **A CronJob writing a token into the Secret the product reads:** depends on when the product re-reads it (kagent
  reconciles, Dify stores provider keys encrypted in its database). Fragile. Rejected.
- **A long-lived token** (Keycloak offline token or a long access-token lifespan for these clients): no refresh logic,
  but a stolen token stays valid for weeks. Rejected.
- **Reusing claw-operator's proxy:** it is part of an alpha operator, hard-codes internet passthroughs (ADR-0590) and is
  not packaged on its own. Rejected.
- **An Envoy or oauth2-proxy sidecar:** neither performs an upstream client-credentials grant without custom filters.
  Not retained.

## Consequences

- Dify and kagent reach the governed chain with no product patch.
- Per-human attribution is lost behind those two clients. The front doors (oauth2-proxy) still log who signed in.
- One more first-party image to build, sign and roll.

## Security considerations

The client secret never leaves the proxy pod. The product only sees a dummy key. The proxy cannot be used from
outside the namespace, and it can only reach the two gateways and Keycloak, so a compromised Dify or kagent pod gets the
persona's rights and nothing more.

## Operational considerations

`zuno_model_tokens{client="dify"}` and `{client="kagent"}` prove the path. The proxy exposes
`zuno_token_proxy_refresh_total{result}`, and a growing `result="error"` means Keycloak or the client secret is broken.
