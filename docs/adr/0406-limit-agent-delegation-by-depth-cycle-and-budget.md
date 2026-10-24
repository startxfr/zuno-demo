# ADR-0406: Limit agent delegation by depth, cycle and budget

- **Status:** Proposed
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
   a corp flag `delegation.allow_write` (default `false`) makes the gateway refuse, on a delegated call, every tool
   whose `tool-policy.yaml` entry does not say `access: read`. `access` is `read` or `write` on every tool; an
   entry that omits it is a `write` tool (fail closed).

## Alternatives considered

- **Free depth up to a higher ceiling with a budget per agent:** rejected for now. It breaks
  ADR-0511's per-user model and makes counters hard to read.
- **No explicit limits, only timeouts:** rejected; a loop is stopped only when time runs out.

## Consequences

The schema and corp policy gain the two keys; the gateway checks depth and cycle in the same
evaluation as ADR-0403; the fork adds the hop counter and `cancel_task`. No new quota object.

## Security considerations

A bounded chain bounds both the surface a delegation can reach and the cost an agent can
cause on a user's behalf. The write flag is a safe default, not a final policy.
