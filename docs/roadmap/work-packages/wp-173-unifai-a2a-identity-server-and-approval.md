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
2. **Limits.** Hop counter and cycle detection in the A2A metadata; `cancel_task` when the wait ends; a span per A2A
   call tied to the node span and `X-Zuno-Run-Id`.
3. **A2A server.** Agent card and task endpoint per agent; validate the Keycloak JWT of realm `zuno`; run the
   workflow as the caller through the identity binding; reject a missing or invalid chain.
4. **Approval.** Map `input-required` and `auth-required` to the local `approval_required` event on the originating
   user's session; persist the pending approval with its checkpoint; cover the A2A node in the approval policy;
   an auto-approve override never crosses a hop.
5. **Operator.** Refuse `zuno.delegation.targets` in `UnifaiAgentBundle` until this ships (`Valid=False`, nothing
   emitted); put in Error at reconcile a workflow whose blueprint contains an `a2a_agent_node`; remove
   `a2a_agent_node` from the `UnifaiAgent.spec.type` enum (CEL) for standalone A2A agents; optionally stop listing the
   A2A element. After delivery, map declared targets to A2A nodes.

## Acceptance

A user-authored workflow with an A2A node is refused until enabled; with it enabled, a declared delegation runs as the user,
shows its chain in the trace, stops at the depth limit and at a cycle, and an approval raised by the target reaches the
user and survives a worker restart.
