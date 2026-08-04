# ADR-0303: Optimize routing using measured quality cost and latency

- **Status:** Proposed
- **Target:** v3
- **Date:** 2026-08-04

## Context

The gateway already collects quality, cost, latency, availability, and classification signals.

## Decision

Use policy-bounded optimization to choose eligible models/providers dynamically while preserving explicit sovereignty and task constraints.

## Alternatives considered

Static provider preference forever.

## Consequences

Can lower cost and latency while protecting response quality.

## Security considerations

Optimization is subordinate to classification and allowlists.

## Operational considerations

Requires reliable metrics and explainable routing traces.

## Migration / evolution

May incorporate per-agent learned policies after governance review.
