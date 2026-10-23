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

## Re-run on operator 0.1.25 (2026-10-23, later)

Operator 0.1.25 (retrieve-first directive for agents with a retriever, `teamOf`, keyless)
recreated the teams as `agent-<name>` (new team ids). Check done first:
`oc -n zuno-unifai get unifaiagent comage-check-deal-status -o jsonpath='{.spec.config.system_message}'`
now ends with "Before you answer, always search the knowledge base with your knowledge
retrieval tool and ground the answer in what it returns, citing the pages you used. Use your
other tools only after that." The harness is `origin/demo222` (16154c3c), which carries the
wave 1 fixes and the ADR-0512 exception for finage.

| Run | Before (operator 0.1.20..22) | After (0.1.25) |
|---|---|---|
| comage scenarios `--target unifai` | 18/20 (90%) | 17/20 (85%), run twice with the same result |
| comage scenario 10 | pass | pass, then fail on the second run (`tool_calls=[]`) |
| comage scenario 11 | fail (`salesforce.opportunity.read`) | **fail**, both runs: `tool_calls=['salesforce.opportunity.read']` |
| comage scenario 8 (first token) | pass | fail once (`no token received`), pass otherwise: model latency, not stable |
| comage security `--target unifai` | 8/8 | 7/8: `unifai_forwards_identity_to_the_gateways` got `tool_calls=[] reply_len=137` |
| finage security `--target unifai` | 5/6, 1 skipped | **6/6 with 1 skipped** (`finage_never_declares_sales_or_adv_knowledge_domains` passes) |
| tekos scenarios `--target unifai` | 17/18 (94%) | 14/18 (78%): environment, see below |

Scenario 11, probed by hand with the scenario's query as `sale-01`: the model does call
`docs_rag_retriever_tool` on some turns (so the directive works), calls
`salesforce.opportunity.read` first on others, and in both cases the turn ends with the
ReAct error `Reasoning too short (0 chars, min 10)`: after a tool call the model produces an
empty final message and the turn fails. The retrieve-first directive is followed
non-deterministically by the local model; the empty-final-answer failure (also noted in
phase A) is a second, independent defect, and also explains the 137-character reply of the
identity check.

Tekos regressions (scenarios 8, 10, 11) are environmental: `consultant-01` has exhausted its
daily token budget (`Rate limit reached: quota_exceeded (quota_class=standard,
dimension=user, budget_tokens=3000000, window=24h)`), so every turn returns that message with
no tool call. The evaluations of this wave consume that budget; tekos has to be re-run after
the window resets or with a persona-specific budget.

Commands: as above, with `UNIFAI_TEAM_ID` taken from `teams.list` (names `agent-<name>`):
`run_scenarios.py --target unifai` (comage twice, tekos), `security_checks.py --target unifai`
(comage, finage). advantage and naveo were not re-run (placeholders, ADR-0007 decision pending).

## Re-run after the ReAct retry and the gateway reasoning fallback (2026-10-23, later)

Deployed: multiagent `devel-472339706` (a recoverable ReAct error such as "Reasoning too
short" lets the model retry instead of ending the turn; `retrieve_first` present, not yet
enabled, operator 0.1.26 pending) and the ai-gateway built from `7685df12` (when the content
is empty, no tool call is made and a `reasoning` text exists, it is served as content with
`zuno_reasoning_fallback: true`; counter `zuno.model_empty_responses`). Harness: `origin/demo222`
(`d1b5c997`). comage only, personas as in the harness (sale-01, sale-02; no persona hit a budget).

| Run | Before fixes (operator 0.1.22) | After the operator 0.1.25 prompt | After ReAct retry + gateway fallback |
|---|---|---|---|
| comage scenarios `--target unifai`, run 1 | 18/20 (90%) | 17/20 (85%) | 16/20 (80%): 8 first token 9.7 s, 10 `tool_calls=[]`, 11, 19 |
| comage scenarios, run 2 | - | 17/20 (85%) | 18/20 (90%): 11, 19 only |
| comage security `--target unifai` | 8/8 | 7/8 | 7/8 (`unifai_forwards_identity_to_the_gateways`: `tool_calls=[] reply_len=115`) |
| comage gate `--target unifai` (scenarios, security, gate checks) | PASS | - | PASS: 17/20 (8 first token 6.75 s, 11, 19), security 8/8, gate checks 4/4 |

