# WP-174: Tekos to Arkos delegation on demo333

- **State:** Not started
- **ADRs:** [ADR-0401](../../adr/0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0403](../../adr/0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md), [ADR-0406](../../adr/0406-limit-agent-delegation-by-depth-cycle-and-budget.md), [ADR-0409](../../adr/0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md)
- **Depends on:** [WP-171](wp-171-okf-delegation-fields-and-conformance-cases.md), [WP-172](wp-172-gateway-enforcement-of-the-delegation-chain.md), [WP-173](wp-173-unifai-a2a-identity-server-and-approval.md)
- **Related:** [WP-154](wp-154-tekos-pilot-on-demo333.md), [WP-169](wp-169-dedicated-evaluation-personas.md)
- **Target:** v0.11
- **Estimated files touched:** ~4 in `zuno-demo-agents` (Tekos delegation block, tests), ~6 in `zuno-demo` (evaluation scenarios, a gate check)

## Goal

Enable the first delegation, Tekos to Arkos (`draft-architecture-testimonial`), and prove it, and every refusal,
on the live cluster as the `eval-*` personas.

## Steps

1. Tekos declares Arkos / `draft-architecture-testimonial` as its only target (an agents release, promoted).
2. Evaluation scenarios as `eval-*` personas: the delegation runs; refused when the user lacks `agent_arkos`; refused for an
   undeclared target; refused at depth 2; refused on a cycle; a delegated write refused while `delegation.allow_write` is false;
   the chain appears in the trace and the gateway audit.
3. When WP-173 delivers end-to-end approval, validate a delegated write with the user's approval and across a worker
   restart, then flip `delegation.allow_write` in the corp policy.

## Acceptance

All scenarios pass on demo333 (the user powers it on); the negative tests prove the identity boundary; nothing else changes
for agents that declare no target.
