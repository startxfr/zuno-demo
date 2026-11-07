# WP-244: Blender workstation experience client

- **State:** Operator pending
- **ADRs:** [ADR-0610](../../adr/0610-generate-blender-objects-as-bpy-scripts-from-a-local-model-through-the-ai-gateway.md)
- **Depends on:** none
- **Related:** [ADR-0587](../../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md),
  [ADR-0565](../../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md),
  [ADR-0606](../../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)
- **Target:** v0.17
- **Estimated files touched:** ~12: the realm, two charts, one Application manifest, the llm role, the demo333
  variables, the agents release (one experience client), the demonstration script, this brief and the tracker

> Why: ADR-0610 lets a 3D artist generate editable Blender objects from a prompt on the platform's local model,
> under their own identity, with nothing leaving the company. Run ahead of its band by user decision (2026-11-07,
> weekend rush before the 2026-11-09 demonstration): planning constraints are lifted, the freeze window is not.

## Goal

The Blender add-on of `docs/demo/blender-3d.md` signs in with the device flow, sends a prompt through
`https://ai-gateway.apps.<domain>` and gets a `bpy` script from `gpt-oss-20b`, on demo333.

## Steps

1. **Keycloak.** Public client `blender` in `gitops/charts/keycloak/files/realm-zuno.json`: device authorization grant
   only (no standard flow, no password grant, no secret), groups and `maas-gateway-audience` mappers. The
   client-reconcile Job creates it on the next Keycloak sync.
2. **ai-gateway.** `blender` in `experienceClients` (the `client` label). `workstationEntry.enabled` admits the
   zuno-agent-gateway pod in the NetworkPolicy; the llm role passes `zuno_ai_gateway_workstation_entry`.
   `zuno_ai_gateway_classification_client_floors: {blender: C3}` in `ansible/clusters/demo333.yml`.
3. **Entry.** `gitops/charts/connectivity-link/templates/workstation-entry.yaml`: reencrypt Route in
   `openshift-ingress`, HTTPRoute on zuno-agent-gateway admitting only `POST /v1/chat/completions` and
   `GET /v1/models` (300 s timeout), AuthPolicy pinning the issuer, the audience, `azp: blender` and the group
   `ocp-ai-dev` (3c review: a public device client lets any realm user mint a token), RateLimitPolicy 60 requests per
   user per 5 min. Turned on in `gitops/apps/connectivity-link/application-d1.yaml`.
4. **Agents release.** `experience-clients/blender/` in zuno-demo-agents (b8ac031, VERSION 0.14.3): task `bpy`, no
   tools, `models.preferred: [reasoning, default]`, every external role forbidden, classification C3. After the
   release and its promotion, the generated routing for (blender, bpy) is `prefer` gpt-oss-20b (MaaS, direct) then
   qwen3.5-9b, `exclude` the six SaaS providers. The generator writes classification floors for agents only, so the C3
   floor is the client floor of step 2. Until the promotion the corp order answers (qwen3.6-27b first, slower).
5. **Add-on.** `docs/demo/blender-3d.md`: device sign-in, `X-Zuno-Agent: blender`, `X-Zuno-Task: bpy`, verified TLS,
   script shown in a text block, static check, run on click.
6. **Live, in order.** Push (Keycloak client, ai-gateway label); `make d1 install llm` (floor, NetworkPolicy peer);
   `make d1 install connectivity-link` (entry). Then the checks below.

## Acceptance checks

- `oc get httproute,authpolicy,ratelimitpolicy -n zuno-ai-run` shows `ai-gateway-workstation` Accepted, its policies
  Enforced.
- Without a token, `POST https://ai-gateway.apps.<domain>/v1/chat/completions` answers 401; with a token of another
  client (`azp` not `blender`) or of a user outside `ocp-ai-dev`, 403; the 61st request of a user within 5 min, 429;
  `GET /health` answers 404 (path not routed).
- With a device-flow token of ai-dev-01, a prompt returns a script that passes the add-on's static check, and the
  `model_call` span shows a local provider at C3.
- After the agents release is promoted, the provider of that span is `gpt-oss-20b`.

## Rollback

`workstationEntry.enabled: false` in the connectivity-link d1 manifest and `zuno_ai_gateway_workstation_entry: false`,
re-run both roles: ArgoCD prunes the Route, HTTPRoute, AuthPolicy and RateLimitPolicy, and the NetworkPolicy peer
goes. Remove the `blender` client from the realm file (the reconcile Job does not delete clients: delete it in the Keycloak console).
The add-on is a local file.

## Progress

- 2026-11-07: pushed 5fd22409; Keycloak client `blender` created by the reconcile Job (device endpoint answers, password
  grant refused with 400); ai-gateway rolled with `blender` in EXPERIENCE_CLIENTS. zuno-demo-agents b8ac031 (VERSION
  0.14.3) pushed, CI green, release and promotion pending. `make d1 install llm` and `make d1 install connectivity-link`
  pending (the entry and the C3 floor are not live yet).
- 2026-11-07: add-on run in Blender 4.2.3 LTS headless: five operators registered, Run builds six objects with a modifier
  and a material, `import os` refused before execution, Markdown-wrapped answers reduced to code.
