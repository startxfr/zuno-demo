# ADR-0589: Serve per-persona OpenClaw assistants via claw-operator behind a token-injecting egress proxy

- **Status:** Superseded in part by [ADR-0590](0590-front-openclaw-with-oauth2-proxy-and-an-egress-firewall-one-claw-operator-per-persona-namespace.md) (2026-11-02, WP-182/WP-183) - the namespaces (created by the openclaw chart, one operator each) and the exposure (oauth2-proxy + password, EgressFirewall) moved; the operator, identity, token injection, tools and fallback stay. Previously: Accepted
- **Target:** v0.13
- **Date:** 2026-11-02
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0571](0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md), [ADR-0574](0574-deploy-unifai-through-argocd-from-a-pinned-olm-catalog.md), [ADR-0586](0586-verify-the-unifai-runtime-images-by-digest-signature-and-attestations-before-deploying-them.md)

## Context

ADR-0587 admits experience clients over the governed chain. The second is a personal assistant: a long-lived
agent per person, with its own memory and skills. OpenClaw is the reference open-source project:

- one gateway process with a web Control UI (and optional messaging channels); configuration in
  `openclaw.json`; custom model providers declared with a `baseUrl`, an `apiKey` and `api: "openai-completions"`;
- **one trust boundary per gateway**: not built for mutually untrusting users; the project's guidance is one
  gateway per user;
- no native OIDC; a *trusted-proxy* mode reads the user from an authenticating proxy (`x-forwarded-user`) with an
  `allowUsers` list;
- the model key is static, while the ai-gateway takes short-lived `zuno` JWTs;
- a public record of malicious community skills (ClawHub) and of exposed instances, see the project's own
  security advisories.

Red Hat's `claw-operator` (`codeready-toolchain/claw-operator`, CRD `Claw`, `claw.sandbox.redhat.com/v1alpha1`,
Apache-2.0) runs one instance per user in its own namespaces, with default-deny NetworkPolicies, an egress
allowlist and a credential proxy that keeps real keys out of the pod. It is alpha, published from a custom
catalog on a `staging` channel without tagged releases, and not supported.

## Decision

**Each demo persona gets one OpenClaw assistant, deployed by claw-operator, whose only model and tool paths are
the ai-gateway and the mcp-gateway, reached through an egress proxy that injects a short-lived token.**

1. **Operator.** claw-operator from its catalog pinned by digest (as ADR-0574 for UnifAI), installed by chart
   `gitops/charts/openclaw` (CatalogSource, Subscription, one `Claw` per persona), Applications
   `gitops/apps/openclaw/`, role `ansible/roles/openclaw`, Day 2 run component `openclaw`. The namespaces it
   creates carry `zuno.io/experience-client: "true"`.
2. **Identity.** One confidential Keycloak client per assistant in the `zuno` realm
   (`openclaw-<persona>`, client-credentials, service-account user carrying the persona's groups); secret from
   Vault through ESO. Metrics show `client="openclaw-<persona>"` and the service-account user.
3. **Token injection.** OpenClaw's provider `zuno` points at the ai-gateway with a placeholder key. An egress
   proxy obtains and refreshes the client-credentials token and sets `Authorization` and the `X-Zuno-Agent`
   header on calls to the ai-gateway and the mcp-gateway. claw-operator's own credential proxy is used if it
   can do this (refreshable credential, in-cluster destinations); otherwise a small first-party sidecar does,
   built and signed in the cluster. The pod never holds a usable token for longer than its lifetime.
4. **Tools.** MCP to `http://mcp-gateway.zuno-ai-run.svc:8080/mcp` through the same proxy; the logical agent
   `openclaw` is entitled per group. **ClawHub and every community skill are disabled.**
5. **Exposure.** The web Control UI only, behind oauth2-proxy (Keycloak `zuno`), OpenClaw in trusted-proxy mode
   with `allowUsers` set to the persona. No messaging channel. Egress limited to the ai-gateway, the
   mcp-gateway and Keycloak; no internet.
6. **Fallback.** If claw-operator cannot express decisions 3 to 5, the same design is deployed with the
   `openclaw-kube` Helm chart, one release per persona; the choice is recorded in WP-182.

## Alternatives considered

- **One shared instance from a Helm chart:** simpler, but contradicts OpenClaw's own trust model and loses the
  per-user story. Rejected.
- **A community operator (`openclaw-rocks/openclaw-operator`):** more packaged, not Red Hat, provenance to audit
  in an ecosystem with a supply-chain record. Rejected.
- **Token exchange on behalf of the real user:** the assistant runs without a browser session, so the user's
  token is absent when it works in the background. Rejected for now.
- **A long-lived token in a Secret:** trivial, a bad practice shown in a public demo. Rejected.
- **Kata sandboxed containers and OpenShell policy around tool execution:** the Red Hat layered-sandbox story,
  but a cluster infrastructure change (operator, nodes). Deferred; recorded as a limit.
- **A messaging channel (Slack, Telegram):** the most striking demo, but internet egress and bot secrets. Deferred.

## Consequences

- The assistant's identity is a service account per persona, not the person: quotas and metrics are those of
  `openclaw-<persona>`, shared across the person's sessions in OpenClaw but not with their UnifAI and Open WebUI
  usage. The shared-quota demonstration of ADR-0587 decision 5 therefore uses the same identity on purpose
  (WP-184 sets the persona's groups so the ceilings apply).
- The operator is alpha: an upgrade is a deliberate catalog pin change, never a channel follow.

## Security considerations

OpenClaw executes tools and keeps memory; prompt injection and memory poisoning are inherent. The design bounds
the blast radius: no internet egress, no community skills, no long-lived credential, tools filtered by the
mcp-gateway per group, models filtered by the ai-gateway per classification, one namespace per persona. It does
not prevent a poisoned assistant from misusing the tools its persona is entitled to; the personas are demo
accounts with demo data only.

## Operational considerations

A 401 from the ai-gateway for a request that bypasses the proxy, and an HTTP request to the internet that fails
from the assistant's pod, are the two checks that the bounds hold (WP-183).
