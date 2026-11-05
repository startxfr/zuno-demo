# WP-204: Install Dify on demo333

- **State:** Done 2026-11-05 on demo333: installed, configured (single local administrator, OpenAI-compatible plugin 0.0.73, models `auto` and `zuno-code`, MCP tool through the token proxy), PyPI window closed. Evidence: chat through the proxy 200 (`zuno-code` routed to codestral-latest), MCP `tools/list` returns the six chat tools for consultant-02, ai-gateway log `agent=dify`, `make d2 check dify` green. Metric proven 2026-11-05 after RHOAI 3.6.0-ea.2: `zuno_model_tokens_total{client="dify"}` = 88 in `prometheus-k8s` (openshift-monitoring; the user-workload and mesh Prometheus do not hold it), chats `auto` (qwen3.6-27b-instruct) and `zuno-code` (codestral-latest) 200. Not exercised: a chat typed in the Dify UI. WP-205 (knowledge adapter) is next.
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
2. Databases `dify` and `dify_plugin` in `zuno-postgresql`, one role, following the MLflow pattern (values block,
   `spec.users`, ExternalSecret, Vault path `dify/postgresql-app`), and `zuno-dify` allowed into `zuno-data`.
3. Keycloak client `dify` (front door plus service account with the `persona` claim): realm file, ExternalSecret, KC_VAULT
   item, Vault seed. **Seed Vault before pushing the client.**
4. Experience-client declaration `experience-clients/dify` in the agents release (tasks `chat` and `code`, allowed
   tools, groups), released and pinned.
5. Role `ansible/roles/dify`: seed, apply both Applications, wait, check (pins, no route to the gateways, Route behind
   Keycloak). **Then, against the running Dify API:** install the plugin package (PyPI window), register the model
   provider and the MCP tool, create the per-person accounts, and verify the `client="dify"` series after a test chat.
   Dedicated S3 bucket: `zuno_dify_s3_*` in `ansible/confidential.yml`.

## Acceptance

A workflow drawn in Dify answers through the ai-gateway (`client="dify"`), calls an mcp-gateway tool (audit
`agent=dify`), and the running image IDs match the pinned digests.
