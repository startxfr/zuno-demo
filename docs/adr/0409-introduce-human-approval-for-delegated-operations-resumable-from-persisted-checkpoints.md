# ADR-0409: Introduce human approval for delegated operations, resumable from persisted checkpoints

- **Status:** Proposed
- **Target:** v0.11
- **Date:** 2026-10-24
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0401](0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0403](0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md), [ADR-0406](0406-limit-agent-delegation-by-depth-cycle-and-budget.md)

## Context

The stub (2026-08-13): "Pause sensitive operations for explicit approval and resume from
persisted checkpoints."

UnifAI's human-in-the-loop gate (`multi-agent/adapters/outbound/hitl/`, `mas/core/hitl/`)
approves write and destructive tool calls through a channel bound to the local session. It
has three limits that matter here: it does not cover the A2A node, so a delegation is never
gated; a delegated agent's approval request cannot reach the user who started the chain,
because the remote agent is a different system that sees only text; and the wait is a
blocking thread with no checkpoint, so a restart loses a pending approval (the 300-second
timeout then rejects).

## Decision

1. **The approver is the initiating user.** A write or destructive tool call made inside a
   delegation asks the user at the head of the chain, never the delegating agent and never
   an auto-resolving rule set for another run (auto-approve overrides are keyed by run and do
   not cross a hop).
2. **A2A carries the request.** The target's A2A server reports a pending approval as the
   task state `input-required`; the delegating A2A client turns it into the local
   `approval_required` event on the user's session and returns the decision to the target.
   `auth-required` is handled the same way for a missing delegated credential.
3. **Approvals survive a restart.** A pending approval is persisted with its checkpoint
   (request, tool call, state needed to resume), so a restart of the worker or the API resumes
   the wait instead of losing it. The default decision on expiry stays `reject`.
4. **The gate covers the delegation itself where configured.** The A2A node participates in the
   approval policy, so delegating can be made to require approval for a given agent.
5. **Until this works, writes are refused.** The corp flag `delegation.allow_write` stays
   `false` ([ADR-0406](0406-limit-agent-delegation-by-depth-cycle-and-budget.md) clause 5) and
   flips only after the end-to-end path is validated on demo333.

## Alternatives considered

- **Keep delegation read-only permanently:** the safe fallback if the fork work is not delivered;
  rejected as the goal because Arkos's drafts and similar tasks are writes.
- **Approve at the delegator and trust the target:** rejected; the person approving would not see
  the tool call that is actually made.

## Consequences

The work is in the UnifAI fork (WP-173): A2A state mapping, a checkpoint store, and the mixin on
the A2A node. zuno-demo owns only the policy flag and the validation scenarios.

## Security considerations

Approval is the control that makes a delegated write acceptable. Persisting it removes a window in
which a restart silently drops or auto-resolves a pending decision.
