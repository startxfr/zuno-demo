# ADR-0021: Route inference according to C1 C2 C3 classification

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Sensitive context must not be sent to a model solely because it is preferred or cheaper.

## Decision

Use C1 SaaS-allowed, C2 conditionally SaaS-allowed, and C3 local-only defaults. Confluence C2 content is explicitly not sent to SaaS. Sovereign DAT work is local-only.

## Alternatives considered

No classification-based routing; per-provider manual choice only.

## Consequences

Policy is consistent across agents and can fail safely.

## Security considerations

No permitted destination means refusal/failure, never policy bypass.

## Operational considerations

Classification decisions should appear in traces without exposing content.

## Migration / evolution

v1 formalizes policy tests and SecNumCloud-oriented controls.
