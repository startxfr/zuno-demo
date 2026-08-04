# ADR-0008: Deploy one frontend and one BFF per agent

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Each agent must expose its own user-facing application and API while reusing implementation code.

## Decision

Create separate frontend and BFF deployments per agent from shared images/configuration.

## Alternatives considered

One monolithic frontend/backend for all agents.

## Consequences

Per-agent routes, scaling, identity configuration, and isolation remain explicit.

## Security considerations

Agent-specific service accounts and NetworkPolicies are possible.

## Operational considerations

More deployments must be operated, but runtime code remains shared.

## Migration / evolution

v2 may add a common portal while keeping instance isolation.
