# ADR-0007: Separate reusable platform components from agent instances

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Five initial agents must become the beginning of a catalog, not five duplicated applications.

## Decision

Maintain shared implementations for frontend, BFF, runtime, AI gateway, MCP gateway, and RAG while instantiating agent-specific deployments/configuration.

## Alternatives considered

Copy each application per agent.

## Consequences

Reduces duplication and makes a sixth agent mostly declarative.

## Security considerations

Shared components increase blast radius and therefore require strong namespace, policy, and regression testing.

## Operational considerations

Version compatibility between shared runtime and agent bundle must be observable.

## Migration / evolution

v1 adds stronger compatibility gates.
