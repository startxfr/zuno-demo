# ADR-0024: Use Vault for application secrets

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The platform requires model-provider keys, OAuth secrets, database credentials, SMTP credentials, and signing material.

## Decision

Use Vault as the centralized secret prerequisite and inject secrets at runtime.

## Alternatives considered

Kubernetes Secrets only; secrets in CI variables without centralized lifecycle.

## Consequences

Centralizes policy and rotation.

## Security considerations

No secrets are committed to the public repository or MEMORY.md.

## Operational considerations

Vault health and connectivity are prerequisites.

## Migration / evolution

v1 adds production rotation/runbooks.
