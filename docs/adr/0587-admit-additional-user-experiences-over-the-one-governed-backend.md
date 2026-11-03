# ADR-0587: Admit additional user experiences over the one governed backend

- **Status:** Implemented (2026-11-03, WP-184: the three experiences run on one identity and one governed backend on demo333)
- **Target:** v0.13
- **Date:** 2026-11-02
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0562](0562-authenticate-unifai-against-the-zuno-keycloak-realm.md), [ADR-0567](0567-move-trustyai-guardrails-into-the-ai-gateway.md), [ADR-0570](0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md), [ADR-0571](0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md), [ADR-0582](0582-serve-a-per-agent-entry-and-descriptive-sheet-from-the-admitted-bundle.md), [ADR-0588](0588-serve-a-general-purpose-chat-experience-with-open-webui.md), [ADR-0589](0589-serve-per-persona-openclaw-assistants-via-claw-operator-behind-a-token-injecting-egress-proxy.md)

## Context

The platform has one user-facing experience: UnifAI (ADR-0561), the agent platform, behind one shared UI and
one Route (ADR-0582 clause 1). Behind it sits a governed chain that UnifAI does not own:

- identity from the `zuno` Keycloak realm (ADR-0562);
- the ai-gateway as the model policy router (ADR-0560): classification routing, guardrails (ADR-0567), the
  per-user, per-group and cross-model ceilings of `app/quota.py`, and the `zuno_model_*` metrics labelled by
  `user`, `group` and `agent`;
- MaaS behind it for the served models and the per-subscription budgets (ADR-0570);
- the mcp-gateway for tools, including its standard MCP streamable-HTTP front door `POST /mcp` with the
  five-factor check in agent mode (ADR-0571 path B).

The demo wants to show that this chain, not the UI, is what the platform provides: three very different
experiences on the same models, quotas, guardrails, tools and telemetry. Two candidates are widely asked for
on OpenShift:

- **Open WebUI**, a general-purpose chat UI with OIDC, OpenAI-compatible connections and native MCP. Official
  Helm chart, no operator, no Red Hat support; branding must be kept since v0.6.6 (its licence).
- **OpenClaw**, a personal AI assistant. Red Hat sponsors the OpenClaw Foundation (2026-09) and publishes
  `claw-operator` (alpha, used by the Developer Sandbox, "not part of supported Red Hat products"); OpenClaw
  Enterprise was announced 2026-09-29 without a date.

State found on 2026-11-02 that constrains the choice:

- MaaS rejects user Keycloak tokens (401, WP-157 inventory) and MaaS API keys are not issued; only the
  ai-gateway accepts a `zuno` user JWT.
- Neither the ai-gateway nor the mcp-gateway has an external Route; their NetworkPolicies admit named peers only.
- The RHOAI Gen AI playground (Technology Preview) is a model and MCP testing tool, not an end-user experience.

## Decision

**A user experience other than UnifAI may be deployed when, and only when, it is a presentation layer over the
governed chain. It owns no model access, no policy and no knowledge of its own.**

1. **Admission contract.** An experience client:
   - authenticates its users against the `zuno` realm, with its own Keycloak client;
   - sends every model call to the ai-gateway's OpenAI-compatible API (`/v1`) with a `zuno` JWT; it holds no
     model key, no MaaS token and no provider URL;
   - reaches tools only through the mcp-gateway `/mcp` front door, with a JWT and an `X-Zuno-Agent` naming the
     experience, so the five-factor check applies;
   - runs no guardrails, no RAG store and no document upload of its own; knowledge comes through MCP tools;
   - is not in `TRUSTED_PLATFORM_CLIENTS`: it cannot choose a quota class or a project id;
   - runs in its own namespace labelled `zuno.io/experience-client: "true"`, default-deny, outside the mesh,
     with images pinned by digest (third-party images are pinned, not signed, as in ADR-0586 decision 7).
2. **The ai-gateway names the client.** Its metrics carry a `client` label taken from the token's `azp`,
   bounded to the known experience clients (anything else is `other`), so one dashboard compares the
   experiences per user and per client.
3. **The NetworkPolicies of the ai-gateway and the mcp-gateway admit experience clients by namespace label,**
   not by name, so adding an experience changes no shared file.
4. **UnifAI stays the agent platform.** Agents, OKF bundles, A2A and per-agent entries live there only. The
   other experiences call no agent; they are general chat (ADR-0588) and personal assistants (ADR-0589).
5. **Quotas are shared across experiences.** A user's ceilings are the ai-gateway's, whatever the client, so a
   budget spent in one experience is spent in all of them.

## Correction notes

ADR-0561 ("the per-agent frontend Route becomes one shared UI") and ADR-0582 clause 1 ("ADR-0561's single UI
and single Route stand") stay true for **agent** UIs. Each carries a dated correction note pointing here: the
single-UI rule is about agents, not about every user-facing surface. No clause is retired, so neither record is
superseded.

## Alternatives considered

- **A showcase namespace outside the governance**, the UIs calling MaaS directly with ServiceAccount tokens:
  fast, but shows the opposite of the point (no user identity, no guardrails, no shared quotas) and breaks the
  rule that every model call traverses the ai-gateway. Rejected.
- **Open WebUI only, OpenClaw deferred** until a supported operator exists: lowest risk, but loses the
  personal-assistant experience, the most distinctive of the three. Rejected; the risk is bounded by ADR-0589.
- **The RHOAI Gen AI playground as the second experience:** Technology Preview, built to test models and MCP
  servers, not for end users. Not an experience; may still be shown as the operator's tool.
- **Direct MaaS for the new clients:** the generated `maas-gateway-auth` refuses Keycloak tokens, and a
  ServiceAccount token hides the user. Rejected until MaaS accepts the realm's tokens.

## Consequences

- Two new namespaces and new Keycloak clients (one for Open WebUI, one per OpenClaw persona); the ai-gateway and the mcp-gateway gain a label-based
  ingress peer and the ai-gateway a `client` label (WP-179).
- Open WebUI (WP-180, WP-181) and OpenClaw (WP-182, WP-183) are independent tracks after WP-179; a joint
  demonstration closes them (WP-184).
- Two third-party products without Red Hat support enter the demo; both are pinned and replaceable without
  touching the governed chain.

## Security considerations

An experience client is untrusted with respect to policy: whatever it sends, the ai-gateway decides the route,
the guardrail and the quota from the token, and the mcp-gateway decides the tool from the user's groups. The
client's compromise exposes its own users' sessions, not other users' data or a model key. The label-based
NetworkPolicy peer means a namespace labelled by mistake can reach both gateways; the label is set only by the
`namespaces` chart.

## Operational considerations

Every experience shows up in `zuno_model_*` with its `client`; an experience that sends nothing to the
ai-gateway is visible as an empty series, which is the check that it does not bypass it.
