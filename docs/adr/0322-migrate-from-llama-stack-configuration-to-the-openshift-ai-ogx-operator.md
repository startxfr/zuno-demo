# ADR-0322: Migrate from Llama Stack configuration to the OpenShift AI OGX Operator

- **Status:** Partially implemented (DSC migration, health checks, OGX provider and parity tests merged; live reconciliation confirmed 2026-08-14 via `make d0 install openshift-ai` - `llamastackoperator` absent, `ogx.managementState: Managed` reconciled; OGX server corpus proof and live provider-parity run still pending, deferred by operator decision, roadmap WP-06)
- **Target:** v0/v0.1
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0018](0018-use-ogx-with-langchain-and-langgraph-for-agentic-workflows.md) and [ADR-0050](0050-abstract-the-rag-backend-and-integrate-openshift-ai-ogx.md) for OGX product mapping and implementation lifecycle

## Context

The repository currently configures:

```yaml
llamastackoperator:
  managementState: Managed
```

and older documentation describes OGX as a project-level name for a collection of OpenShift AI capabilities rather than a discrete component.

Red Hat OpenShift AI 3.5 documents a **Llama Stack to OGX migration** and exposes the OGX Operator as a `DataScienceCluster` component activated with:

```yaml
spec:
  components:
    ogx:
      managementState: Managed
```

The OpenShift AI 3.5 OGX documentation exposes native agentic/RAG APIs, OpenAI-compatible APIs and vector-store integrations. PostgreSQL with pgvector is supported as a remote vector store provider, which aligns directly with ADR-0015 and avoids introducing another persistent vector database solely for OGX.

The Zuno architecture still needs an application orchestration boundary because OKF, C1/C2/C3 policy, MCP authorization, task-specific workflows and model-cost/policy decisions are Zuno responsibilities rather than OGX responsibilities.

## Decision

Adopt the **actual Red Hat OpenShift AI OGX Operator** as the product-native agentic/RAG capability and remove the legacy `llamastackoperator` configuration from the Zuno `DataScienceCluster`.

The integration boundary is:

```text
OKF agent contract
      |
      v
Zuno Agent Runtime
      |
      +--> LangGraph/LangChain when deterministic Zuno workflow orchestration is required
      |
      +--> Zuno RAG provider interface
                |
                +--> existing PostgreSQL/pgvector provider
                +--> OGX-backed provider
                          |
                          +--> OGX APIs
                          +--> PostgreSQL/pgvector remote vector store
      |
      +--> MCP Gateway / tools
      |
      v
Zuno AI policy routing / OpenShift AI MaaS
      |
      v
KServe / vLLM / llm-d / approved external models
```

### v0 migration scope

- replace `llamastackoperator` with `ogx.managementState: Managed` in the OpenShift AI `DataScienceCluster` configuration;
- add Day 1 health checks proving the OGX Operator/component is reconciled;
- correct platform documentation so OGX is no longer described as an informal umbrella term;
- preserve the current custom RAG provider and existing Tekos behavior during migration;
- preserve LangChain/LangGraph as an optional orchestration implementation behind the Agent Runtime, not as a competing platform operator.

### v0.1 integration scope

- implement the OGX-backed RAG provider behind the stable Zuno retrieval contract;
- use the existing PostgreSQL/pgvector platform as the preferred durable remote vector store where the current OpenShift AI support/lifecycle is acceptable;
- evaluate OGX OAuth, ABAC and multi-tenancy capabilities without bypassing Keycloak/Zuno authorization boundaries;
- add parity/evaluation tests before any task switches from the custom provider to OGX by default.

## Consequences

The repository aligns with the actual OpenShift AI 3.5 product model and can demonstrate a native Red Hat agentic/RAG capability without abandoning Zuno's declarative OKF contract or policy/orchestration differentiation.

There will be temporary duplication between the custom `rag-service` and OGX. This is intentional until evaluation proves equivalent retrieval, citations, metadata filtering and authorization semantics.

Because the targeted OpenShift AI 3.5 release train is Early Access and some OGX sub-capabilities can carry Technology Preview lifecycle status, Zuno must retain the provider abstraction and must not make the demo irreversibly dependent on a preview-only interface.

## Security considerations

OGX authentication/ABAC is defense in depth, not a replacement for Zuno's trusted identity propagation, agent entitlement, MCP policy intersection or C1/C2/C3 restrictions.

Any OGX-backed retrieval path must preserve:

- initiating-user identity;
- source ACL and group filters;
- data classification;
- provenance and citations;
- external-model egress restrictions.

## Operational considerations

The OpenShift AI role/checks must verify `ogx` readiness after `DataScienceCluster` reconciliation. Provider selection must be observable so traces identify whether a request used native pgvector retrieval or OGX-backed retrieval.

The deployment documentation must record the lifecycle status of the OGX capabilities actually enabled on the target OpenShift AI release.

## Acceptance criteria

- `llamastackoperator` is absent from the rendered `DataScienceCluster`.
- `spec.components.ogx.managementState: Managed` is rendered and reconciles successfully.
- Existing Tekos tests continue to pass without requiring the OGX provider.
- An OGX-backed RAG proof can index/query a controlled test corpus through PostgreSQL/pgvector.
- Provider-parity tests prove metadata/ACL/classification/citation behavior before default-provider migration.

## References

- Red Hat OpenShift AI Self-Managed 3.5, **Working with OGX**, including Llama Stack to OGX migration and activation of the OGX Operator.
- Red Hat OpenShift AI Self-Managed 3.5, **Select and deploy a vector database**, including PostgreSQL with pgvector as an OGX remote vector store provider.
- Red Hat OpenShift AI Self-Managed 3.5 release notes for the lifecycle status of OGX sub-capabilities.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md)
- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md)
- [ADR-0018](0018-use-ogx-with-langchain-and-langgraph-for-agentic-workflows.md)
- [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md)
- [ADR-0114](0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md)
- [ADR-0050](0050-abstract-the-rag-backend-and-integrate-openshift-ai-ogx.md)
