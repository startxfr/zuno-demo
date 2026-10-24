# ADR-0409: Introduce human approval for delegated operations, resumable from persisted checkpoints

- **Status:** Accepted (2026-10-24) - the decisions below are settled; it becomes `Implemented` once the proofs of "Before Implemented" are made live (WP-173, WP-174)
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
5. **Until this works, writes are refused; afterwards, only for listed targets.** The corp boolean
   `delegation.allow_write` stays `false` ([ADR-0406](0406-limit-agent-delegation-by-depth-cycle-and-budget.md)
   clause 5) until the end-to-end path is validated on demo333. When approval ships, the boolean is replaced by a list in
   `policies/limits/limits-policy.yaml`, `delegation.write_allowed: [{agent, task}]`: a write tool is allowed on a
   delegated call only when the target `agent/task` is on it. The first entry is Arkos / `draft-architecture-testimonial`
   (it carries `git.file.write` and `git.repository.create`); every later target stays read-only until reviewed and
   listed. The list, its gateway check and its test ship in the same corp release as the approval (WP-173).
6. **No approver, no write.** A run with no identity binding (a scheduled or internal run, ADR-0563) has nobody to ask;
   a delegated write in it is refused, never auto-approved.

## Decisions of 2026-10-24

Taken with the user while closing this record:

- **Writes are lifted per target,** through the list of clause 5, not by one global flag. Rejected: keeping the single
  boolean, which would open every future target with the first write.
- **Durability: a pending approval survives a restart of the worker or the API** (clause 3). Rejected: surviving the loss
  of Redis or a cluster shutdown, a durable-storage project in the fork for an approval that lasts hours or days, which
  the demo never produces (an approval is given in minutes, and the user's session does not survive demo333 being
  powered off anyway).
- **Expiry: 300 seconds, then rejection,** as today. A silence is a refusal, never an approval. Rejected: a longer
  delay for delegations (15 minutes), which keeps a write request open and lengthens the delegating agent's whole turn.
- **Approving the delegation itself is a per-agent option, off by default** (clause 4). Rejected: always asking
  (every Arkos draft becomes a click path, against the point of delegating) and asking automatically when the target
  carries write tools (a further rule to code and test, for the risk the write approval already covers).

## Before Implemented

On demo333: an approval raised by the target reaches the initiating user on the session that started the chain; it
survives a restart of the worker; a silence for 300 seconds rejects the write; an auto-approval set for another run does
not cross the hop; a delegated write to a target absent from `delegation.write_allowed` is refused by the gateway;
and a run with no identity binding cannot write.

## Alternatives considered

- **Keep delegation read-only permanently:** the safe fallback if the fork work is not delivered;
  rejected as the goal because Arkos's drafts and similar tasks are writes.
- **Approve at the delegator and trust the target:** rejected; the person approving would not see
  the tool call that is actually made.

## Consequences

The work is in the UnifAI fork (WP-173): A2A state mapping, a checkpoint store, and the mixin on
the A2A node. zuno-demo owns the policy (the boolean today, the per-target list with the approval), the
gateway check of that list and the validation scenarios.

## Security considerations

Approval is the control that makes a delegated write acceptable. Persisting it removes a window in
which a restart silently drops or auto-resolves a pending decision.
