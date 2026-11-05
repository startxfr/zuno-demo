# WP-208: Five experiences demonstration

- **State:** Done (2026-11-05: dashboards and script written, terminal and browser rehearsal done on demo333, see the evidence)
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

## Result (2026-11-05)

The rehearsal ran end to end on demo333 and the dashboard shows all five clients with data in every row. Reservation
recorded with the closure: in the browser rehearsal the kagent refusal to read a Secret was **demonstrated at the model
level, not at the tool level** (the agent declined from its prompt and made no tool call; the server-side refusal
`resource not allowed: Kind=Secret` was proven earlier, in the WP-206 test and in the `downstream_error` of
`k8s.resource.read`). Not shown: the `k8s.*` tools from UnifAI (no agent declares a task for them) and the Perses
rendering (the vendor image has no UI).
