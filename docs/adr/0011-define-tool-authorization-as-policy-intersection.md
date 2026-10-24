# ADR-0011: Define tool authorization as policy intersection

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Allow a tool only when agent declaration, task rights, user/group rights, classification and platform policy all permit it.

## Evolution (2026-08-13)

ADR-0203 applies the same least-privilege pattern to RAG/knowledge access. Tool authorization remains a five-factor intersection; knowledge authorization is a separate, analogous intersection and must not be collapsed into tool permissions or frontend visibility.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.

## Amendment (2026-10-24) - a delegated call

[ADR-0403](0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md)
states how the intersection applies when an agent delegates to another: the five
factors apply to the **target** agent and its task alone, for the initiating user
and at the highest classification of the chain; the delegator's own tool rights are
not intersected, because delegating exists so the target can do what the delegator
cannot. What the delegator contributes is the signed declaration of the target
([ADR-0401](0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md)).
