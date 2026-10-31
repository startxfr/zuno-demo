# WP-173: UnifAI A2A identity, server and approval (specification for the fork)

- **State:** Not started
- **ADRs:** [ADR-0402](../../adr/0402-adopt-a2a-as-the-inter-agent-protocol.md), [ADR-0403](../../adr/0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md), [ADR-0406](../../adr/0406-limit-agent-delegation-by-depth-cycle-and-budget.md), [ADR-0409](../../adr/0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md)
- **Depends on:** [WP-170](wp-170-agent-delegation-contract-and-adrs.md)
- **Related:** [WP-146](wp-146-unifai-identity-and-context-header-forwarding.md), [WP-150](wp-150-unifai-operator-okf-agent-bundles.md)
- **Target:** v0.11
- **Estimated files touched:** in the UnifAI fork only (`multi-agent/lib/mas` A2A node, provider and a new A2A server, HITL, `unifai-operator` bundle and admission); none in `zuno-demo`

> The fork belongs to the session that maintains it; priority and scope are the user's decision. This brief is
> a specification, not an instruction to start. Reframed on 2026-10-24 with that session: a CEL rule cannot read the
> free-form blueprint, so the refusal of hand-added A2A nodes happens at reconcile time, not at admission.

## Goal

An agent can delegate to another over A2A as the initiating user, within the limits and the approval contract.

## Steps

1. **A2A client identity.** `forward_user_token` on the A2A node and provider, headers templated like MCP
   (reuse `IdentityForwarder` and `render_header_templates`); treat `IdentityTokenUnavailable` as a fail-closed
   refusal, not a crash; send `X-Zuno-Delegated-By` and `X-Zuno-Delegation-Depth` rendered by the platform.
2. **Classification.** Send the run's current `X-Zuno-Data-Classification` on the A2A request; the server starts the target run at the higher of that and its own default; the client raises the delegator's run to at least the result's level (monotone, ADR-0565). Tested on both sides, since the mcp-gateway cannot see the delegator's run.
3. **Limits.** Hop counter and cycle detection in the A2A metadata; `cancel_task` when the wait ends; a span per A2A
   call tied to the node span and `X-Zuno-Run-Id`.
4. **A2A server.** Agent card and task endpoint per agent; validate the Keycloak JWT of realm `zuno`; run the
   workflow as the caller through the identity binding; reject a missing or invalid chain.
5. **Approval.** Map `input-required` and `auth-required` to the local `approval_required` event on the originating
   user's session; persist the pending approval with its checkpoint; cover the A2A node in the approval policy;
   an auto-approve override never crosses a hop.
6. **Operator.** Refuse `zuno.delegation.targets` in `UnifaiAgentBundle` until this ships (`Valid=False`, nothing
   emitted); put in Error at reconcile a workflow whose blueprint contains an `a2a_agent_node`; remove
   `a2a_agent_node` from the `UnifaiAgent.spec.type` enum (CEL) for standalone A2A agents; optionally stop listing the
   A2A element. After delivery, map declared targets to A2A nodes.

## Acceptance

A user-authored workflow with an A2A node is refused until enabled; with it enabled, a declared delegation runs as the user,
shows its chain in the trace, stops at the depth limit and at a cycle, and an approval raised by the target reaches the
user and survives a worker restart.

## Progress (2026-10-24)

Step 6 is delivered (UnifAI fork, operator 0.1.35, live on demo333; the fork's roadmap item R-507): an `UnifaiAgent` of type
`a2a_agent_node` is refused at admission and one stored earlier goes to Error; a workflow or template holding an
`a2a_agent_node`, inline or through an expanded `$ref`, goes to Error before any UnifAI call; a bundle declaring
`zuno.delegation.targets` is `Valid=False`, reason `DelegationUnsupported`, nothing emitted; the embedded OKF v0.3 schema is
synced with zuno-demo-agents `51b9e92`, so the delegation fields pass schema validation and then hit that explicit refusal.
Hiding the A2A element from the UnifAI catalog was decided against by the user.

**Consequence for zuno-demo:** an agent that declares a delegation target is not deployed by this operator until
steps 1 to 5 land and the refusal is lifted. Declaring Tekos -> Arkos in the agents repository before that would take Tekos
off demo333. The declaration is therefore the last step of [WP-174](wp-174-tekos-to-arkos-delegation-on-demo333.md),
not a preparation for it.

Steps 1 to 5 (client identity, classification, limits, A2A server, approval) wait for the user's priority.

## Progress (2026-10-31): the short path through the zuno a2a-gateway

Delivered in the fork (operator 0.1.43, live on demo333): a bundle declaring
`zuno.delegation.targets` is no longer refused when the stack enables delegation (`spec.delegation`, unset on
`zuno-unifai` today). The operator emits an orchestrator and, per target, an `a2a_agent_node` whose `base_url` is the
zuno a2a-gateway (`/agents/<target>`, [WP-175](wp-175-a2a-gateway-and-persona-test-blueprints.md)), with
`auth_method: forward_user_token` and the headers `X-Zuno-Delegated-By: <agent>:<task>`, `X-Zuno-Delegation-Depth: 1`,
`X-Zuno-Task: <target task>` and `X-Zuno-Run-Id: {session_id}`; a free-form A2A workflow stays refused. Step 1 is
covered by the fork's A2A node (`forward_user_token`) and step 4 by the zuno gateway instead of a server in the fork; steps 2, 3 and 5
(classification return, hop counter and cancel, approval across hops) are not delivered.

What the gateway checks on these calls (component tests, no live traffic yet): the user's token and the target's
entitlement, the chain headers against the signed declarations (depth, cycle, declared target, active agents), and the
`X-Zuno-Task` and `X-Zuno-Run-Id` the operator sends (the gateway reads the task from the header when the message names
none, and keeps the run id for tracing only when it is a plain token).

Not proven: a live delegated call carrying a real user token through the operator-emitted workflow. It needs
`spec.delegation` enabled on `zuno-unifai` through GitOps (the user's approval) and the full operator canary 0.1.44. Until
then no delegation traffic flows.

## Added when ADR-0409 and ADR-0406 were accepted (2026-10-24)

- **Per-target delegated writes.** With the approval, replace `delegation.allow_write` by `delegation.write_allowed: [{agent, task}]` in
  `policies/limits/limits-policy.yaml` (first entry: Arkos / `draft-architecture-testimonial`), the gateway check in
  `components/mcp-gateway/app/policy.py` and `agent_chain.py`, and a test per case, all in the same corp release as the approval.
- **Approving the delegation itself** is a per-agent option, off by default, in the approval policy of the A2A node.
- **A run with no identity binding cannot write** through a delegation (no approver).
- Acceptance: an approval survives a restart of the worker or the API and expires after 300 seconds (a silence is a refusal); an
  auto-approval set for another run does not cross the hop.

## Related work (2026-10-24)

[WP-175](wp-175-a2a-gateway-and-persona-test-blueprints.md) delivers step 1's first half (`forward_user_token` on the A2A node, fork commit
`178cbd52b`) and a zuno-side A2A gateway ([ADR-0585](../../adr/0585-serve-zuno-agents-over-a2a-from-a-gateway-answering-with-the-callers-identity.md))
for calls a user makes directly. It does not render `X-Zuno-Delegated-By` / `X-Zuno-Delegation-Depth`, does not raise approvals and does not
lift the operator refusal of step 6: the rest of this work package is unchanged, and the fork's own server of step 4 stays specified.
