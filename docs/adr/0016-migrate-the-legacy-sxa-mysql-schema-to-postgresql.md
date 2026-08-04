# ADR-0016: Migrate the legacy SXA MySQL schema to PostgreSQL

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The source commercial schema is a MySQL 5.0-era phpMyAdmin dump and cannot be used directly as the target database.

## Decision

Create reviewed PostgreSQL migrations derived from the supplied schema and load demo data from an external sanitized dump.

## Alternatives considered

Run legacy MySQL inside the demo; redesign sales data from scratch.

## Consequences

Preserves real business semantics while modernizing the database layer.

## Security considerations

Real source data is never committed; legacy password fields are not reused for authentication.

## Operational considerations

Migration must handle enums, zero dates, auto-increment, timestamp semantics, missing foreign keys, and inconsistent identifiers.

## Migration / evolution

v1 can add data-quality validation and reconciliation.
