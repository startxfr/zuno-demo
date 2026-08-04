# ADR-0020: Support governed local and SaaS model routing

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Different tasks balance quality, cost, sovereignty, and latency differently.

## Decision

All inference passes through the AI Gateway. Default SaaS preference/fallback is OpenAI → Gemini → Anthropic → Mistral, overridable by agent/task policy; local Granite/Qwen/Llama models are also available.

## Alternatives considered

Single model/provider; agent-specific direct provider integrations.

## Consequences

Enables fallback, cost governance, and workload-specific routing.

## Security considerations

Classification and source restrictions override provider preference.

## Operational considerations

Provider health, token usage, cost, and latency are observed.

## Migration / evolution

v3 adds automated optimization based on measured quality/cost/latency.
