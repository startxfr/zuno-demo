# ADR-0018: Use LangChain and LangGraph with OpenShift AI capabilities

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The platform needs stateful declarative workflows, RAG, tools, human approval, and long-running resumable tasks while also using OpenShift AI services.

## Decision

Use LangChain/LangGraph at the application orchestration layer and integrate OpenShift AI 3.5 capabilities such as OGX/RAG/model serving where they add platform value.

## Alternatives considered

Only LangChain; only OGX; custom workflow engine.

## Consequences

Balances mature workflow orchestration with OpenShift AI integration.

## Security considerations

Runtime tool/model calls remain behind central policy boundaries.

## Operational considerations

Component maturity/support status must be visible in prechecks/docs.

## Migration / evolution

Revisit the split as OpenShift AI agentic capabilities mature.
