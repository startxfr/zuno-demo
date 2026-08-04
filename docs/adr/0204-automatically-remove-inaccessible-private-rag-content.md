# ADR-0204: Automatically remove inaccessible private RAG content

- **Status:** Proposed
- **Target:** v2
- **Date:** 2026-08-04

## Context

v0 may defer full deletion when source permissions change if implementation cost is too high.

## Decision

Synchronize source ACL revocation to retrieval indexes and remove/invalidate private embeddings promptly.

## Alternatives considered

Rely only on query-time filtering indefinitely.

## Consequences

Reduces residual access risk.

## Security considerations

Deletion/invalidation must be verifiable.

## Operational considerations

Requires source identity mapping and reconciliation jobs.

## Migration / evolution

May move earlier if risk assessment requires it.
