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

## What remains

1. GPU nodes and the four models back (on 2026-11-02 both GPU nodes were NotReady).
2. Behavioural proof as `eval-consultant-01`: SSO chat in the UI (Team agent-arkos, workflow arkos) and arkos scenario 21 (`TEMPO_URL` set): a `delegate_task` span with `mas.success` true, a `POST /agents/tekos/ 200` at the a2a-gateway, Tekos content in the answer, then the read-only check `platform/testing/a2a_delegation_check.py` (cc) and the refusal checks of `evaluations/common/delegation_checks.py` on the gateway.
3. The cost of an Arkos turn that delegates (the traces carry no token counts: use the ai-gateway counters).
4. Then WP-174 Done and ADR-0401, ADR-0403, ADR-0406 to Implemented.
