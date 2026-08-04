# ADR-0106: Harden the platform toward SecNumCloud-oriented controls

- **Status:** Proposed
- **Target:** v1
- **Date:** 2026-08-04

## Context

The target security posture references SecNumCloud principles even though the MVP is an internal demo.

## Decision

Add production-grade identity, network, logging, secret rotation, data-location, supply-chain, operational, and evidence controls aligned with the applicable target.

## Alternatives considered

Treat MVP controls as sufficient for production.

## Consequences

Creates a structured hardening path.

## Security considerations

Some SaaS usage may be incompatible with certain sovereignty requirements and must remain policy-driven.

## Operational considerations

Requires formal control mapping and runbooks.

## Migration / evolution

Exact certification scope is a separate governance decision.
