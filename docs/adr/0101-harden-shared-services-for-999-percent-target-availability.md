# ADR-0101: Harden shared services for 99.9 percent target availability

- **Status:** Proposed
- **Target:** v1
- **Date:** 2026-08-04

## Context

The MVP can tolerate reduced availability, but the industrialized target is 99.9%.

## Decision

Introduce HA and disruption-resilient patterns for shared runtime, gateway, identity, database, and critical model-serving paths.

## Alternatives considered

Treat MVP topology as production topology.

## Consequences

Improves availability at increased cost and operational complexity.

## Security considerations

HA must preserve policy/state consistency.

## Operational considerations

Requires SLOs, alerts, capacity, and maintenance runbooks.

## Migration / evolution

Detailed topology is finalized after MVP measurements.
