# WP-174: Arkos to Tekos delegation on demo333 (the file keeps its first name; direction reversed 2026-11-01)

- **State:** Not started
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
