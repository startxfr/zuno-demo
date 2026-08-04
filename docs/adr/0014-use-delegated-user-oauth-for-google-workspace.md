# ADR-0014: Use delegated user OAuth for Google Workspace

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Gmail and Drive access must remain bounded by each user permissions.

## Decision

Use delegated OAuth2 per user for Google Workspace APIs, retain credentials/session state for at most five days, and support revocation.

## Alternatives considered

Domain-wide service account for all reads; static shared credentials.

## Consequences

Preserves user ACLs and avoids broad technical-account access.

## Security considerations

Tokens are encrypted/protected through Vault-backed handling and never stored in source control.

## Operational considerations

Token renewal/revocation becomes an operational flow.

## Migration / evolution

v1 refines token lifecycle and audit.
