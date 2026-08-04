# Architecture Decision Records

ADRs are immutable decision records. When a decision changes, a new ADR supersedes the previous record instead of rewriting history.

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0001](0001-use-a-monorepo-for-the-zuno-agent-platform.md) | v0 | Implemented | Use a monorepo for the Zuno agent platform |
| [ADR-0002](0002-use-openshift-4-20-and-openshift-ai-3-5-ea2-for-the-mvp.md) | v0 | Implemented | Use OpenShift 4.20 and OpenShift AI 3.5 EA2 for the MVP |
| [ADR-0003](0003-use-ansible-and-make-as-the-deployment-entry-point.md) | v0 | Implemented | Use Ansible and Make as the deployment entry point |
| [ADR-0004](0004-use-github-as-the-canonical-source-repository.md) | v0 | Implemented | Use GitHub as the canonical source repository |
| [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md) | v0 | Implemented | Use OKF v0.2 as the declarative agent definition contract |
| [ADR-0006](0006-extend-okf-with-zuno-agent-specific-metadata.md) | v0 | Implemented | Extend OKF with Zuno agent-specific metadata |
| [ADR-0007](0007-separate-agent-instances-from-reusable-platform-components.md) | v0 | Implemented | Separate agent instances from reusable platform components |
| [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md) | v0 | Implemented | Use one frontend and one BFF deployment per agent |
| [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md) | v0 | Accepted | Separate Agent Runtime from AI Inference Gateway |
| [ADR-0010](0010-introduce-a-central-mcp-gateway.md) | v0 | Implemented | Introduce a central MCP Gateway |
| [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md) | v0 | Implemented | Define tool authorization as policy intersection |
| [ADR-0012](0012-use-keycloak-as-the-central-identity-provider.md) | v0 | Implemented | Use Keycloak as the central identity provider |
| [ADR-0013](0013-propagate-end-user-identity-through-agent-calls.md) | v0 | Implemented | Propagate end-user identity through agent calls |
| [ADR-0014](0014-use-delegated-google-oauth-for-google-workspace-access.md) | v0 | Implemented | Use delegated Google OAuth for Google Workspace access |
| [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md) | v0 | Implemented | Use PostgreSQL and pgvector as the persistent data platform |
| [ADR-0016](0016-migrate-the-legacy-sxa-schema-to-postgresql.md) | v0 | Implemented | Migrate the legacy SXA schema to PostgreSQL |
| [ADR-0017](0017-access-sales-data-through-controlled-mcp-tools.md) | v0 | Implemented | Access sales data through controlled MCP tools |
| [ADR-0018](0018-use-ogx-with-langchain-and-langgraph-for-agentic-workflows.md) | v0 | Implemented | Use OGX with LangChain and LangGraph for agentic workflows |
| [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md) | v0 | Implemented | Use OpenShift AI model serving for local inference |
| [ADR-0020](0020-support-both-local-and-external-llm-providers.md) | v0 | Implemented | Support both local and external LLM providers |
| [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md) | v0 | Implemented | Route models according to C1 C2 C3 classification |
| [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md) | v0 | Implemented | Use GitOps-managed declarative agent tasks and policies |
| [ADR-0023](0023-use-a-namespace-per-agent-isolation-model.md) | v0 | Implemented | Use a namespace-per-agent isolation model |
| [ADR-0024](0024-use-vault-for-application-secrets.md) | v0 | Implemented | Use Vault for application secrets |
| [ADR-0025](0025-keep-sensitive-and-real-commercial-data-outside-the-public-repository.md) | v0 | Implemented | Keep sensitive and real commercial data outside the public repository |
| [ADR-0026](0026-provide-an-aiagent-kubernetes-crd-and-operator.md) | v1 | Proposed | Provide an AIAgent Kubernetes CRD and operator |
| [ADR-0027](0027-evaluate-every-agent-with-twenty-acceptance-scenarios.md) | v0 | Implemented | Evaluate every agent with twenty acceptance scenarios |
| [ADR-0028](0028-require-a-seventy-five-percent-evaluation-threshold.md) | v0 | Implemented | Require a seventy-five percent evaluation threshold |
| [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md) | v0 | Implemented | Instrument model usage costs and distributed traces |
| [ADR-0030](0030-use-a-command-dispatch-makefile-interface.md) | v0 | Implemented | Use a command-dispatch Makefile interface |
| [ADR-0101](0101-provide-ha-for-shared-agent-platform-services.md) | v1 | Proposed | Provide HA for shared agent platform services |
| [ADR-0102](0102-target-99-9-percent-platform-availability.md) | v1 | Proposed | Target 99.9 percent platform availability |
| [ADR-0103](0103-persist-resumable-long-running-agent-workflows.md) | v1 | Proposed | Persist resumable long-running agent workflows |
| [ADR-0104](0104-introduce-controlled-semantic-caching.md) | v1 | Proposed | Introduce controlled semantic caching |
| [ADR-0105](0105-automate-monthly-knowledge-ingestion.md) | v1 | Proposed | Automate monthly knowledge ingestion |
| [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md) | v1 | Proposed | Enforce OKF bundle signing and validation |
| [ADR-0107](0107-introduce-automated-model-quality-gates.md) | v1 | Proposed | Introduce automated model quality gates |
| [ADR-0108](0108-automate-model-evaluation-with-lm-eval.md) | v1 | Proposed | Automate model evaluation with LM-Eval |
| [ADR-0109](0109-implement-source-freshness-and-trust-scoring.md) | v1 | Proposed | Implement source freshness and trust scoring |
| [ADR-0110](0110-automate-document-acl-synchronization.md) | v1 | Proposed | Automate document ACL synchronization |
| [ADR-0111](0111-strengthen-secnumcloud-oriented-security-controls.md) | v1 | Proposed | Strengthen SecNumCloud-oriented security controls |
| [ADR-0112](0112-implement-production-grade-backup-and-recovery.md) | v1 | Proposed | Implement production-grade backup and recovery |
| [ADR-0201](0201-introduce-agent-to-agent-communication.md) | v2 | Proposed | Introduce agent-to-agent communication |
| [ADR-0202](0202-adopt-a2a-as-the-inter-agent-protocol.md) | v2 | Proposed | Adopt A2A as the inter-agent protocol |
| [ADR-0203](0203-propagate-user-identity-across-agent-to-agent-calls.md) | v2 | Proposed | Propagate user identity across agent-to-agent calls |
| [ADR-0204](0204-introduce-controlled-shared-agent-memory.md) | v2 | Proposed | Introduce controlled shared agent memory |
| [ADR-0205](0205-expose-agent-delegation-traces-to-users.md) | v2 | Proposed | Expose agent delegation traces to users |
| [ADR-0206](0206-limit-recursive-agent-delegation.md) | v2 | Proposed | Limit recursive agent delegation |
| [ADR-0207](0207-add-specialized-task-oriented-frontend-views.md) | v2 | Proposed | Add specialized task-oriented frontend views |
| [ADR-0208](0208-automate-removal-of-inaccessible-private-rag-content.md) | v2 | Proposed | Automate removal of inaccessible private RAG content |
| [ADR-0209](0209-introduce-advanced-human-approval-workflows.md) | v2 | Proposed | Introduce advanced human approval workflows |
| [ADR-0301](0301-introduce-lora-and-peft-model-customization.md) | v3 | Proposed | Introduce LoRA and PEFT model customization |
| [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md) | v3 | Proposed | Build dataset-to-model MLOps pipelines |
| [ADR-0303](0303-support-dynamic-lora-adapter-loading.md) | v3 | Proposed | Support dynamic LoRA adapter loading |
| [ADR-0304](0304-optimize-model-selection-using-quality-cost-and-latency.md) | v3 | Proposed | Optimize model selection using quality cost and latency |
| [ADR-0305](0305-introduce-automated-model-benchmarking.md) | v3 | Proposed | Introduce automated model benchmarking |
| [ADR-0306](0306-expand-the-agent-catalog-beyond-the-initial-five-agents.md) | v3 | Proposed | Expand the agent catalog beyond the initial five agents |
| [ADR-0307](0307-support-self-service-agent-onboarding.md) | v3 | Proposed | Support self-service agent onboarding |
| [ADR-0308](0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md) | v3 | Proposed | Expand agent lifecycle management through the AIAgent Operator |
| [ADR-0309](0309-introduce-policy-driven-autonomous-optimization.md) | v3 | Proposed | Introduce policy-driven autonomous optimization |
