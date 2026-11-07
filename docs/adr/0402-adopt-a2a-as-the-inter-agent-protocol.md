# ADR-0402: Adopt A2A as the inter-agent protocol

- **Status:** Implemented (2026-11-07, WP-173, WP-174: Arkos to Tekos delegation runs over A2A live on demo333, through the zuno a2a-gateway; the fork A2A server was dropped by decision on 2026-11-05)
- **Target:** v0.11
- **Date:** 2026-10-24
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0401](0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0403](0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md)

## Context

The stub (2026-08-13) read: "Use a standard protocol for agent delegation instead
of bespoke point-to-point contracts." Since then the question has been settled by
the platform choice. UnifAI (ADR-0561) ships an A2A client: the `a2a_agent_node` and
`A2AProvider`, built on the `a2a-sdk` (`startx-unifai`,
`multi-agent/lib/mas/elements/nodes/a2a_agent/` and `.../providers/a2a_client/`), and
its operator already lists the node type among those a bundle can map onto.

## Decision

Agent-to-agent delegation uses the A2A protocol, through the `a2a-sdk` that UnifAI
already depends on. No bespoke inter-agent HTTP contract is introduced.

This ADR decides the protocol and nothing else. Who may delegate to whom is
[ADR-0401](0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md);
identity and chain are [ADR-0403](0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md);
limits are [ADR-0406](0406-limit-agent-delegation-by-depth-cycle-and-budget.md).

UnifAI is an A2A client only today: it exposes no agent card and no task endpoint.
Receiving a delegation therefore needs an A2A server in the fork, tracked as WP-173;
until it exists, no delegation runs.

## Alternatives considered

- **A bespoke REST contract between agents:** rejected; the standard exists and the
  platform already uses it.
- **Compose the agents in one workflow with the orchestrator node:** possible for a
  demo, but then B is no longer an independent, separately entitled agent; it does
  not replace delegation between agents.

## Consequences

No code change from this ADR. It fixes the vocabulary the other four rely on.

## Update (2026-10-24)

[ADR-0585](0585-serve-zuno-agents-over-a2a-from-a-gateway-answering-with-the-callers-identity.md) adds a zuno-side A2A gateway
(`components/a2a-gateway`) that serves the active agents of the admitted release. "No delegation runs" above therefore no longer
holds for a call a user makes directly, for instance from a blueprint. A delegation declared in a bundle (`zuno.delegation.targets`)
still waits for WP-173, because the operator refuses it and the platform does not yet render the chain headers.

## Update (2026-11-05)

The A2A server in the fork (WP-173 step 4) is dropped by decision of the user: the zuno a2a-gateway serves the agents, and the
fork stays an A2A client only. "Receiving a delegation therefore needs an A2A server in the fork" above no longer holds. The
delegating run is delivered by the fork's client work (R-535 in the fork's roadmap, WP-173 steps 1 to 3 and 5).

## Update (2026-11-07) - Implemented

The four decisions that rely on this vocabulary are `Implemented`: [ADR-0401](0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0403](0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md),
[ADR-0406](0406-limit-agent-delegation-by-depth-cycle-and-budget.md) and [ADR-0409](0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md). WP-173 and WP-174 are Done: the fork's A2A client delegates, the
zuno a2a-gateway serves the target, and no bespoke inter-agent contract was introduced.
