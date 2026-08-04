# ADR-0028: Instrument usage cost routing and distributed traces

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The AI Gateway must measure, control, route, and explain model usage across local and SaaS providers.

## Decision

Collect token usage, cost, latency, model/provider selection, routing decisions, MCP/tool traces, and workflow traces using an observability stack and OpenTelemetry-compatible patterns.

## Alternatives considered

Provider billing dashboards only; application logs only.

## Consequences

Enables FinOps, debugging, policy validation, and optimization.

## Security considerations

Telemetry must mask secrets and sensitive prompt content.

## Operational considerations

Observability is a platform prerequisite.

## Migration / evolution

v3 uses these signals for automated optimization.
