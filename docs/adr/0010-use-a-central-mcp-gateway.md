# ADR-0010: Use a central MCP Gateway

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Several agents share tools but permissions differ by agent, task, user, and data class.

## Decision

Place a central MCP Gateway in front of MCP servers and make it the governed tool entry point.

## Alternatives considered

Direct runtime-to-MCP calls only; per-agent gateway.

## Consequences

Centralizes authorization, routing, audit, and tool inventory.

## Security considerations

Gateway policy failure must default deny.

## Operational considerations

Gateway becomes a critical shared service.

## Migration / evolution

v1 adds HA and richer audit; v2 adds A2A-aware tool delegation.
