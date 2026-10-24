# WP-170: Agent delegation contract and ADRs

- **State:** Repo work merged
- **ADRs:** [ADR-0401](../../adr/0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0402](../../adr/0402-adopt-a2a-as-the-inter-agent-protocol.md), [ADR-0403](../../adr/0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md), [ADR-0406](../../adr/0406-limit-agent-delegation-by-depth-cycle-and-budget.md), [ADR-0409](../../adr/0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md)
- **Depends on:** none
- **Related:** [WP-171](wp-171-okf-delegation-fields-and-conformance-cases.md), [WP-172](wp-172-gateway-enforcement-of-the-delegation-chain.md), [WP-173](wp-173-unifai-a2a-identity-server-and-approval.md), [WP-174](wp-174-tekos-to-arkos-delegation-on-demo333.md)
- **Target:** v0.11
- **Estimated files touched:** ~12 docs in `zuno-demo` (five ADRs, three amendments, stub, index, tables)

> Decision of 2026-10-24 (user, after the reassessment of ADR-0401 to ADR-0409): write the
> delegation contract first and enable it later, for one demo case. Identity travels as the
> user's JWT plus a declared chain; authorization is the target's own rights intersected with the
> user's, with delegation declared in the delegator's signed OKF; depth is 1 by default under a corp
> ceiling; budget stays the user's; approval is delivered end to end; the target is reached through an
> A2A server added to UnifAI.

## Goal

Replace five v0.4 stubs by records that say who may delegate to whom, with which identity and
which limits, and amend the three ADRs the contract touches (ADR-0011, ADR-0579, ADR-0511).

## Steps

1. Promote ADR-0401, ADR-0402, ADR-0403, ADR-0406 and ADR-0409; retarget to v0.11; update the stub, the
   index, the version tables and the change log. (done)
2. Dated notes on ADR-0011, ADR-0579 and ADR-0511. (done)
3. ADR-0404, ADR-0405, ADR-0407 and ADR-0408 stay stubs with the reassessment table.

## Acceptance

`python3 platform/docs/check_docs.py` passes; each ADR states its alternatives and its residual risk
(ADR-0403); the user accepts or amends the four `Proposed` records.

## Open questions

Whether ADR-0405 (user-facing delegation traces beyond spans) needs its own record once the chain is
audited.
