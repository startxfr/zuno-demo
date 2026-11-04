# WP-204: Install Dify on demo333

- **State:** Not started
- **ADRs:** [ADR-0599](../../adr/0599-serve-a-no-code-workflow-canvas-with-dify-as-an-experience-client.md), [ADR-0601](../../adr/0601-inject-client-credentials-tokens-for-experience-clients-without-oidc-passthrough.md)
- **Depends on:** [WP-202](wp-202-common-preparation-for-dify-and-kagent.md), [WP-203](wp-203-dify-preparation.md)
- **Related:** [WP-205](wp-205-dify-external-knowledge-adapter-over-the-mcp-gateway.md), [WP-208](wp-208-five-experiences-demonstration.md)
- **Target:** v0.14
- **Estimated files touched:** `gitops/charts/dify`, `gitops/apps/dify`, `ansible/roles/dify`, `gitops/charts/postgresql` (database block, user, ExternalSecret), Keycloak client `dify` (four touch points), Vault seed, `zuno-demo-agents/experience-clients/dify`

## Goal

Dify runs in `zuno-dify` under ADR-0599, installed and checked by `make d2 install dify` and `make d2 check dify`.

## Steps

1. Wrapper chart at the WP-203 pins: values, token proxy instance, oauth2-proxy front door, Route (claimed by the front
   door first), EgressFirewall (Keycloak Route allowed, `0.0.0.0/0` denied), egress NetworkPolicy.
2. Database `dify` in `zuno-postgresql` following the MLflow pattern (values block, `spec.users`, ExternalSecret,
   Vault path `dify/postgresql-app`).
3. Keycloak client `dify` (front door plus service account with the `persona` claim): realm file, ExternalSecret, KC_VAULT
   item, Vault seed. **Seed Vault before pushing the client.**
4. Experience-client declaration `experience-clients/dify` in the agents release (tasks `chat`, `workflow`, allowed
   tools, groups), released and pinned.
5. Role `ansible/roles/dify`: seed, apply the Application, wait, configure the model provider and the MCP tool through
   Dify's API, check (pins, `client="dify"` series after a test chat).

## Acceptance

A workflow drawn in Dify answers through the ai-gateway (`client="dify"`), calls an mcp-gateway tool (audit
`agent=dify`), and the running image IDs match the pinned digests.
