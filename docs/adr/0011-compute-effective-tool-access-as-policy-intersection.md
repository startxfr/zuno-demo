# ADR-0011: Compute effective tool access as policy intersection

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Declaring a tool in an agent definition must not be sufficient to authorize its use.

## Decision

Effective access equals agent-declared tools ∩ agent permissions ∩ user/group permissions ∩ data classification ∩ task/approval policy.

## Alternatives considered

Agent-only allowlist; user-only RBAC.

## Consequences

Prevents a single policy source from over-granting access.

## Security considerations

Default-deny behavior is mandatory when any dimension is unresolved.

## Operational considerations

Policy decisions should be traceable.

## Migration / evolution

v1 adds formal policy tests and audit dashboards.
