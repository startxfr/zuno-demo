# ADR-0009: Separate Agent Runtime from AI Inference Gateway

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Workflow orchestration and model governance have different responsibilities and security boundaries.

## Decision

Agent Runtime owns state, tasks, LangChain/LangGraph, RAG, MCP, memory, and approvals. AI Gateway owns inference routing, model policy, metering, quotas, fallback, streaming, and cache.

## Alternatives considered

One combined AI backend; direct model calls from each agent.

## Consequences

Clear boundaries improve policy enforcement and allow independent evolution.

## Security considerations

Only the runtime may orchestrate business tools; all model traffic must pass through the AI Gateway.

## Operational considerations

Two shared services must be monitored and versioned.

## Migration / evolution

The split remains foundational through v3.
