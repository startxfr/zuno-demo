# WP-174: Arkos to Tekos delegation, state of 2026-11-02

Status: live wiring done on demo333, the behavioural proof is NOT made yet (no GPU node was available when the operator fix landed).

## Chain of events

| Step | Result |
|---|---|
| Direction | reversed on 2026-11-01: Arkos delegates to Tekos (`answer-technical-question`, depth 1); Arkos is already C3/local-only, so the static C3 raise costs nothing there |
| Platform | operator 0.1.45 then 0.1.47; app images rolled by a0; a2a-gateway rebuilt (reads `X-Zuno-Task`); bundle CR fields `spec.delegation` and `ceilings.delegationTargets: ["tekos/answer-technical-question"]` on arkos (devel `0992e62a`); LLM client timeout 200 s on all UnifaiLLM (`95d1b879`) |
| Release | agents v0.8.0 (Arkos 0.2.1, Tekos 0.4.4), admitted with `make d3 admit agents RELEASE=v0.8.0 UPDATE_LOCK=1` (lock moved from v0.6.3, `54698705`), bundles repinned (arkos `d53b6fe0`, tekos `5346bd20`), checked read-only by a9 |
| Tekos first token | 2.0 s with local reasoning first (was 9.7 s), 52/52 stresstest (08) |
| First delegation attempts | failed: `iem.delegate_task` returned `Node tekos is not adjacent, or the uid is wrong` in 0.0 s, twice; the a2a-gateway saw only the public agent card, no POST. Same with a real SSO session in the UI (run `3d3e45e2-8d89-4a4e-b037-450fa22e9658`, trace `e7a54aafaf9730e6436ee07b3c4f0ada`) |
| Cause | the orchestrator prompt named the target by title and key `tekos/answer-technical-question` while the graph uid of the A2A node is `a2a-tekos` |
| Fix | operator 0.1.49 (orchestrator prompt carries the exact node uids and a REMOTE work item rule), live on demo333 on 2026-11-02; a9 checked the four arkos orchestrators read-only |
| Control | the persona blueprint `test-consultant-01-a2a` (Personal workspace) reaches Tekos through the gateway: `POST /agents/tekos/ 200`, reply in 10 s; so the A2A node, the user's forwarded token and the gateway work |

## Lessons

- Arkos scenario 21 first passed on the topic of the reply while both `delegate_task` spans had failed (the model knew the answer). A reply is not a delegation: the scenario now requires a `delegate_task` span with `mas.success` true (`8aa9494a`).
- `IdentityTokenUnavailable` at node init is expected and harmless (no session exists at graph build); it was not the cause.
- Tool error texts were invisible until the multiagent image `devel-77e1a6421` logged them and put them in the span status message.
- A remote model cannot stand in while there is no GPU: Arkos tasks are `local_only_for: [C2, C3]` and the chain is C3.

## Agents v0.8.1 (2026-11-02, evening)

Release v0.8.1 (tekos 0.4.5, arkos 0.2.2, naveo 0.1.1) adds `local_only_for: [C1, C2, C3]` to five Confluence-reading tasks. It was admitted (`780cc227`) and the bundles repinned: arkos `okf-arkos@sha256:c9cfa572…` and tekos `okf-tekos@sha256:33c8a076…` are Ready; naveo is pinned but stays a non-served placeholder (as before). The delegation fields of the Arkos CR are unchanged. Rollback of the pair: repin to the v0.8.0 digests (arkos `d53b6fe0…`, tekos `5346bd20…`), keeping `spec.delegation` and `ceilings.delegationTargets`.

Offline checks on devel after the admission: `check_docs.py` passes; the evaluation tests pass except `test_scenario_failover.py::test_verify_falls_back_to_the_counter_delta` (the test mocks `_query_provider_counts` while `verify_one_agent` first calls `_query_provider_counts_or_none`, since `4d059a51`; not related to the release). No Arkos or Tekos scenario expects a remote route.

## Live attempt with the models back (2026-11-03)

One GPU node came back (three of the four models Ready). Arkos scenario 21 as `eval-consultant-01` failed: both `iem.delegate_task` spans failed with "Node a2a-tekos is not adjacent, or the uid is wrong" and, on a retry, "Node agent-2 is not adjacent" (Tempo trace `2634004a…`, calls made by the `orchestrate` node). The uid is right and the A2A node is in the plan (`after: orchestrate`). Cause found by a9 reading the runtime: the orchestrator's delegation policy drops every adjacent node that has a path to the finalizer, and the operator's blueprint puts both workers (`agent-2`, `a2a-tekos`) before the write stage and `finish`, so neither is delegable (`topology.list_adjacent` omits them too). This is an operator blueprint bug introduced with the delegating shape (0.1.43 to 0.1.49): the workers must be leaves of the orchestrator. The fix ships in the next operator release; the proof is rerun after it.

