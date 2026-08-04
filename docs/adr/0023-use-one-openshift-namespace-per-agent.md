# ADR-0023: Use one OpenShift namespace per agent

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Agents have different users, tools, policies, and potential data sensitivity.

## Decision

Create a namespace per agent instance and separate shared platform namespaces for common services.

## Alternatives considered

Single namespace for the whole demo.

## Consequences

Improves RBAC, quota, NetworkPolicy, and operational separation.

## Security considerations

Namespace boundaries complement but do not replace application-level authorization.

## Operational considerations

More namespaces require templated/operator management.

## Migration / evolution

AIAgent operator automates the lifecycle.
