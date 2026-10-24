# WP-175: A2A gateway and persona test blueprints

- **State:** Repo work in review
- **ADRs:** [ADR-0585](../../adr/0585-serve-zuno-agents-over-a2a-from-a-gateway-answering-with-the-callers-identity.md), [ADR-0402](../../adr/0402-adopt-a2a-as-the-inter-agent-protocol.md), [ADR-0403](../../adr/0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md), [ADR-0406](../../adr/0406-limit-agent-delegation-by-depth-cycle-and-budget.md)
- **Depends on:** [WP-172](wp-172-gateway-enforcement-of-the-delegation-chain.md)
- **Related:** [WP-173](wp-173-unifai-a2a-identity-server-and-approval.md), [WP-174](wp-174-tekos-to-arkos-delegation-on-demo333.md)
- **Target:** v0.11
- **Estimated files touched:** ~25 in `zuno-demo` (`components/a2a-gateway`, `gitops/charts/a2a-gateway`, `gitops/apps/a2a-gateway`, the `mcp` and `mcp_build` roles, two network policies, a seeding script) and ~6 in the UnifAI fork (A2A node identity forwarding, already pushed)

> Decision of 2026-10-24 (user): build a real A2A server on the RHOAI model path and the zuno gateways, and give every
> business persona two test blueprints in UnifAI, one of them delegating to an agent over A2A. The server lives in
> `zuno-demo` (ADR-0585); the fork's own server (WP-173 step 4) stays specified.

## Goal

Each of the 17 business personas owns `test-<persona>-chat` and `test-<persona>-a2a` in UnifAI on demo333. The second one
delegates to an agent the persona is entitled to, over A2A, with the persona's own token; a persona asking for an agent it is
not entitled to is refused like an unknown agent.

## Steps

1. **Fork: identity on the A2A node.** `auth_method: forward_user_token` and templated headers (WP-173 step 1), limited to
   cluster-internal targets. Done in the fork (`178cbd52b`).
2. **Component.** `components/a2a-gateway`: one A2A agent per active agent of the admitted release, token validation with the
   `zuno-admin-api` audience, entitlement, delegation-chain checks, model call through the ai-gateway, bounded tool loop through the
   mcp-gateway. Tests drive it with the A2A SDK client UnifAI uses.
3. **Deployment.** Chart, Applications, network policies (ai-gateway and mcp-gateway accept the new pod), build and install under the
   `mcp` run component. Live steps wait for the user's go and for the session that owns `zuno-unifai` to roll the fork image.
4. **Persona blueprints.** `platform/testing/seed_persona_blueprints.py` creates, validates and cleans the 32 blueprints.
5. **Proof.** One turn per persona family on demo333, the entitlement refusals, and the depth limit.

## Acceptance

The tests of the component pass; on demo333 a persona's `test-<persona>-a2a` blueprint validates and answers, the ai-gateway routing
decision and quota are attributed to that persona, and the mcp-gateway tool surface is the agent's.

## Open questions

- Approval across hops (ADR-0409) is not part of this work package.
