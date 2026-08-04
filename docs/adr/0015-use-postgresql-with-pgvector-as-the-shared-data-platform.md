# ADR-0015: Use PostgreSQL with pgvector as the shared data platform

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The platform needs commercial relational data, vector search, workflow state, and optionally full-text retrieval.

## Decision

Deploy a dedicated HA PostgreSQL platform in OpenShift and use pgvector for vector data, with logical isolation by agent/domain.

## Alternatives considered

Dedicated vector database product; one database instance per agent.

## Consequences

Reduces platform count and supports hybrid SQL/full-text/vector patterns.

## Security considerations

Database roles and network access must remain least-privilege.

## Operational considerations

HA is required for industrialized target.

## Migration / evolution

Redis may be added for ephemeral caching without replacing PostgreSQL as durable state.
