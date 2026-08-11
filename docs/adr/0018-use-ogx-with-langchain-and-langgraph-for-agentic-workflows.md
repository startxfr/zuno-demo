# ADR-0018: Use OGX with LangChain and LangGraph for agentic workflows

- **Status:** Superseded by ADR-0322
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team
- **Superseded:** 2026-08-11 by [ADR-0322](0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md)

## Historical context

This ADR introduced the correct architectural separation between Red Hat OpenShift AI capabilities and application-level agent orchestration, but it used the name "OGX" as an umbrella term for model serving, embeddings and retrieval capabilities. That interpretation no longer matches the OpenShift AI 3.5 product model.

OpenShift AI 3.5 exposes OGX as an actual `DataScienceCluster` managed component and OGX Operator. The repository must therefore distinguish:

- **OpenShift AI model serving** such as KServe, vLLM and llm-d;
- **OGX** as the product-native agentic/RAG API and runtime capability managed by the OGX Operator;
- **LangChain/LangGraph** as Zuno's application orchestration layer where explicit workflow graphs remain useful;
- **Zuno Agent Runtime** as the executor of the declarative OKF agent contract.

## Historical decision

Compose OpenShift AI native capabilities as the inference and AI substrate, and use LangChain/LangGraph as an explicit orchestration layer inside the Agent Runtime when Zuno requires deterministic multi-step workflow control, tool sequencing, state transitions or recovery logic.

The original decision to keep orchestration outside the inference layer remains valid. The product mapping and lifecycle are superseded by ADR-0322, which activates the real OpenShift AI OGX component and defines the boundary between OGX, LangGraph, the Zuno RAG abstraction and model serving.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.

## Related ADRs

- [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md)
- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0050](0050-abstract-the-rag-backend-and-integrate-openshift-ai-ogx.md)
- [ADR-0322](0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md)
