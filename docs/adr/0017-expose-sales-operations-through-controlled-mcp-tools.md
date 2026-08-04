# ADR-0017: Expose sales operations through controlled MCP tools

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Comage, Advantage, and Finage need read/write sales access but unrestricted generated SQL is unsafe.

## Decision

Expose deterministic task-oriented sales operations through an MCP service. Store allowed queries/actions with agent GitOps definitions and validate writes before execution.

## Alternatives considered

Direct unrestricted SQL from the LLM; separate REST API for v0.

## Consequences

Improves safety and testability while keeping MCP consistent with the platform tool model.

## Security considerations

Writes, especially status changes, are policy-controlled and can require approval.

## Operational considerations

MCP health is part of `make check`.

## Migration / evolution

A dedicated domain API can replace internals later without changing the agent tool contract.