## Second live pass (2026-11-03, both GPU nodes back, ai-gateway build 36, agents v0.9.2)

- Arkos acceptance scenarios as `eval-consultant-01`: 16 of 19 pass (84%, threshold 75%), 2 skipped. The three failures: scenario 21 (the delegation, the operator blueprint defect above), scenario 10 (no Confluence tool call: the orchestrator spends its rounds on the refused `iem.delegate_task` calls before the draft step; to recheck after the fix) and scenario 19 (needs an in-cluster kube config, not runnable from a workstation).
- Mermaid in the UnifAI chat on image devel-c33f19799 (Personal blueprint `test-consultant-01-chat`, SSO as `eval-consultant-01`): a valid flowchart renders as an SVG in the answer (`[data-testid=mermaid-diagram] svg`), and a deliberately invalid request leaks no error graphic into the page. A long answer with a diagram of about 15 nodes renders too; asking for 25 nodes with long paragraphs gave an answer without a diagram block, which says nothing about the renderer.
- Cost of one Arkos `draft-architecture-testimonial` turn that tries to delegate and fails (ai-gateway counters `zuno_model_tokens_total` and `zuno_model_calls_total`, labels `agent="arkos"`, `user="eval-consultant-01"`, a delta around one run): about 270,000 prompt tokens, 44,000 completion tokens and 117 model calls, all on the local providers. Caveat: the window may include other traffic of the same persona, so read it as an upper bound; the failed delegation retries inflate it, so the figure for a working delegation has to be measured again after the operator fix.

## Operator 0.1.50 and 0.1.51 on demo333 (2026-11-03)

- **0.1.50** (catalog pin `bd0fd5df`): the workers are leaves of the orchestrator. `iem.delegate_task` is no longer refused: four Arkos runs show `execute_tool iem.delegate_task` with `mas.success` true (for example trace `5a97accbe663c076602e895312cf6784`). All of them went to `agent-2`, the draft worker: the generated orchestrator prompt said "Delegate to `agent-2` first" and listed `a2a-tekos` only "when the user asks". Scenario 21 still failed (the model answered alone), and the a2a-gateway saw no call.
- **0.1.51** (catalog pin `8905e13a`): the prompt names `agent-2` as the agent's own and presents the A2A targets as the way to reach another agent's knowledge (R-524). Scenario 21, trace `fb4f78021ae13745fa52ca494630554f`: the model calls `a2a-tekos`. The worker log shows the agent card `GET /agents/tekos/.well-known/agent-card.json` 200, `POST /agents/tekos/` 200 after 8 s and `a2a.delegated`; `platform/testing/a2a_delegation_check.py` passes ("a2a-gateway served 1 call(s) to tekos"). A first `delegate_task` failed with "`work_item_id` is a required property" and the second succeeded.
- **Not proven**: the final reply of the turn is empty (`reply_chars=0`), so the Tekos content does not reach the user, and no mcp-gateway audit line with `delegated_by` was seen. The orchestrator runs a single cycle (it ends with the A2A item waiting) and no second cycle starts after `a2a.delegated`: the A2A result does not come back to `orchestrate`, and `finish` runs with nothing collected. Suspected cause: the 0.1.50 blueprint change, which removed the path by which a worker result reached the finalizer. Reported to the operator owner; scenario 7 returns an empty reply intermittently since 0.1.50 for the same reason, probably.
- Arkos scenarios on 0.1.51: 14 of 19 on the last pass (7, 10, 11, 19 and 21 failed; 19 cannot run from a workstation). Cost of a working delegating turn: not measured.

## What remains

1. An operator release that routes the A2A result back to the orchestrator (the final reply is empty on 0.1.51), pinned on demo333.
2. Behavioural proof as `eval-consultant-01`: SSO chat in the UI (Team agent-arkos, workflow arkos) and arkos scenario 21 (`TEMPO_URL` set): a `delegate_task` span with `mas.success` true, a `POST /agents/tekos/ 200` at the a2a-gateway, Tekos content in the answer, then the read-only check `platform/testing/a2a_delegation_check.py` (cc) and the refusal checks of `evaluations/common/delegation_checks.py` on the gateway.
3. The cost of an Arkos turn that delegates (the traces carry no token counts: use the ai-gateway counters).
4. Then WP-174 Done and ADR-0401, ADR-0403, ADR-0406 to Implemented.
