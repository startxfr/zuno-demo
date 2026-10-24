# ADR-0406: Limit agent delegation by depth, cycle and budget

- **Status:** Accepted (2026-10-24) - the decisions below are settled; it becomes `Implemented` once the proofs of "Before Implemented" are made live (WP-174)
- **Target:** v0.11
- **Date:** 2026-10-24
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0401](0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0403](0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md), [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md), [ADR-0579](0579-extend-okf-to-v0-3-with-skills-model-roles-guardrails-and-limits.md)

## Context

The stub (2026-08-13): "Prevent loops and runaway cost through hop/depth and policy
limits." ADR-0511 already says ADR-0406 will limit agent-to-agent recursion, not human usage.

The UnifAI fork limits each agent locally (steps, rounds, a 4-hour workflow timeout)
but has no delegation depth, no cycle detection across A2A hops (A to B to A runs until
timeouts), no per-delegated-call budget, and its A2A wait gives up after about 30
seconds without cancelling the remote task. ADR-0511 attributes quota to the user
(JWT `sub`), groups and project; a delegated call carries the user's token, so it
already counts for that user.

## Decision

1. **Depth.** The default depth is 1: A may call B, B may not call anyone. An agent may
   raise it with `zuno.limits.delegation.max_depth` (integer, at least 1), never above the
   corp ceiling `max_delegation_depth` in `policies/limits/limits-policy.yaml`, whose initial
   value is 2. The OKF narrowing rule (ADR-0579) refuses a bundle above the ceiling.
2. **Cycle.** A chain that contains the same agent twice is refused, whatever the depth.
3. **Budget.** A delegated call is charged to the initiating user's quota (ADR-0511), with
   no new dimension and no per-agent budget. The chain is added to the audit and the spans
   (ADR-0403) so a cost can be traced to the delegation that caused it.
4. **Time.** The A2A client cancels the remote task when it stops waiting (`cancel_task`),
   so a timed-out delegation does not keep running and spending; the wait bound is the
   delegating task's own timeout.
5. **Writes.** Until human approval works across a delegation
   ([ADR-0409](0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md)),
   the gateway refuses, on a delegated call, every tool whose `tool-policy.yaml` entry does not say `access: read`.
   `access` is `read` or `write` on every tool; an entry that omits it is a `write` tool (fail closed). Today the
   switch is the corp boolean `delegation.allow_write` (default `false`, release 0.4.1). It is **transitional**:
   when approval ships it is replaced by a per-target list (ADR-0409 clause 5), so that lifting the restriction for
   one delegation never lifts it for the next.

## What bounds the breadth

Depth limits the chain vertically, not the number of calls one agent makes in a turn: Tekos may call Arkos several
times. No explicit cap exists, and none is added now. The bound is indirect and known: the delegating agent's own loop
limits (about 10 steps for a ReAct agent, up to 15 to 20 rounds for the custom and orchestrator agents) and the user's
daily token budget (3 M tokens for the standard class, ADR-0511), which a delegated call draws on like a direct one.
Revisit with a `limits.delegation.max_calls_per_run` field if demo333 shows an agent fanning out; the trigger is
measured, not assumed.

## Decisions of 2026-10-24

Taken with the user while closing this record:

- **Depth: default 1, corp ceiling 2** (clause 1). Rejected: a ceiling of 1 (it forbids a plausible agent that
  delegates to an agent that delegates) and a ceiling of 3 (each hop multiplies the reachable surface and the cost for
  a case no agent asks for).
- **No explicit breadth cap** (above). Rejected for now: `max_calls_per_run`, which adds a schema field (a release and
  the operator's embedded schema) and a counter to maintain before any measurement.
- **The wait is the delegating task's timeout, with `cancel_task`** (clause 4). Rejected: a dedicated corp timeout, whose
  right value depends on how long an Arkos draft really takes, which has not been measured.
- **The cost is the initiating user's** (clause 3). Rejected: a per-agent cap for delegated calls, which breaks the
  one-user-one-budget reading of ADR-0511 and needs a new quota dimension.

## Before Implemented

On demo333: a depth-2 chain and a cycle are refused; a delegated call is charged to the initiating user and traceable to
its chain; a delegation that stops being awaited cancels the remote task; and the number of calls an agent makes in a turn
is read from real traces to confirm the indirect bound or trigger the cap above.

## Alternatives considered

- **Free depth up to a higher ceiling with a budget per agent:** rejected for now. It breaks
  ADR-0511's per-user model and makes counters hard to read.
- **No explicit limits, only timeouts:** rejected; a loop is stopped only when time runs out.

## Consequences

The schema and corp policy gain the two keys; the gateway checks depth and cycle in the same
evaluation as ADR-0403; the fork adds the hop counter and `cancel_task`. No new quota object.

## Security considerations

A bounded chain bounds both the surface a delegation can reach and the cost an agent can
cause on a user's behalf. The boolean write switch is a safe default, not a final policy: ADR-0409 replaces it by a per-target list.
