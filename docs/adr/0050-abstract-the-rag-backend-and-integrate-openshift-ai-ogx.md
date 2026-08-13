# ADR-0050: Abstract the RAG backend and integrate OpenShift AI OGX

- **Status:** Superseded by ADR-0322
- **Target:** v0.1
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team
- **Superseded:** 2026-08-11 by [ADR-0322](0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md)

## Context

The custom `rag-service` provides PostgreSQL/pgvector hybrid retrieval and remains useful as a controllable reference implementation. The original ADR treated "OGX/RAG capabilities" as an alternative backend without modeling OGX as its own OpenShift AI managed component.

OpenShift AI 3.5 now has a documented OGX Operator and `spec.components.ogx.managementState` lifecycle. OGX exposes agentic/RAG APIs and supports PostgreSQL with pgvector as a remote vector-store provider. The repository therefore needs a product-accurate integration rather than an informal OGX label around existing RAG building blocks.

## Historical decision retained

Keep a stable internal RAG provider interface consumed by Agent Runtime. Agent definitions select logical knowledge collections and retrieval requirements, not backend-specific endpoints.

PostgreSQL/pgvector remains the durable Zuno data platform and reference retrieval provider. Provider switching must preserve metadata, citations, ACL filtering, provenance and C1/C2/C3 handling.

## Supersession

ADR-0322 supersedes the implementation part of this ADR and consolidates it with ADR-0018. It decides that:

- the OpenShift AI 3.5 OGX Operator is explicitly activated and lifecycle-managed as a real product component;
- the legacy `llamastackoperator` `DataScienceCluster` configuration is removed;
- the Zuno RAG abstraction remains the compatibility boundary;
- an OGX-backed provider can use OGX APIs while PostgreSQL/pgvector remains the preferred persistent vector-store technology;
- LangGraph remains available for Zuno-specific orchestration rather than being replaced blindly by OGX.

## Security considerations

Every RAG provider must enforce the same classification, ACL, identity, provenance and source-filter contracts. Selecting OGX must never widen data access or permit C2/C3 content to cross a model/provider boundary that ADR-0021 and ADR-0035 would otherwise reject.

## Operational considerations

Parity tests must compare the custom pgvector provider and OGX-backed provider for retrieval quality, metadata filtering, citations, identity propagation and classification behavior before the OGX provider becomes the default.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Implementation state, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md)
- [ADR-0018](0018-use-ogx-with-langchain-and-langgraph-for-agentic-workflows.md)
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md)
- [ADR-0322](0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md)
