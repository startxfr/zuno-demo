# ADR-0012: Use Keycloak as the central identity provider

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Agents need a common authentication and authorization authority and Google Workspace must federate into it.

## Decision

Deploy/configure Keycloak as a prerequisite and use groups such as `agent_<name>` plus task roles and `sales_admin`.

## Alternatives considered

Application-local accounts; Google identity only.

## Consequences

Centralizes identity and decouples applications from the upstream identity provider.

## Security considerations

Keycloak configuration and service credentials are protected by Vault.

## Operational considerations

Availability of authentication is a shared dependency.

## Migration / evolution

v1 hardens HA, lifecycle, and policy administration.
