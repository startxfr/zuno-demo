# WP-298: Run Claude Code on sovereign models through Praxis

- **State:** Not started
- **ADRs:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Depends on:** [WP-292](wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md)
- **Related:** [ADR-0610](../../adr/0610-generate-blender-objects-as-bpy-scripts-from-a-local-model-through-the-ai-gateway.md)
- **Target:** v0.17
- **Estimated files touched:** ~10: realm, the connectivity-link entry, the praxis NetworkPolicy, evaluations/claude-code

## Goal

From the presenter's workstation, Claude Code works on `qwen3.6-27b-instruct` and `gpt-oss-20b` through Praxis, under the presenter's own Keycloak identity, and nothing leaves the cluster.

## Steps

1. Keycloak client `claude-code` (public, device grant, audience mapper `zuno-admin-api`):
   - in `gitops/charts/keycloak/files/realm-zuno.json`;
   - applied to the live realm, since import is create-only.
2. Workstation host `praxis.<domain>` on `zuno-agent-gateway`, modelled on `gitops/charts/connectivity-link/templates/workstation-entry.yaml`:
   - an HTTPRoute in `zuno-ai-gateways` for `POST /v1/messages`, `POST /v1/messages/count_tokens` and `GET /v1/models`;
   - an AuthPolicy with `allowedClients: [claude-code]`;
   - a per-user RateLimitPolicy;
   - the Praxis NetworkPolicy peer.
3. `evaluations/claude-code/`:
   - an `apiKeyHelper` script: device sign-in, cached refresh token, prints an access token;
   - a `settings.json` example (`ANTHROPIC_BASE_URL`, the model names);
   - a README.
4. Ask the `zuno-demo-agents` session to add the experience-client declaration `claude-code` to the agents release.
5. Live, with the owner's go: the realm, then the entry.

## Acceptance

- The device sign-in works.
- Claude Code finishes a small coding task on `qwen3.6-27b-instruct`.
- The Praxis trace shows the local backend, and no SaaS call is made.
- A token of another client is refused by the AuthPolicy.
