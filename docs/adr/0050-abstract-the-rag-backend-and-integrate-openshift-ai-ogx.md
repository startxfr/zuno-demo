# ADR-0050: Abstract the RAG backend and integrate OpenShift AI OGX

- **Status:** To be implemented
- **Target:** v1
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The custom `rag-service` provides PostgreSQL/pgvector hybrid retrieval and is useful as a controllable MVP implementation. OpenShift AI 3.5 also introduces OGX/RAG capabilities that align with the project objective to demonstrate OpenShift AI components, but those capabilities may have EA/TP lifecycle constraints.

## Decision

Define a stable internal RAG API/provider interface used by Agent Runtime. Keep PostgreSQL/pgvector as the v0 fallback/reference provider and add an OGX-backed provider for OpenShift AI 3.5. Agent definitions select logical collections, not backend-specific APIs.

## Consequences

The platform can demonstrate OGX without making all agent behavior depend on one preview implementation. RAG metadata contracts must remain portable across providers.

## Security considerations

Both providers must enforce classification and ACL filters consistently. Switching provider must not widen accessible data.

## Operational considerations

Create parity tests covering retrieval quality, filtering, citations and classification propagation across pgvector and OGX providers.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Implementation state, Acceptance criteria and Review evidence.

## Related ADRs

- ADR-0015
- ADR-0018
- ADR-0046
