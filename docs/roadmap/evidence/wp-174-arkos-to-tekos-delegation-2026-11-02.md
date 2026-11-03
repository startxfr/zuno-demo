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

## Operator 0.1.52 and 0.1.53 on demo333 (2026-11-03)

- **0.1.52** (catalog pin `7ba9072b`): the A2A answer returns to the orchestrator (R-525), but the model re-delegated the same question to Tekos 10 to 11 times per turn, because it never marked the work item done (22 `POST /agents/tekos/` 200 for two delegating runs, traces `a8a0351de8e780dbc478f6a499f027f2` and `66ab22fff98b5c5671acf8b4dfce199c`). A run could end with an empty reply (scenario 11 failed twice).
- **0.1.53** (catalog pin `90146463`, catalog `sha256:8279a9bb8ee6de6604c38c6aff75015d7f6949412b9c2817a2b851dd3bc1f3d2`; application images `devel-8c86d4f19` rolled in `a2cbb665`): R-528 tells the orchestrator that an agent's answer is final, and the multiagent image caps a work item at 3 delegations (past the cap `delegate_task` returns "was already delegated 3 times and is marked done"). Live on demo333 on 2026-11-03 (18:17 to 18:30 local):
  - Scenario 21 (hardened: 1 to 3 A2A messages, a non-empty reply carrying the Tekos content) passed 3 of 3 as `eval-consultant-01`: A2A sends 3, 2 and 1; replies of 6074, 3489 and 2691 characters.
  - The full Arkos suite: 18 of 18 (6, 17 and 19 skipped as not applicable).
  - `platform/testing/a2a_delegation_check.py --delegator arkos --target tekos --since 40m`: 9 calls served to `tekos`, 9 x 200, 0 x 404.
  - mcp-gateway audit: 16 lines with `delegated_by=arkos:draft-architecture-testimonial`.
  - The cap fired in traces `b9c9982da9e180eb911c30250668e8e3`, `e3661c262d1e9d97192b53231634f4d3` and `a391670119861d02335fe0e388c1a0d5`.
  - The `FAILED` labels printed by the scenario were a harness label (a span without `mas.success`), fixed in `0b55200e`. No `mas.session` or `send_message` span has an error status.
- **Unrelated defect seen**: Tekos calls git-forge `list_repositories` without `provider`, `owner` and `repo`, which returns a 502 (traces `8e160bd26cda4688485f4315ccbe69fb`, `a695d489fb4297e09daa9af30d05dc90`, `a28c1c212a58f0cde28f1843b9b34e1b`).
- **Refusal checks replayed** (`evaluations/arkos/security_checks.py`, `eval-consultant-01`, operator 0.1.53): the delegated surface exposes only read tools; refused without the target entitlement, with a depth header that disagrees and with half a chain (403). The undeclared target, the depth limit and the cycle answer 200 with an EMPTY tool list on `tools/list` and `denied: ... (ADR-0401)` / `(ADR-0406)` on `tools/call`; the checks expected a 403 and were corrected to accept an empty surface (`bde97594`). Write refusal: the delegated surface lists no write tool.
- **Cost of one delegating turn** (ai-gateway counters, user `eval-consultant-01`, idle baseline checked, scenario 21, one passing turn of about 90 s, 2026-11-03 19:21): Arkos 753,363 tokens in 208 model calls, Tekos 85,696 tokens in 104 model calls, about 839,000 tokens and 312 calls for the turn, all on local `gpt-oss-20b`. The `evaluation` quota class of the persona is exhausted by a few such turns (a rate limit of about 16 minutes followed).
- **Not proven**: `X-Zuno-Max-Tokens` end to end. Still red: `unifai_forwards_identity_to_the_gateways` (the orchestrator no longer calls MCP tools itself, the worker does).

## Cost levers, git-forge schema and what the fork does not do (2026-11-03, evening)

- **git-forge schema (mcp-gateway)**: `tools/list` advertised an open schema, so the model omitted the required arguments of `git.repository.list` (provider, owner, owner_type) and got 502s (6 traces between 18:00 and 20:50). The gateway now reads the schema and description the backend publishes (cached 300 s, 3 s timeout, open-schema fallback): commits `8625492f` and `4c6bef54` (the SDK field is `input_schema`, not `inputSchema`; the first build kept the open schema), builds `mcp-gateway-38` and `-39`. Live: `git.repository.list` requires provider, owner and owner_type; `git.repository.read` requires provider, owner and repo; listing takes 0.45 s cold, 0.12 s cached. Four Arkos turns afterwards show no git-forge error, but none called git-forge either, so a real Tekos call is not yet shown.
- **Delegation cap at 1** (`MAS_MAX_DELEGATIONS_PER_ITEM=1` for multiagent and its worker, `bf128167`, rolled 21:00): four scenario 21 turns, each with exactly one A2A message and a correct answer. Arkos 882,973 / 630,747 / 591,682 / 339,729 tokens in 208 / 182 / 182 / 117 model calls; Tekos 25,376 / 27,508 / 26,104 / 34,164 tokens in 26 / 39 / 39 / 52 calls. Against one turn at the cap of 3 (Arkos 753,363 tokens and 208 calls, Tekos 85,696 and 104), Tekos costs about a third; Arkos does not move measurably (high variance, 4 samples). A turn with no delegation at all cost 309,231 tokens and 104 Arkos calls: most of the cost is Arkos's own loop, which needs the per-node call counter b9 plans for 0.1.55.
- **Quality at the cap of 1**: the Arkos suite passed 17 of 18 (scenario 10 failed, 7, 11 and 21 passed). Scenario 10 is flaky and its cause is not isolated: three further runs gave one pass, one rate-limited run (the `evaluation` quota class is exhausted by a few turns) and one run where the model read the RAG retriever and git-forge but not Confluence. Whether the cap changes this is not shown (no repeated baseline at the cap of 3). The scenario now also accepts an allowed mcp-gateway call in the run's trace (`137c78b3`), because the worker's tool call is not in the orchestrator's stream.
- **Cancellation of a delegation no longer awaited (ADR-0406 clause 4)**: not implemented in the fork. `cancel_task` exists in the A2A client but nothing calls it; on the node's 30 s polling timeout (hard-coded, 0.5 s x 60) the remote task keeps running, and a user abort or a cancelled Temporal run does not reach it. Planned by b9 for 0.1.55 together with a configurable timeout; the live proof needs it.
- **`X-Zuno-Max-Tokens`**: the ai-gateway cuts at the header (64 gives 64 and 128 gives 128 completion tokens). The operator sets the header on every model call and on the A2A hop from the task ceiling (b9, `agentbundle_controller.go:392`). Arkos's drafting task declares 8192, so no observed call reaches the cap (the largest has 1,781 completion tokens; one call has 1,537, near the 1,536 of `structure-demo`). A test bundle with a ceiling of 64 would need a signed task, since bundles are verified from the signed release; not done. Open until a span attribute (offered by b9 for 0.1.55) or a low-ceiling task shows the value on the wire.

## What remains

1. `X-Zuno-Max-Tokens` on the wire for a UnifAI model call, and the cancellation of an abandoned delegation (ADR-0406 clause 4): both wait for operator 0.1.55.
2. Whether the cap of 1 stays, and what to do with Arkos's own loop (117 to 208 model calls per turn): a decision, with the per-node counter of 0.1.55.
3. Scenario 10 flakiness, and a real Tekos call through the new git-forge schema.
