# WP-208: Five experiences demonstration

- **State:** Not started
- **ADRs:** [ADR-0599](../../adr/0599-serve-a-no-code-workflow-canvas-with-dify-as-an-experience-client.md), [ADR-0600](../../adr/0600-govern-kubernetes-read-tools-in-the-mcp-gateway-and-admit-kagent-as-a-thin-operations-client.md)
- **Depends on:** [WP-204](wp-204-install-dify-on-demo333.md), [WP-205](wp-205-dify-external-knowledge-adapter-over-the-mcp-gateway.md), [WP-207](wp-207-kagent-preparation-and-install.md)
- **Related:** [WP-184](wp-184-three-experiences-demonstration.md)
- **Target:** v0.14
- **Estimated files touched:** `docs/demo/five-experiences.md`, `gitops/charts/{grafana,perses}` dashboards

## Goal

One demo script and one dashboard show UnifAI, Open WebUI, OpenClaw, Dify and kagent on the same identity, models,
guardrails, tools and quotas.

## Steps

1. Extend the "Three experiences" dashboards with `client="dify"` and `client="kagent"`, and the mcp-gateway `k8s.*`
   capability calls.
2. Demo script: a business RAG workflow drawn in Dify (knowledge node over Confluence, model, tool), the same question
   in UnifAI and Open WebUI, a cluster diagnosis in kagent and the same read tool used from UnifAI by an operations
   persona; the limit that Dify and kagent count per persona.
3. Live rehearsal on demo333 with the user's go; record it.

## Acceptance

The rehearsal runs end to end and the dashboard shows all five clients.
