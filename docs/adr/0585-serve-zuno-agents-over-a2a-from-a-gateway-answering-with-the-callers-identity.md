# ADR-0585: Serve zuno agents over A2A from a gateway that answers with the caller's identity

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-24
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0402](0402-adopt-a2a-as-the-inter-agent-protocol.md) (where the A2A server lives), [ADR-0403](0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md), [ADR-0406](0406-limit-agent-delegation-by-depth-cycle-and-budget.md)
- **Related:** [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0571](0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md), [ADR-0583](0583-require-group-visibility-and-object-level-authorisation-before-per-agent-entries.md)

## Context

ADR-0402 chose A2A as the inter-agent protocol and noted that UnifAI is an A2A client
only: receiving a delegation needs an A2A server, which WP-173 specifies inside the
UnifAI fork, running the target workflow as the caller. That work waits for the user's
priority, and until it exists no agent can be delegated to, so nothing exercises the
client, the identity forwarding of ADR-0563 or the delegation limits of ADR-0406 end
to end. The user asked for a real A2A server, built on the RHOAI model path and the
existing zuno gateways, so that every demo persona can try a delegation from a
UnifAI blueprint.

## Decision

1. **A zuno-side A2A gateway.** `components/a2a-gateway` (namespace `zuno-ai-run`)
   serves each active agent of the admitted release as an A2A 0.3 agent over JSON-RPC,
   at `/agents/<agent>/`, with a public card at `/.well-known/agent-card.json`. It is a
   second way to reach an agent, beside the agent's UnifAI workflow; it does not replace
   the fork's server of WP-173, which stays the way to run a UnifAI workflow as the caller.
2. **It answers with zuno's own path.** The agent's task prompt comes from the admitted
   release; the model call goes through the ai-gateway and the tool calls through the
   mcp-gateway, both with the caller's own Keycloak token and the `X-Zuno-Agent`,
   `X-Zuno-Task` and `X-Zuno-Data-Classification` headers. Model routing, guardrails,
   quota and the five-factor tool policy therefore apply to the real user, exactly as for
   a UnifAI turn (ADR-0563, ADR-0571).
3. **Identity and entitlement at the door.** Every task call needs a valid token of realm
   `zuno` with the audience `zuno-admin-api`. A caller without the agent's access group
   (ADR-0040) gets the answer given for an unknown agent (ADR-0583). The card is public
   and shows no group name.
4. **Delegation contract.** The `X-Zuno-Delegated-By` and `X-Zuno-Delegation-Depth`
   headers are verified with the same rules as the mcp-gateway (declared targets, depth
   within the corp ceiling, no cycle, classification only raised, ADR-0401, ADR-0406) and
   passed on unchanged. The gateway never delegates onward.
5. **Client side.** The fork's A2A node accepts `auth_method: forward_user_token`
   (WP-173 step 1), limited to cluster-internal or allow-listed targets, so the token of
   the initiating user reaches the gateway and no stored credential is involved.
6. **Read-only tools.** With no approval across hops, the tool loop offers, and runs, only the tools the
   mcp-gateway lists with `readOnlyHint: true`; a write tool is never reachable through this gateway.
7. **Out of scope.** Approval across hops (ADR-0409) is not implemented: the gateway
   never raises `input-required`. The operator keeps refusing A2A in objects it manages
   (WP-173 step 6); the gateway is reached from blueprints a person builds in the UI.

## Consequences

Two A2A servers may coexist: this gateway answers with zuno policy, the fork's answers with
the UnifAI workflow. An A2A agent here and the UnifAI workflow of the same name can give
different answers (no workflow-level retrieval or memory); the agent card says nothing about
that, the documentation does. If the fork's server ships, agents may move to it and this
gateway becomes a thin test target or is removed.

## Security considerations

The gateway holds no credential of its own and never calls a model or a tool as itself; a bug
in it cannot widen what a user may do, only what it shows of the agent definitions, which the
card limits to the title, the description and the task names. Task state is in memory in one
replica, so a restart loses running tasks. The token is forwarded only to services inside the
cluster.

## Operational considerations

Built and deployed with the `mcp` run component (`make d1 build mcp`, `make d1 install mcp`),
agents and limits from the same admitted release as the mcp-gateway. No change to demo222
before the cutover (ADR-0573).
