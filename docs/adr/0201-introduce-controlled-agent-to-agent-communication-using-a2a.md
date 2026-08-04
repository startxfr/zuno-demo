# ADR-0201: Introduce controlled agent-to-agent communication using A2A

- **Status:** Proposed
- **Target:** v2
- **Date:** 2026-08-04

## Context

v0/v1 reuse common tools rather than having Arkos invoke Tekos as an agent, but future catalog interactions need delegation.

## Decision

Adopt a controlled A2A-compatible protocol with identity propagation, policy, budgets, recursion limits, and delegation traces.

## Alternatives considered

Custom RPC between agents; shared tool reuse only forever.

## Consequences

Enables agent composition while containing recursive behavior.

## Security considerations

All delegated calls inherit or further restrict user authorization and classification.

## Operational considerations

A2A calls require new tracing and failure semantics.

## Migration / evolution

Start with narrowly approved delegation relationships.
