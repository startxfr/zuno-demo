# ADR-0104: Enforce signed OKF bundles at deployment

- **Status:** Proposed
- **Target:** v1
- **Date:** 2026-08-04

## Context

Git review alone does not prove a runtime bundle is the reviewed artifact.

## Decision

Verify Git provenance and bundle signatures before operator/runtime acceptance.

## Alternatives considered

Unsigned bundles with repository-only trust.

## Consequences

Strengthens supply-chain integrity.

## Security considerations

Signing key lifecycle is managed through Vault/external secure systems.

## Operational considerations

CI/CD and operator admission must share verification rules.

## Migration / evolution

May later use policy/admission integrations.
