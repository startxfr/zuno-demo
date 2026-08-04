# ADR-0025: Keep real and nominative commercial data out of the public repository

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The canonical repository is public while the SXA source/data is business-sensitive.

## Decision

Commit only schema-derived documentation, migrations, and sanitized/synthetic fixtures. Keep real dumps, customer data, emails, credentials, and tokens external.

## Alternatives considered

Commit encrypted production dumps; make the repository private by assumption.

## Consequences

Preserves public open-source posture without publishing sensitive business information.

## Security considerations

`.gitignore`, review checklist, CI scanning, and contributor guidance reinforce the rule.

## Operational considerations

Demo data loading references an external sanitized source.

## Migration / evolution

Revisit repository visibility only through a separate explicit decision.
