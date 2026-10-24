# ADR-0402: Adopt A2A as the inter-agent protocol

- **Status:** Accepted
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
