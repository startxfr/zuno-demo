# ADR-0588: Serve a general-purpose chat experience with Open WebUI

- **Status:** Implemented (2026-11-02, WP-181: installed on demo333, `make d2 check open-webui` green)
- **Target:** v0.13
- **Date:** 2026-11-02
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0562](0562-authenticate-unifai-against-the-zuno-keycloak-realm.md), [ADR-0568](0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0571](0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md), [ADR-0586](0586-verify-the-unifai-runtime-images-by-digest-signature-and-attestations-before-deploying-them.md)

## Context

ADR-0587 admits experience clients over the governed chain. The first is a general-purpose chat for any
employee: pick a model, chat, call a tool, no agent. Open WebUI is the most used open-source UI of that kind:

- official Helm chart (`open-webui/open-webui`, helm.openwebui.com); no operator; no Red Hat support;
- OIDC login with a documented Keycloak path (`OPENID_PROVIDER_URL`, `ENABLE_OAUTH_SIGNUP`,
  `ENABLE_OAUTH_ROLE_MANAGEMENT` with a roles claim);
- OpenAI-compatible connections; native MCP over streamable HTTP since v0.6.31 (`WEBUI_SECRET_KEY` required);
- its own RAG and document upload;
- licence: BSD-3 up to v0.6.5; from v0.6.6 the "Open WebUI" branding must not be removed without permission;
- OpenShift: no documented `restricted` SCC profile for the main chart; the pod security context must be left
  to the SCC (no fixed UID or fsGroup).

What is not known yet and decides the wiring: whether the pinned version can forward the signed-in user's OAuth
access token on an OpenAI connection (and refresh it), and whether an MCP connection can carry fixed headers
(`X-Zuno-Agent`, `X-Zuno-Task`) next to the user's token.

## Decision

**Open WebUI is deployed as the general-purpose chat experience under ADR-0587's contract.**

1. **Packaging.** Chart `gitops/charts/open-webui` wraps the official chart at a pinned version, image by
   digest; ArgoCD Applications `gitops/apps/open-webui/`; role `ansible/roles/open_webui`; Day 2 run component
   `open-webui`. Namespace `zuno-openwebui` (label `zuno.io/experience-client: "true"`, default-deny, outside the
   mesh). Pod security context left to the `restricted` SCC; persistent volume on the cluster's resolved
   StorageClass; `WEBUI_SECRET_KEY` and the OIDC client secret from Vault through ESO.
2. **Login.** Keycloak client `open-webui` in the `zuno` realm (confidential, standard flow, groups in the ID
   and access tokens). First login creates the account; roles come from the groups claim; local sign-up and
   password login are off.
3. **Models.** One OpenAI connection to `http://ai-gateway.zuno-ai-run.svc:8080/v1`, authenticated with **the
   signed-in user's access token**. If the pinned version cannot forward it, a small header relay in the same
   namespace does it (session token in, bearer out). **A shared key is never configured**: it would hide the
   user from quotas, guardrails and metrics. The model list is the ai-gateway's `/v1/models` for that user.
4. **Tools.** One MCP connection to `http://mcp-gateway.zuno-ai-run.svc:8080/mcp`, the user's token plus
   `X-Zuno-Agent: open-webui` and a fixed task; the logical agent `open-webui` is entitled per group like any
   agent, so a user sees only the tools their groups grant. Knowledge is reached through the existing
   knowledge-search tools.
5. **Off.** Open WebUI's RAG, document upload, web search, image generation outside the ai-gateway,
   community functions and pipelines, and direct connections added by users.
6. **Exposure.** One Route with an ACME certificate (cert-manager); the "Open WebUI" branding is kept.

## Alternatives considered

- **Native RAG with the RHOAI embedding model:** familiar drag-a-PDF experience, but a second knowledge store
  outside classification and outside ADR-0568. Rejected.
- **Chat only, no tools:** simplest; the unification would stop at models and guardrails. Rejected.
- **RHOAI Gen AI playground:** Technology Preview, a testing tool. Rejected as an experience.
- **LibreChat or AnythingLLM:** similar features, smaller OpenShift footprint in the field; no reason to prefer
  them for a demo that wants the most recognised UI. Not retained.

## Consequences

- Open WebUI keeps its own user database (accounts, chats) in its volume; identity and authorisation stay
  Keycloak's and the gateways'.
- Upgrades follow the pinned chart; the relay of decision 3, if needed, is first-party code built and signed in
  the cluster like any zuno component.

## Security considerations

The user's token reaches Open WebUI's server and is forwarded to two in-cluster services only; egress is limited
to them and to Keycloak. Admin rights in Open WebUI come from a Keycloak group, not from first-user-is-admin.
With uploads, community functions and user-added connections off, the UI cannot pull code or reach other
endpoints.

## Operational considerations

`zuno_model_tokens{client="open-webui"}` is the proof that it uses the governed chain; an empty series while
users chat means a bypass or a broken connection.
