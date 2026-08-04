# ADR-0018: Use OGX with LangChain and LangGraph for agentic workflows

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Context

Zuno Demo requires an explicit, reviewable architecture decision so implementation, security and roadmap work remain aligned across the MVP and future releases.

**Definition — OGX (OpenShift AI GenAI/RAG eXtensions):** the set of Red Hat OpenShift AI 3.5 native capabilities the platform consumes directly rather than reimplementing — KServe/vLLM-based `InferenceService` model serving, the OpenShift AI embedding and retrieval building blocks used for hybrid RAG over PostgreSQL/pgvector, and the DataScienceCluster-managed serving runtimes for the local Granite/Qwen/Llama model variants. OGX is infrastructure and inference capability, not orchestration: it has no concept of multi-step agent workflows, tool-call sequencing, or conversational state.

## Decision

Compose OGX (model serving, embeddings, retrieval) as the inference substrate, and use LangChain/LangGraph as the explicit orchestration layer on top of it inside the Agent Runtime (ADR-0009): LangGraph defines each agent's workflow as a graph of nodes (retrieve, call-tool-via-MCP-Gateway, reason, respond) with LangChain providing the model/tool client bindings. This keeps orchestration portable and inspectable in application code while letting OGX own GPU-backed inference and retrieval, which is where OpenShift AI's native capabilities add the most value.

## Alternatives considered

Alternatives remain valid when documented in implementation discussions, but this ADR records the selected direction for the stated target release.

## Consequences

Implementation and documentation must follow this decision. Any material change requires a superseding ADR and an explicit migration/evolution note.

## Security considerations

Security implications must be evaluated during implementation. This decision must not weaken identity propagation, data classification, least privilege, secret management or auditability.

## Operational considerations

Operational checks, observability and rollback/diagnostic procedures must be added as the corresponding capability becomes executable.

## Migration / evolution

Future changes must be documented by a new ADR using `Supersedes ADR-0018` when applicable.

## Related ADRs

See [ADR index](README.md).
