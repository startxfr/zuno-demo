# ADR-0026: Provide an AIAgent CRD and operator

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The platform objective is to instantiate future agents declaratively.

## Decision

Create an AIAgent Kubernetes API/operator that reconciles an agent definition into per-agent frontend/BFF/configuration/policy resources and references shared services.

## Alternatives considered

Manual Helm releases per agent; application-specific operators.

## Consequences

Turns agent lifecycle into a platform capability.

## Security considerations

Operator permissions must be narrowly scoped and it must validate bundles before reconciliation.

## Operational considerations

Operator status becomes a key troubleshooting surface.

## Migration / evolution

v3 evolves this into mature self-service onboarding.
