# ADR-0030: Keep ADR history immutable and supersede decisions explicitly

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The architecture will evolve through v0, v1, v2, and v3. Rewriting history would hide why changes happened.

## Decision

Do not silently rewrite accepted decisions when architecture changes. Create a new ADR that explicitly supersedes the earlier one.

## Alternatives considered

Maintain only a current-state architecture document.

## Consequences

Preserves rationale and migration history.

## Security considerations

Security trade-offs remain auditable.

## Operational considerations

Documentation must link superseding ADRs.

## Migration / evolution

Applies to all future versions.
