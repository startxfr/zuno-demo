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
   delegated call only when the target `agent/task` is on it. The first entry is Tekos / `answer-technical-question`
   (it carries `aap.cluster.audit`; see the amendment of 2026-11-06); every later target stays read-only until reviewed and
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

## Amendment (2026-11-05)

Decided with the user. Clause 3 ("Approvals survive a restart") is **deferred**: the approval of WP-173 step 5 ships first
**without persistence**. A pending approval is held by the worker that raised it; a restart of the worker loses it, and it
expires as a refusal after 300 seconds, as today (a silence is a refusal, so the loss fails closed). Clauses 1, 2, 4, 5 and 6
are unchanged.

- **Before Implemented:** the proof "it survives a restart of the worker" is removed from this ADR's gate and moves to the
  later version that adds the checkpoint store. Every other proof of the list still applies.
- **Order of the fork work (R-535):** 1 identity, 3 limits, 2 classification, 5 approval. Each step goes into a weekly
  release; the steps that change A2A behaviour get a canary on demo333.

### Gateway contract of the approval (2026-11-05)

Agreed with the fork (R-535) and implemented in `components/a2a-gateway` and `components/mcp-gateway`:

- **Request.** On a delegated call to a target listed in `delegation.write_allowed`, a call of a write tool stops the turn at the
  task state `input-required`, with `status.message.metadata["zuno.approval"] = {request_id, operation, args, reasoning}`
  (`args` is a redacted summary: sensitive keys are masked, long values cut).
- **Answer.** A message on the same `task_id` and `context_id` with a data part
  `{"zuno.approval": {request_id, decision, feedback}}`. The gateway serves `approve` and `reject`; any other decision
  (`modify`, `redirect`) counts as a refusal. Only the caller who started the task may answer.
- **Silence is a refusal.** The state needed to go on is held in the gateway's memory for 300 seconds. An answer that comes later,
  or after a restart, finds nothing to resume: the task fails and the write never runs. Until an answer arrives the task stays in
  `input-required`. (The A2A SDK ends a turn at `input-required`, so no thread waits.)
- **Both gateways check the list.** The a2a-gateway offers write tools to the model only for a listed target; the mcp-gateway
  refuses a delegated write unless the executing `agent/task` is listed. `delegation.allow_write` stays honoured as the legacy
  global switch, off by default. The list itself is in the corp policy of the agents release (`policies/limits/limits-policy.yaml`)
  and is there (agents v0.14.1 carried an Arkos entry, replaced by Tekos / `answer-technical-question` on 2026-11-06).

## Amendment 2026-11-06: the write target is Tekos, not Arkos

The first `delegation.write_allowed` entry named Arkos / `draft-architecture-testimonial`, from the first direction of
[WP-174](../roadmap/work-packages/wp-174-tekos-to-arkos-delegation-on-demo333.md) (Tekos asks Arkos). The direction was reversed on
2026-11-01: Arkos asks Tekos, Tekos declares no target, and nothing delegates to Arkos, so that entry could never be reached
(found while preparing the live proof, after agents v0.14.1). The list holds the *target* of a delegation, so it now holds Tekos /
`answer-technical-question`, whose `aap.cluster.audit` (`access: write`, a Day 0 health check run through AAP) is the only write tool a
delegation can reach today. `approval: ask` goes on the delegating bundle, Arkos, as `spec.delegation.approval` (operator 0.1.61 or later).
The Arkos entry is removed rather than kept dormant: a safety list should hold nothing that cannot fire.

## Progress 2026-11-06: the approval round trip is proven live

On demo333 (UnifAI 0.1.61, agents v0.14.2, `approval: ask` on Arkos), an approval raised by Tekos reached the initiating user on the
session that started the chain (`approval_required`, about 10 s), an approve let the write reach the mcp-gateway (one call), a reject
and a silence of 300 s ran no write, and the session's auto-approval rules were not used. Still to show before `Implemented`: a live
refusal of a delegated write to a target absent from `delegation.write_allowed`, that an auto-approval set for another run does not
cross the hop, and that a run with no identity binding cannot write. See the evidence in
[WP-174](../roadmap/work-packages/wp-174-tekos-to-arkos-delegation-on-demo333.md).

The proof that an auto-approval does not cross the hop could not be made on UnifAI 0.1.61: a session rule (`session.approval.rule`,
`approve_all`) is saved but never reaches a session run by the Temporal worker, whose gate is built without the session metadata and
logs `approve_all: False` (fork R-539, fix planned in 0.1.62). It is to be replayed once after 0.1.62 is pinned.

Replayed on 2026-11-06 after UnifAI 0.1.62 was pinned on demo333 (catalog `sha256:b8586c96…`, five images, operator CSV 0.1.62): with a session
`approve_all` rule set before the prompt, the Temporal worker now logs `approve_all: True` for the session, and the delegated write
(`aap.cluster.audit`, `write`) still raised an `approval_required` that waited for a human answer (the a2a-gateway logged `approval requested`
then `approval answered decision=reject`, nothing ran). An auto-approval therefore does not cross the hop. The proof script is
`evaluations/arkos/approval_proof.py reject --rule`.

The per-session cap of 3 approval requests (fork R-538, UnifAI 0.1.62) could not be reached live: in three runs on 2026-11-07 (one prompt per
turn, a resubmit in the same session, one prompt asking for four delegations) Arkos stopped after the first refusal and the session completed,
so no 4th request was raised. The cap is accepted as covered by the upstream tests; the gateway side needs no counter of its own.

The "no identity binding" case is covered by gateway tests (2026-11-06): an anonymous or forged token is refused with 401 before the model or any tool
is reached, a forged token cannot answer a pending approval (the write stays unrun and the real initiating user can still answer), and a token
without a `sub` claim is refused. The write path needs a caller identity at every step, so no run without one can approve or write.

