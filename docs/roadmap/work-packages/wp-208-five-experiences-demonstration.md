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
`k8s.resource.read`). Not shown: the Perses
rendering (the vendor image has no UI).

## Known defects at v0.14 (2026-11-06)

Recorded with the second browser run ([evidence](../evidence/wp-208-five-experiences-browser-2026-11-06.md)); none blocks the
acceptance, none is fixed by this work package (D4 turned out to be a wrong account).

| # | Defect | State |
|---|---|---|
| D1 | A Dify Workflow run once waited 7 minutes before its first MCP request (426 s, 2026-11-05). The wait is inside the Dify worker (`celery -P gevent -c 1`), not in the token proxy or the gateway. Not reproduced since (4.1 s after four idle minutes, 2.8 s twice before). | Open, cause not established. The token proxy now fails an MCP POST after 30 s (`MCP_TIMEOUT_S`, commit `6a275897`): a guard against a stuck upstream, not a fix of this stall |
| D2 | The Dify Chatflow on the `auto` model sometimes answers "no information" although retrieval returned passages: the answer varies from run to run | Open, model behaviour |
| D3 | Open WebUI loops in visible reasoning on a question outside its tools (cluster pods) and does not answer | Open, cause not investigated |
| D4 | kagent: the browser sign-in ended in 403 from oauth2-proxy because the account of the shared browser session is not in `ocp-ai-ops`; as `ai-ops-01` it works (checked 2026-11-06, pods diagnosis with 2 `k8s.resource.list` calls). The refusal of a Secret is still the model's, with no tool call (see Result) | Resolved (wrong account); the tool-level refusal stays proven by the WP-206 test only |
| D6 | The mcp-gateway audit shows kagent's persona with groups `agent_tekos` and `openwebui_admin` besides `ocp-ai-ops` | Open, not checked |
| D5 | OpenClaw's onboarding answer comes from its own documents, not from Confluence | Accepted, demo wording to adjust |

## Follow-up (2026-11-06): `k8s.*` from UnifAI

Tekos 0.5.0 (agents release 0.14.0, promoted by zuno-demo PR #35) declares the five `k8s.*` read tools on
`answer-technical-question`; `tool-policy.yaml` admits `ocp-ai-ops` only on them (`aap_ops` removed, so consultant-02 and
the Dify/OpenClaw service accounts gain nothing). Live on demo333 after `make d2 install mcp` and `make d2 install unifai`.
Tested in the UnifAI Team workspace `agent-tekos` (user screenshots 12:49 and 12:51): **ai-ops-01** got a grounded answer
(pod `a2a-gateway-…`, startup probe failure on 15021); the mcp-gateway audit holds one line
`tool=k8s.events.read agent=tekos task=answer-technical-question groups=[agent_tekos, ocp-ai-ops, …] allowed=True`.
**consultant-02** got a generic answer ("1 tool used" is the documentation retriever) and no `k8s.*` audit line at all:
the tools are not offered to that persona. Not tested: Arkos (declares none), a refused `k8s.*` call (the model never
sees the tool, so there is no deny line).
