# ADR-0005: Use OKF v0.2 as the declarative agent contract

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Agents must be portable, reviewable definitions instead of hard-coded behavior.

## Decision

Use Open Knowledge Format v0.2 as the base declarative contract for agent knowledge, context, provenance, trust, freshness, and behavior metadata.

## Alternatives considered

Custom YAML with no standard base; runtime-specific Python configuration.

## Consequences

Agent intent becomes reviewable and versioned; runtime implementation remains separate.

## Security considerations

OKF bundles must never contain secrets or unrestricted data payloads.

## Operational considerations

Bundle validation is part of deployment.

## Migration / evolution

Future OKF revisions may require migration ADRs.
