# WP-207: kagent preparation and install

- **State:** Done 2026-11-05 on demo333: kagent 0.10.4 installed as a thin client in `zuno-kagent` (controller with namespaced Roles only, UI behind oauth2-proxy, token proxy, own database), `zuno-sre` Ready and answering from mcp-gateway tools only (listed the pods of `zuno-ai-run`); `zuno_model_tokens_total{client="kagent"}` = 2488 in prometheus-k8s. Persona `ai-ops-01`. Details and traps in the evidence file.
- **ADRs:** [ADR-0600](../../adr/0600-govern-kubernetes-read-tools-in-the-mcp-gateway-and-admit-kagent-as-a-thin-operations-client.md), [ADR-0601](../../adr/0601-inject-client-credentials-tokens-for-experience-clients-without-oidc-passthrough.md)
- **Depends on:** [WP-202](wp-202-common-preparation-for-dify-and-kagent.md), [WP-206](wp-206-kubernetes-read-tools-behind-the-mcp-gateway.md)
- **Related:** [WP-208](wp-208-five-experiences-demonstration.md)
- **Target:** v0.14
- **Estimated files touched:** evidence `docs/roadmap/evidence/wp-207-kagent-spike.md`, `gitops/charts/kagent`, `gitops/apps/kagent` (d0 CRDs, d1 controller), `ansible/roles/kagent`, Keycloak client `kagent`, `zuno-demo-agents/experience-clients/kagent`

## Goal

kagent runs in `zuno-kagent` as a thin client: one ModelConfig and one RemoteMCPServer through the token proxy, its own
tool servers and sample agents off.

## Steps

1. **Spike** (scratch namespace `zuno-kagent-scratch`, user's go): chart pins and digests; CRDs (cluster-scoped?);
   controller RBAC (cluster-wide?) and whether it can be namespaced; `providers: null` and every bundled tool server
   and agent disabled; `restricted-v2` fit; ModelConfig to the proxy with the CA from `kube-root-ca.crt`;
   RemoteMCPServer to the proxy `/mcp`; where the A2A endpoint listens; UI behind oauth2-proxy.
2. **Chart.** d0 Application for the CRDs chart, d1 for the controller and UI, both pinned. Token proxy instance, front
   door, EgressFirewall (allow the control plane on 6443 only if the controller needs the API outside the cluster
   network), NetworkPolicy restricting the A2A port to the UI.
3. **Identity.** Keycloak client `kagent` (front door plus service account with the `persona` claim of the operations
   persona). Seed Vault before pushing.
4. **Declaration.** `experience-clients/kagent` with task `diagnose` granting the WP-206 capabilities; a declarative
   Agent `zuno-sre` whose prompt explains the platform namespaces.
5. **Role and check.** `make d2 install kagent` and `make d2 check kagent` (pins, `client="kagent"` series, one
   `tools/list`).

## Acceptance

Asked why a pod is failing, `zuno-sre` answers from mcp-gateway tools only (audit `agent=kagent`, `capability=k8s.*`),
with `zuno_model_tokens{client="kagent"}` growing and no tool server of kagent's own running.
