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
| D1 | A Dify Workflow run once waited 7 minutes before its first MCP request (426 s, 2026-11-05). The wait is inside the Dify worker (`celery -P gevent -c 1`: one stuck run also freezes the beat tasks; `py-spy` needs `SYS_PTRACE`), not in the token proxy or the gateway. Not reproduced since: 2.8 s twice, 4.1 s after four idle minutes (11:07), 3 s about six minutes after the worker restart (16:20, search 1.1 s, summary 1.9 s). | Mitigated, cause not established. The worker now has 4 slots (`CELERY_WORKER_AMOUNT=4`, commit `fb4c7602`, banner `concurrency: 4 (gevent)`), so a stuck run holds one slot of four. The token proxy also fails an MCP POST after 30 s (`MCP_TIMEOUT_S`, `6a275897`). Neither fixes the cause: if a stall comes back, take a `py-spy dump` (needs `SYS_PTRACE`, not granted) |
| D2 | The Dify Chatflow answered with odd text, "no information" or "I'm ready to help" although retrieval returned passages | Fixed (2026-11-06): the LLM node never received the user's question (system message only, `memory: null`), so the model saw the retrieved pages and no question. A user message `{{#sys.query#}}` is added (`f6733e74`). Two smaller causes were fixed on the way: the 1024-token output budget (Qwen 3.6 thinks first, the gateway served the unfinished reasoning as the answer; 3072 now) and a prompt that declined on imperative phrases (now lists what the context shows). Re-tested by the user, reported OK; the before captures are in the evidence |
| D3 | Open WebUI looped in visible reasoning on a question outside its tools (cluster pods) and did not answer | Fixed in the gateway (2026-11-06): `knowledge.tech.search` advertised an empty argument schema, so the model called it without `query` and retried; the nine in-process capabilities now declare their schema (`2ecd5842`, mcp-gateway build 44). Checked live: `tools/list` shows `query` required. Re-tested by the user in Open WebUI (two chats): no loop, one answer |
| D4 | kagent: the browser sign-in ended in 403 from oauth2-proxy because the account of the shared browser session is not in `ocp-ai-ops`; as `ai-ops-01` it works (checked 2026-11-06, pods diagnosis with 2 `k8s.resource.list` calls). The refusal of a Secret is still the model's, with no tool call (see Result) | Resolved (wrong account); the tool-level refusal stays proven by the WP-206 test only |
| D5 | OpenClaw's onboarding answer came from its own documents, not from Confluence: the claw has the `zuno` MCP server configured, but the bare question matches its own vocabulary | Fixed in the script (2026-11-06): the demo sentence names Confluence; re-tested by the user on the `consultant-02` claw, it calls `Zuno Confluence-page-search` and lists the six pages |
| D6 | The mcp-gateway audit shows kagent's persona with groups `agent_tekos`, `ocp-ai-ops` and `openwebui_admin` | Explained (2026-11-06): these are the real Keycloak groups of the user `ai-ops-01` in `realm-zuno.json` (Tekos entitlement, cluster operations, Open WebUI admin); kagent's token is that persona's. The audit lines still read `agent=kagent task=diagnose` and only the five declared tools were allowed, so no extra capability is shown. Hardening option, not done: a dedicated persona for kagent with `ocp-ai-ops` only |
| D8 | 20 failed Dify calls in 24 h were counted per attempt (10 on `local`, 10 on `local-maas`) | Fixed (2026-11-06): they were HTTP 400, the gateway's own reply cap filled the 32 768-token window to the token (32 768 - 24 605 = 8 163 for a prompt of 24 606 tokens). The cap now keeps a 5 % margin (`f294dd1e`) and a model's own 400/413/422 is no longer replayed on its same-model sibling (`4d9934d5`); ai-gateway build 44. The 400 path itself was not triggered live (an oversized prompt is skipped by the pre-flight and served by gpt-oss); it is covered by `test_wp208_client_rejection.py` |
| D9 | The a2a-gateway and the mcp-gateway read the agents release only at pod start, so promoting a new agents release needs the role to be run again | Closed as by design (2026-11-06): `make d2 check agents` now compares the digest the gateways run with the lock and fails on a gap |
| D10 | UnifAI's Tekos agent is reachable only through the Team workspace `agent-tekos`, with no agent list; it can confuse the demo | Closed (2026-11-06): step 8 of the script says so |
| D11 | The first run of the Dify role (`make d2 install dify`, configure task) fails and the retry passes, twice out of two on 2026-11-06; the failure is hidden by `no_log` and the API log shows only the login before it stops | Open, cause not investigated; retry the role once |

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

Screenshots: [ai-ops-01 question](../../assets/img/unifai-tekos-k8s-ai-ops-01-question.png),
[ai-ops-01 answer](../../assets/img/unifai-tekos-k8s-ai-ops-01-answer.png),
[consultant-02 generic answer](../../assets/img/unifai-tekos-k8s-consultant-02-generic-answer.png).