Scenario 11 still fails on every run: `tool_calls=['salesforce.opportunity.read']`, the model
reads Salesforce and never calls the retriever, so the retry does not change the choice of
tool; the intended lever is `retrieve_first` (operator 0.1.26). Scenarios 8 and 10 vary
from run to run (first-token 6.75 to 9.7 s on the shared local model, a turn without any tool
call), as do the identity check and its 115-character reply: the results are within the noise
of a shared GPU model, the totals 16 to 18 out of 20 cover the whole range seen before.

Raw Prometheus (thanos-querier, `oc whoami -t`):
`sum by (provider,model,recovered)(zuno_model_empty_responses_total)` returns a single series,
`provider=local-wesh, model=qwen3.5-9b-wesh, recovered=true`, value 7 (about 4.5 over the last
hour); no series with `recovered=false`. So the gateway recovered 7 empty responses from
qwen3.5-9b-wesh and none were lost. `Reasoning too short` occurrences in
`unifai-multiagent-temporal-worker` and `unifai-multiagent-be` logs over the last 40 and 60
minutes: 0 (it was the reply of the failing turns before).

Commands: `run_scenarios.py --target unifai` (twice), `security_checks.py --target unifai`,
`run_acceptance_gate.py --target unifai` in `evaluations/comage` (setup as above); then
`oc -n zuno-unifai logs deploy/unifai-multiagent-temporal-worker --since=40m | grep -c 'Reasoning too short'`
and an instant query on `zuno_model_empty_responses_total` against the thanos-querier route.

## Re-run on operator 0.1.26 (2026-10-23, devel, demo333)

Operator 0.1.26 with `retrieveFirst` on comage and tekos. Served on UnifAI: comage and tekos;
advantage, finage and naveo are placeholders ("not served", ADR-0007); arkos, cognos and
soursage are not deployed, so no parity run exists for them.

| Check | Result |
| --- | --- |
| comage scenarios `--target unifai` | 18/20 (90%), PASS. Scenario 11 now passes. Failures: 8 first token 9.4 s (objective 6 s), 19 (needs the in-cluster Kubernetes client) |
| comage security `--target unifai` | 8/8, including `unifai_forwards_identity_to_the_gateways` |
| tekos scenarios `--target unifai` | 17/18 (94%), PASS. Only 19 fails (in-cluster client) |

Scenario 11 passes because the expected page name is accepted as proof of retrieval
(`2a272fe7`): with `retrieveFirst` no retriever tool event is emitted. UnifAI has no sales
source for comage, so for that agent the scenario proves a grounded reply, not a sales citation.

## arkos on operator 0.1.27 (2026-10-23, devel, demo333)

arkos is served (bundle release v0.1.1, `plan_draft_write`, team `agent-arkos`, `retrieveFirst` on).
Personas: consultant-01 sees the four arkos workflows, sale-01 sees none.

| Check | Result |
| --- | --- |
| scenarios `--target unifai`, run 1 | 16/18 (89%): 8 first token 7.7 s, 19 (in-cluster client) |
| scenarios inside the gate, run 2 | 14/18 (78%, threshold 75%): 8 first token 11.9 s, 10 (the agent read Confluence with `confluence.page.read`, the scenario expects `confluence.page.search`), 11 (`tool_calls=[]`, expected page named: `retrieveFirst`), 19 |
| security `--target unifai` | 11/11 after a harness fix (below) |
| gate `--target unifai` | OVERALL PASS: scenarios 78%, security 11/11, capability gates 4/4 |

Harness fix: `unifai_forwards_identity_to_the_gateways` sent "Search our Confluence for the
Satellite page...", which the arkos graph answers by drafting a DAT without calling the
search tool (`tool_calls=[]`, a reply of 2199 characters). The probe now asks explicitly for the
Confluence search tool; the tool call then reaches the MCP gateway with the caller's token.

Margin is thin (78% against 75%) and varies between runs with the model's tool choice and
the first-token latency under load. Scenarios 10 and 11 should accept a read or the expected
page as proof, as the tekos scenario already does; not changed here.

### arkos harness hardening (same day)

Scenario 11 now asks the S0R42 question and requires the page name, as tekos does (arkos reads the
same Confluence sources, `retrieveFirst` emits no retriever event). Scenario 10 accepts
`confluence.page.read` as well as `confluence.page.search` as proof of reaching live Confluence (the
model chooses between them). Scenarios `--target unifai`: **17/18 (94%)**, only 19 (in-cluster client)
fails; first token passed on this run, so the latency remains load-dependent.
