# ADR-0103: Automate knowledge freshness and ACL synchronization

- **Status:** Proposed
- **Target:** v1
- **Date:** 2026-08-04

## Context

Public docs update monthly while private sources may change or lose access more frequently.

## Decision

Automate ingestion, freshness scoring, source versioning metadata, and ACL synchronization with explicit stale-content behavior.

## Alternatives considered

Static manually rebuilt indexes.

## Consequences

Improves grounding and reduces unauthorized stale embeddings.

## Security considerations

Source revocation must propagate to retrievable content.

## Operational considerations

Requires scheduled and event-driven jobs where practical.

## Migration / evolution

v2 strengthens private-content deletion automation.
