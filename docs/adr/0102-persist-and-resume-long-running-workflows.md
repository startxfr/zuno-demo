# ADR-0102: Persist and resume long-running workflows

- **Status:** Proposed
- **Target:** v1
- **Date:** 2026-08-04

## Context

DAT and complex tasks may run for minutes and users may close their browser.

## Decision

Persist workflow checkpoints so long tasks can pause, resume, survive transient failures, and expose progress.

## Alternatives considered

Keep all state in process memory.

## Consequences

Improves user experience and resilience.

## Security considerations

Checkpoint data must respect document and user access classification.

## Operational considerations

Requires cleanup/retention policies.

## Migration / evolution

v2 may extend resumability across delegated agents.
