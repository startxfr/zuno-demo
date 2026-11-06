# WP-174: Arkos to Tekos delegation on demo333 (the file keeps its first name; direction reversed 2026-11-01)

- **State:** Done (2026-11-06)
- **ADRs:** [ADR-0401](../../adr/0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0403](../../adr/0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md), [ADR-0406](../../adr/0406-limit-agent-delegation-by-depth-cycle-and-budget.md), [ADR-0409](../../adr/0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md)
- **Depends on:** [WP-171](wp-171-okf-delegation-fields-and-conformance-cases.md), [WP-172](wp-172-gateway-enforcement-of-the-delegation-chain.md), [WP-173](wp-173-unifai-a2a-identity-server-and-approval.md)
- **Related:** [WP-154](wp-154-tekos-pilot-on-demo333.md), [WP-169](wp-169-dedicated-evaluation-personas.md)
- **Target:** v0.11
- **Estimated files touched:** ~4 in `zuno-demo-agents` (Arkos delegation block, tests), ~6 in `zuno-demo` (evaluation scenarios, a gate check)

## Goal

Enable the first delegation, Arkos to Tekos (`answer-technical-question`), and prove it, and every refusal,
on the live cluster as the `eval-*` personas.

## Steps

1. Arkos declares Tekos / `answer-technical-question` as its only target (an agents release, promoted; declared on agents `devel` at `10f1bd9`, not released). **Not before the operator supports it**: 0.1.35 and 0.1.42 put any bundle declaring `zuno.delegation.targets` in `Valid=False` (`DelegationUnsupported`), and 0.1.43 still refuses the `plan_draft_write` shape Arkos uses (0.1.44), so an earlier release would take Arkos off the cluster. The platform side needs `spec.delegation` and `spec.ceilings.delegationTargets: ["tekos/answer-technical-question"]` on the zuno-unifai CR, and the a2a-gateway must read `X-Zuno-Task` (the operator's A2A node sends it). The gateway-level checks stay skipped until then, which is the intended state.
2. The gateway-level scenarios are written (`evaluations/common/delegation_checks.py`, wired into `evaluations/arkos/security_checks.py`, shipped in both Jobs' ConfigMaps, 17 unit tests): they skip until the admitted release declares Arkos -> Tekos. Add the behavioural ones once WP-173 exists. Evaluation scenarios as `eval-*` personas: the delegation runs; refused when the user lacks `agent_tekos`; refused for an
   undeclared target; refused at depth 2; refused on a cycle; a delegated write refused while `delegation.allow_write` is false;
   the chain appears in the trace and the gateway audit.
3. When WP-173 delivers end-to-end approval, validate a delegated write with the user's approval and across a worker
   restart, then flip `delegation.allow_write` in the corp policy.

## Prerequisites (decided when ADR-0403 was accepted, 2026-10-24)

Before Arkos declares any target: WP-146 step 6 is closed (who may author the `X-Zuno-*` templates in UnifAI) and `JWT_AUDIENCE` is enforced on the
gateways. WP-173 must have lifted the operator's refusal of delegation targets, and the per-target write list must be released.

## Acceptance

All scenarios pass on demo333 (the user powers it on); the negative tests prove the identity boundary; nothing else changes
for agents that declare no target.

## Live proofs that make the ADRs `Implemented` (2026-10-24)

- **Classification on return (ADR-0401):** an Arkos run is already C3, so a result from Tekos (C1, or C2 when it draws on Confluence) joins a C3 context and the local-only rules keep applying; Tekos itself is never raised.
- **Chain and refusals (ADR-0401, ADR-0403):** the audit line and the trace carry `sub`, `delegated_by`, `delegation_depth`; unentitled user, undeclared
  target, depth 2 and a cycle are refused.
- **Limits (ADR-0406):** the cost lands on the initiating user; a delegation that is no longer awaited cancels the remote task; the number of calls per
  turn is read from real traces to confirm the indirect bound (or trigger a cap).
- **Approval (ADR-0409):** an approval reaches the user who started the chain, survives a worker restart, expires after 300 seconds, and a write to a
  target absent from `delegation.write_allowed` is refused.

## Note (2026-10-24)

Update (2026-10-31): the operator now emits the delegation through the zuno a2a-gateway ([WP-173](wp-173-unifai-a2a-identity-server-and-approval.md), short path), so
[WP-175](wp-175-a2a-gateway-and-persona-test-blueprints.md)'s gateway does serve this work package once `spec.delegation` is enabled: it receives the
chain headers the operator renders, verifies them against the signed declarations and answers as the user. A persona test blueprint still carries no chain
(it is not an agent of the release). The live proofs above are still to run.

## Progress (2026-10-31): chart ready, nothing enabled

The `unifai` chart renders `delegation` per bundle (`okf.bundles[].delegation`, with `ceilings.delegationTargets` already passed through) only when set; no bundle sets it today, so the rendered objects are unchanged. Enabling it for Tekos -> Arkos stays a separate GitOps change that needs the user's approval, operator 0.1.44 and its canary.

## Progress (2026-10-31): operators rolled

Operators 0.1.42, 0.1.43, 0.1.44, 0.1.45 and 0.1.47 are live on demo333 (catalog pins by digest, each verified with its release identity and the admission preflight; 0.1.46 was never released). The delegation fields on `zuno-unifai` came from a separate commit and are applied. The application images move once, with the query prefix, as described in [operations](../../platform/operations.md#rolling-a-unifai-release-and-taking-over-a-roll-wp-176-wp-178).

## Progress (2026-11-02)

Wiring is live on demo333 (agents v0.8.0 admitted, bundles repinned, operator 0.1.49 fixing the node uid); the behavioural proof waits for the GPU models. See [the evidence](../evidence/wp-174-arkos-to-tekos-delegation-2026-11-02.md).

## Progress (2026-11-03): the delegation works

Operator 0.1.53 (catalog pin `90146463`; R-528 and a cap of 3 delegations per work item) and the application images
`devel-8c86d4f19` (`a2cbb665`) are live on demo333. As `eval-consultant-01`:
- Scenario 21 passed 3 of 3, with 3, 2 and 1 A2A messages and a non-empty reply carrying the Tekos content each time.
- The Arkos suite passed 18 of 18.
- `a2a_delegation_check.py`: 9 x 200, 0 x 404.
- The mcp-gateway audit carries `delegated_by`.

[The evidence](../evidence/wp-174-arkos-to-tekos-delegation-2026-11-02.md#operator-0152-and-0153-on-demo333-2026-11-03)
has the traces. [WP-172](wp-172-gateway-enforcement-of-the-delegation-chain.md) is Done.

Proofs made, against the list above:

| Proof | ADR | State |
|---|---|---|
| The chain in the audit line and the trace (`sub`, `delegated_by`, depth) | 0401, 0403 | made |
| The number of calls per turn read from real traces; the cap was needed and fired | 0406 | made |
| Classification on return: Tekos results join Arkos's C3 run | 0401 | made 2026-11-06: the gateway returns `zuno.classification` (C1, C3 when raised) |
| Refusals: unentitled user, undeclared target, depth 2, cycle, half a chain, depth header mismatch, read-only delegated surface (`evaluations/arkos/security_checks.py`) | 0401, 0403, 0406 | made: 7 of 7 hold on 0.1.53 |
| The cost lands on the initiating user; the cost of one delegating turn | 0406 | made: one scenario 21 turn as `eval-consultant-01` at the cap of 3 costs about 65,000 tokens and 24 calls: Arkos ~58,000 tokens in 16 calls, Tekos ~6,600 in 8 (all local gpt-oss-20b). The ai-gateway counters count each call once per Keycloak group of the caller (13 for this persona), so the raw sums first read were 13 times too high (`e9a67d3c`; the Tempo trace has 9 Arkos chat spans where the counters said 117 calls). No cost problem remains |
| A delegation no longer awaited cancels the remote task | 0406 | made on UnifAI 0.1.57: with `timeoutSeconds: 1`, `a2a.timeout` then `a2a.task_cancelled`, span `mas.a2a_cancel=cancelled`, trace `54ebccfa482247d3ae41280e1dab4424` ([evidence](../evidence/wp-174-arkos-to-tekos-delegation-2026-11-02.md#unifai-v0157-on-demo333-the-cancel-on-timeout-is-proven-2026-11-04)). A user abort is not covered, by the decision of 2026-11-04 |
| `X-Zuno-Max-Tokens` end to end | 0406 | made on v0.1.55: the model spans carry `mas.x_zuno_max_tokens=8192`, the declared value, and the ai-gateway cuts at the header (64 gives 64) |
| Approval (ADR-0409) | 0409 | gateway side live (agents v0.14.1, gateways build 10/41); waits for UnifAI 0.1.61 and `approval: ask` |

The refusal checks were replayed as `eval-consultant-01` on 0.1.53. Three of them (undeclared target, depth limit, cycle)
first failed with status 200, although the gateway was right. On `/mcp`, a refused chain gets `tools/list` 200 with an
EMPTY tool list, and its `tools/call` answers "denied: ... (ADR-0401)" or "denied: ... (ADR-0406)". The checks now count
an empty surface as a refusal (`bde97594`). With that fix, all 7 hold. The legitimate chain lists 6 read tools.

`unifai_forwards_identity_to_the_gateways` failed on this operator for a reason unrelated to the chain. The orchestrator
now only calls `workplan.*` and `iem.delegate_task`, and the MCP calls come from the worker, so the check never saw
them. Since `1261ebf1`, the check accepts the mcp-gateway trace as proof. It has not been rerun live since that change.

**Result:** ADR-0401 and ADR-0403 are `Implemented`. ADR-0406 and this work package stay open on two proofs:
- the cancellation of a delegation no longer awaited;
- `X-Zuno-Max-Tokens` end to end.

The cost of a delegating turn is moderate once the counters are read correctly (see the next section).

A defect unrelated to the delegation was also seen: Tekos calls git-forge `list_repositories` without `provider`,
`owner` and `repo`, which returns a 502.

## Progress (2026-11-03, evening): cost levers and the two last proofs

See [the evidence](../evidence/wp-174-arkos-to-tekos-delegation-2026-11-02.md#cost-levers-git-forge-schema-and-what-the-fork-does-not-do-2026-11-03-evening).
- **Cap at 1** (`MAS_MAX_DELEGATIONS_PER_ITEM=1`, `bf128167`): four scenario 21 turns passed, each with exactly 1 A2A message.
  - Corrected for the counters' 13x group fan-out (`e9a67d3c`):
    - Arkos: 26,000 to 68,000 tokens in 9 to 16 calls;
    - Tekos: about 2,000 tokens in 2 to 4 calls;
    - a turn with no delegation: about 24,000 tokens in 8 calls.
    The cap of 1 saves about 4,500 tokens per turn.
  - The Arkos suite passed 17 of 18 at the cap of 1. Scenario 10 is flaky, and the cap's effect on it is not shown.
- **Counter defect**: the ai-gateway adds each model call, its tokens and its cost once per Keycloak group of the caller
  (`components/ai-gateway/app/telemetry.py`, three `for g in group_list` loops). Any sum over a user or an agent is
  multiplied by the number of groups. Fixed the same night (`cc000ec3`, build `ai-gateway-40`): these metrics take one
  point per call, and the group panels read `zuno_model_calls_by_group_total` and `zuno_model_tokens_by_group_total`.
  Live control: 3 calls by consultant-02, who holds 10 groups, counted 3 calls and 87 tokens.
- **git-forge**: the 502s came from `tools/list` advertising an open schema. The mcp-gateway now advertises the backend's
  schema (`8625492f`, `4c6bef54`, verified on `tools/list`). No real Tekos call through the new schema has been seen yet.
- **Still open, both waiting for operator 0.1.55**: the cancellation of a delegation no longer awaited (not implemented
  in the UnifAI client) and `X-Zuno-Max-Tokens` end to end. ADR-0406 stays `Accepted`, and approval (ADR-0409) still
  waits for WP-173.

## Progress (2026-11-04): UnifAI v0.1.55

See [the evidence](../evidence/wp-174-arkos-to-tekos-delegation-2026-11-02.md#unifai-v0155-on-demo333-2026-11-04).
- `X-Zuno-Max-Tokens` is proven end to end: the value reaches the model spans, and the ai-gateway enforces it.
- The cancellation of an abandoned delegation is still not proven. The A2A send is a single blocking call, so the poll
  timeout that would cancel the task is never reached. The fix (a non-blocking send, then a cancel on poll timeout)
  ships in 0.1.57.
- Still open: that cancellation (ADR-0406 stays `Accepted` on it alone), approval (ADR-0409, waits for WP-173), the
  intermittent empty final reply after a delegation (fix planned in 0.1.56), and turns where Arkos answers without
  delegating.

## Progress (2026-11-04): UnifAI v0.1.57

See [the evidence](../evidence/wp-174-arkos-to-tekos-delegation-2026-11-02.md#unifai-v0157-on-demo333-the-cancel-on-timeout-is-proven-2026-11-04).
- The cancellation of an abandoned delegation is proven (ADR-0406 is `Implemented`); the A2A send is non-blocking when `timeoutSeconds` is set.
- Still open: approval (ADR-0409, waits for WP-173), the intermittent empty final reply after a delegation (fix R-531 in 0.1.56 and 0.1.57, not yet re-measured), and turns where Arkos answers without delegating.

## Progress (2026-11-06): UnifAI v0.1.60 and agents v0.14.1 on demo333

- **Pinned and rolled:** UnifAI v0.1.60 (catalog `1df1594c`, five images) and agents v0.14.1 (`okf-corp@sha256:7b8319c8`); the mcp-gateway and
  the a2a-gateway re-read the release at pod start and the a2a-gateway holds `delegation.write_allowed`. That entry was Arkos / `draft-architecture-testimonial`, which no delegation can reach; it is
  replaced by Tekos / `answer-technical-question` (whose `aap.cluster.audit` is the write tool) in the next agents release ([ADR-0409](../../adr/0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md) amendment).
- **Cancel, end to end (R-529):** `user.session.submit`, then `session.cancel` 2 s after the agent-card GET: the worker logs `a2a.task_cancelled`
  with the task id, `tasks/get` answers `canceled`, and the span `mas.node A2A: Tekos` carries `mas.a2a_interrupted=true`, `mas.a2a_task_id` and
  `mas.a2a_cancel=cancelled` (Tempo, session `bbce89d0`).
- **Classification on return (ADR-0403 clause 5):** the gateway returns `zuno.classification` on the completed task, C1 by default and C3 when the
  caller raises it (live, both pass).
- **Gateway cancel log:** the `tasks/cancel agent=... task_id=... caller=...` line was not visible because the `a2a_gateway` logger had no handler;
  the gateway now configures it (`configure_logging`), live with the next gateway build.
- **Arkos not delegating:** on the plain scenario 21 prompt Arkos answered "I will reach out to the technical consultant" without any tool call on 3 of 4
  turns; the emitted blueprint still holds the `a2a-tekos` node, and a directive prompt delegates. This looks like model behaviour, not 0.1.60.
- **Acceptance amended (same decision as [WP-173](wp-173-unifai-a2a-identity-server-and-approval.md), 2026-11-05):** the approval proof no longer
  requires surviving a worker restart (a pending approval is lost with the worker and ends as a refusal after 300 s; persistence comes in a later
  version).
- **Approval round trip, live (ADR-0409, 2026-11-06, UnifAI 0.1.61, agents v0.14.2, a2a-gateway build 11, `approval: ask` on Arkos):**
  as `eval-consultant-01`, Arkos asked Tekos for a cluster audit. The session's HITL stream (`session.subscribe`) carried
  `approval_required` about 10 s after the submit (`tool_name` `aap.cluster.audit`, `tool_access_mode` `write`, arguments redacted).
  - **approve** (`POST session.approval`): the gateway logged `approval answered ... decision=approve` and the write reached the
    mcp-gateway at once (exactly one `aap.cluster.audit` call in 30 minutes).
  - **reject:** the gateway logged `decision=reject`, the mcp-gateway received no call, and the session completed.
  - **silence:** after 330 s without an answer the request was refused and nothing reached the mcp-gateway; Arkos then delegated again and
    asked again every five minutes until the session was cancelled (b9: the cap of 5 is per delegation, a per-session cap is a product decision).
  - **R-537:** `unifai-rag-celery` rolled with the old and the new pod alive together, without scaling to 0.
- **The write, once the AAP template was clean (2026-11-06, 16:12):** the first approved write failed downstream, unrelated to the approval: AAP
  answered 400 on the launch of Job Template `zuno-day0-check` (`'env' value missing`), because the template carried a required Survey
  question `env` that is in no repository file and that the playbook does not use. The Survey was switched off (it already was, a minute
  earlier, by another actor) and the same round trip then ran end to end: approve, then AAP job 1329 (`zuno-day0-check`, launch type
  `manual`) started at 16:12:36, seconds after the answer, and the session completed. The original Survey spec is kept in
  `/var/tmp/aap_template16_original.json` on the operator's machine (question `env`, text, default `dev`, required).
- **Closure decision (2026-11-06):** this work package is `Done`. The one proof not replayed live, the refusal of a delegated write to a
  target absent from `delegation.write_allowed`, is accepted as covered by the mcp-gateway and a2a-gateway unit tests, because no second
  write-capable target exists to replay it against. [ADR-0409](../../adr/0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md)
  stays `Accepted` until its remaining proofs are made.
