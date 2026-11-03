# WP-174: Arkos to Tekos delegation on demo333 (the file keeps its first name; direction reversed 2026-11-01)

- **State:** Repo work merged
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
| Classification on return: Tekos results join Arkos's C3 run | 0401 | not checked separately |
| Refusals: unentitled user, undeclared target, depth 2, cycle, half a chain, depth header mismatch, read-only delegated surface (`evaluations/arkos/security_checks.py`) | 0401, 0403, 0406 | made: 7 of 7 hold on 0.1.53 |
| The cost lands on the initiating user; the cost of one delegating turn | 0406 | made: one scenario 21 turn as `eval-consultant-01` cost Arkos 753,363 tokens in 208 calls and Tekos 85,696 tokens in 104 calls (about 839,000 tokens, all local gpt-oss-20b; ai-gateway counters, idle baseline checked, `f4fd6318`). Whether this cost is acceptable or needs a lower ceiling is an open decision, not a missing proof |
| A delegation no longer awaited cancels the remote task | 0406 | not implemented: the UnifAI client never calls `cancel_task` as of 0.1.53, on a timeout, a user abort or a cancelled Temporal run (b9, fork code); fix planned in 0.1.55 |
| `X-Zuno-Max-Tokens` end to end | 0406 | half proven: the ai-gateway enforces the header (64 gives 64 completion tokens, 128 gives 128); the operator sends it on every call, but Arkos declares 8192, so no call reaches it, and the value sent is not logged. A low-ceiling test needs a signed release; a span attribute with the value is offered for 0.1.55 |
| Approval (ADR-0409) | 0409 | waits for WP-173 |

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

The cost of a delegating turn is a decision still open: accept it, or lower the delegation cap or the token ceiling.

A defect unrelated to the delegation was also seen: Tekos calls git-forge `list_repositories` without `provider`,
`owner` and `repo`, which returns a 502.

## Progress (2026-11-03, evening): cost levers and the two last proofs

See [the evidence](../evidence/wp-174-arkos-to-tekos-delegation-2026-11-02.md#cost-levers-git-forge-schema-and-what-the-fork-does-not-do-2026-11-03-evening).
- **Cap at 1** (`MAS_MAX_DELEGATIONS_PER_ITEM=1`, `bf128167`): four scenario 21 turns passed, each with exactly 1 A2A message.
  - Tekos: 25,376 to 34,164 tokens per turn, about a third of its cost at the cap of 3.
  - Arkos: 339,729 to 882,973 tokens, with no measurable change and a high variance.
  - A turn with no delegation costs Arkos 309,231 tokens in 104 calls, so most of the cost is Arkos's own loop, not
    the delegation.
  - The Arkos suite passed 17 of 18 at the cap of 1. Scenario 10 is flaky, and the cap's effect on it is not shown.
  - Keeping the cap at 1, and reducing Arkos's own loop, are decisions still open.
- **git-forge**: the 502s came from `tools/list` advertising an open schema. The mcp-gateway now advertises the backend's
  schema (`8625492f`, `4c6bef54`, verified on `tools/list`). No real Tekos call through the new schema has been seen yet.
- **Still open, both waiting for operator 0.1.55**: the cancellation of a delegation no longer awaited (not implemented
  in the UnifAI client) and `X-Zuno-Max-Tokens` end to end. ADR-0406 stays `Accepted`, and approval (ADR-0409) still
  waits for WP-173.
