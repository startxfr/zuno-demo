# WP-155 wave 1: evaluation parity, UnifAI pilot vs agent-runtime

Measured on `demo333` on 2026-10-23 (GPU models up), each agent run one at a time.
Stack: `zuno-unifai/unifai`, team workspaces `<agent>-pilot` (group-bound `agent_<agent>`).
Harness: branch `feat/evals-unifai-all-agents` plus the two harness fixes below. Baseline:
the same scenarios against agent-runtime/BFF on the same cluster, the same day, through
`oc port-forward` (agent-runtime, mcp-gateway, ai-gateway, guardrails, rag-service, each
`<agent>-bff`) and the public Keycloak and frontend routes.

arkos, cognos and soursage have no UnifAI workflow: arkos was not run live on UnifAI.

## Summary

| Agent | Scenarios UnifAI | Scenarios agent-runtime | Security UnifAI | Security agent-runtime | Gate `--target unifai` |
|---|---|---|---|---|---|
| comage | 18/20 (90%), 2 skipped | 20/22 (91%) | 8/8 | 8/8 | PASS |
| tekos | 17/18 (94%), 2 skipped | 19/20 (95%) | 12/12 | 12/12 | PASS |
| advantage | 12/16 (75%), 4 skipped | 19/20 (95%) | 6/6, 1 skipped | 7/7 | PASS (exactly at the threshold) |
| finage | 12/16 (75%), 4 skipped | 19/20 (95%) | 5/6, 1 skipped | 6/7 | FAIL (security) |
| naveo | 11/16 (69%), 4 skipped | 19/20 (95%) | 4/4, 1 skipped | 5/5 | FAIL (scenarios below 75%) |

Skipped items are not counted. Scenario 19 (needs the in-cluster Kubernetes client) fails
on both targets for every agent when run from a workstation: environment, it runs in the
Day 3 evaluation Job.

## Per agent

### comage
| Scenario | UnifAI | agent-runtime |
|---|---|---|
| 10 live Salesforce read | pass (a `salesforce.opportunity.read` tool call is attempted) | fail: `source_mode=none`, salesforce-mcp has no backend (known gap) |
| 11 RAG citation | **fail**: no retriever call (tool_calls empty, or only `salesforce.opportunity.read`) | pass |
| 19 in-cluster client | fail (environment) | fail (environment) |
| 6, 17 | skipped (no placeholder tiles; no bearer API) | pass |

### tekos
Only 19 fails, on both targets (environment). Skipped on UnifAI: 6, 17. Same as phase A, now with the local models up.

### advantage, finage, naveo (`status: placeholder`)
The harness assumes a placeholder agent has no UnifAI workflow, so it skips chat scenarios
and expects the blocked-chat scenarios to pass. On demo333 the three workflows exist in
their pilot team and answer entitled personas (replies of 300 to 1100 characters).

| Scenario | UnifAI | agent-runtime |
|---|---|---|
| 4 tile disabled for the entitled user | fail: workflow visible | pass |
| 7 BFF chat blocked | fail: HTTP 200 with a reply | pass |
| 9 streaming chat blocked | fail: HTTP 200 with a reply | pass |
| 10 (naveo) question blocked | fail: HTTP 200 with a reply | pass |
| 10 (advantage, finage) RAG citation | pass (retriever used) | pass |
| 11 (naveo) RAG citation | pass | pass |
| 1, 8 | skipped (chat) | pass |
| 6, 17 | skipped | pass |
| 19 | fail (environment) | fail (environment) |

Security: `unifai_forwards_identity_to_the_gateways` is skipped (placeholder). Finage fails
`finage_never_declares_sales_or_adv_knowledge_domains` on both targets: two finage tasks
(`identify-business-ready-to-invoice`, `monthly-invoice-report`) list
`salesforce.opportunity.read` in `allowed_tools`; a repository defect independent of UnifAI.

## Defects

| Class | Defect |
|---|---|
| (a) real | ADR-0007 is not enforced on UnifAI: advantage, finage and naveo (placeholder) answer chat for entitled users and their workflows are visible. Either their status flips (and the scenarios become chat/RAG/latency scenarios) or the pilot must not expose them. |
| (a) real | comage scenario 11: the retriever IS attached (checked on the cluster: the primary workflow `comage` is the agent `comage-check-deal-status`, config `retriever: $ref:retriever/knowledge-comage`, the retriever `knowledge-comage` is Ready) but the model does not call it; it calls `salesforce.opportunity.read` instead. In agent-runtime the `retrieve_reason_respond` shape always retrieves before reasoning, in UnifAI retrieval is an optional tool the model chooses. A behavioural parity gap, not a wiring defect. Options: strengthen the task prompt, or add a forced-retrieval step to the blueprint template. |
| (a) real, repo | finage tasks declare `salesforce.opportunity.read` (both targets). |
| (a) bundle | finage: two tasks declare `salesforce.opportunity.read`; `finage_never_declares_sales_or_adv_knowledge_domains` fails on both targets. Defect of the agent definitions (zuno-demo-agents), forwarded to its owner. |
| (a) decision | advantage, finage, naveo are `zuno.status: placeholder` but are served and answer 200 on UnifAI (ADR-0007). Proposed: the operator skips placeholder bundles unless `spec.servePlaceholder: true`; waiting for the user. |
| (b) environment | scenario 19 needs the in-cluster Kubernetes client; salesforce-mcp is not deployed (comage scenario 10 on agent-runtime). |
| (c) harness, fixed | comage scenario 10 had no `expect_tool` (KeyError); the tekos re-export lacked `wanted_tools` (ImportError for every `expect_tool` scenario run from an agent directory): `f07f4a79`. |
| (c) harness, fixed | advantage/finage RAG scenario used `consultant-01`, not in their team (HTTP 403 on the workflow listing): `40605665`. |
| (c) harness, open | for placeholder agents with a live UnifAI workflow, the "blocked" scenarios and the chat skips are wrong; they need a status-aware variant once the decision above is taken. |

## Commands

Secrets (`DEMO_PERSONA_PASSWORD`, `<AGENT>_FRONTEND_CLIENT_SECRET`) are read from the
`zuno-auth` Secrets at run time and never written down.

```
export UNIFAI_URL=https://unifai-ui-zuno-unifai.apps.demo333.startx.fr UNIFAI_TEAM_ID=<id of <agent>-pilot>
export KEYCLOAK_URL=https://keycloak.apps.demo333.startx.fr FRONTEND_URL=https://<agent>.apps.demo333.startx.fr
# oc port-forward: RUNTIME_URL, MCP_GATEWAY_URL, AI_GATEWAY_URL, GUARDRAILS_URL, RAG_SERVICE_URL, BFF_URL
cd evaluations/<agent>
python3 run_scenarios.py --target unifai
python3 security_checks.py --target unifai
python3 run_acceptance_gate.py --target unifai
python3 run_scenarios.py ; python3 security_checks.py     # agent-runtime baseline
```
