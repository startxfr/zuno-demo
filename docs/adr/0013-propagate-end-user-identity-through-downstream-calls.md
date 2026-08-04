# ADR-0013: Propagate end-user identity through downstream calls

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Google, Confluence, sales visibility, and tool authorization may depend on the real requester.

## Decision

Preserve end-user identity context from frontend through BFF, runtime, MCP gateway, and user-scoped tools, using service identities only where appropriate.

## Alternatives considered

Shared technical identity for all downstream operations.

## Consequences

Maintains least privilege and user-specific source ACLs.

## Security considerations

Token exchange/OBO paths must avoid credential leakage and confused-deputy issues.

## Operational considerations

Tracing must correlate calls without logging raw tokens.

## Migration / evolution

v2 extends propagation across A2A calls.
