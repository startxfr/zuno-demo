# ADR-0105: Block releases on automated model and agent quality gates

- **Status:** Proposed
- **Target:** v1
- **Date:** 2026-08-04

## Context

v0 establishes the evaluation corpus but may initially run some checks manually.

## Decision

Integrate evaluation, RAG metrics, LM-Eval where relevant, and the agreed pass threshold into CI release gates.

## Alternatives considered

Human review only; benchmark dashboards with no enforcement.

## Consequences

Prevents known regressions from reaching the demo/production target.

## Security considerations

Evaluation data must be sanitized and stable.

## Operational considerations

Quality runs add compute/time to delivery.

## Migration / evolution

Threshold and score dimensions can evolve by agent.
