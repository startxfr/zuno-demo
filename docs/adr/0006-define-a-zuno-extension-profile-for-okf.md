# ADR-0006: Define a Zuno extension profile for OKF

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Base OKF does not by itself prescribe the complete runtime configuration required for the platform.

## Decision

Extend OKF with Zuno fields for tasks, models, RAG, MCP, UI metadata, authorization, memory, classifications, budgets, guardrails, and scheduling.

## Alternatives considered

Store runtime configuration in separate unrelated files.

## Consequences

One coherent agent definition is possible while preserving a standards-based knowledge layer.

## Security considerations

Schema validation and allowlists are required so declarative fields cannot silently grant unsafe capabilities.

## Operational considerations

The operator/runtime must support explicit profile versions.

## Migration / evolution

Profile revisions are versioned and backward compatibility is documented.
