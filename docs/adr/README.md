# Architecture Decision Records

ADRs are immutable decision records. When a decision changes, a new ADR supersedes the previous record instead of rewriting history.

Most ADRs below carry only a title, status/target/date, and their unique Decision text - the boilerplate clauses every ADR used to repeat (Context, Alternatives, Consequences, Security/Operational considerations, Acceptance criteria, Review evidence, Migration) now live once in [Standard clauses](#standard-clauses) and apply unless a specific ADR overrides them inline.

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
| [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md) | v0 | Implemented | Separate Agent Runtime from AI Inference Gateway |
| [ADR-0010](0010-introduce-a-central-mcp-gateway.md) | v0 | Implemented | Introduce a central MCP Gateway |
| [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md) | v0 | Implemented | Define tool authorization as policy intersection |
| [ADR-0012](0012-use-keycloak-as-the-central-identity-provider.md) | v0 | Implemented | Use Keycloak as the central identity provider |
| [ADR-0013](0013-propagate-end-user-identity-through-agent-calls.md) | v0 | Implemented | Propagate end-user identity through agent calls |
| [ADR-0014](0014-use-delegated-google-oauth-for-google-workspace-access.md) | v0 | Implemented | Use delegated Google OAuth for Google Workspace access |
| [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md) | v0 | Implemented | Use PostgreSQL and pgvector as the persistent data platform |
| [ADR-0016](0016-migrate-the-legacy-sxa-schema-to-postgresql.md) | v0 | Implemented | Migrate the legacy SXA schema to PostgreSQL |
| [ADR-0017](0017-access-sales-data-through-controlled-mcp-tools.md) | v0 | Implemented | Access sales data through controlled MCP tools |
| [ADR-0018](0018-use-ogx-with-langchain-and-langgraph-for-agentic-workflows.md) | v0 | Superseded by ADR-0322 | Use OGX with LangChain and LangGraph for agentic workflows |
| [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md) | v0 | Implemented | Use OpenShift AI model serving for local inference |
| [ADR-0020](0020-support-both-local-and-external-llm-providers.md) | v0 | Implemented | Support both local and external LLM providers |
| [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md) | v0 | Implemented | Route models according to C1 C2 C3 classification |
| [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md) | v0 | Implemented | Use GitOps-managed declarative agent tasks and policies |
| [ADR-0023](0023-use-a-namespace-per-agent-isolation-model.md) | v0 | Superseded by ADR-0329 | Use a namespace-per-agent isolation model |
| [ADR-0024](0024-use-vault-for-application-secrets.md) | v0 | Implemented | Use Vault for application secrets |
| [ADR-0025](0025-keep-sensitive-and-real-commercial-data-outside-the-public-repository.md) | v0 | Implemented | Keep sensitive and real commercial data outside the public repository |
| [ADR-0026](0026-provide-an-aiagent-kubernetes-crd-and-operator.md) | v1 | Proposed | Provide an AIAgent Kubernetes CRD and operator |
| [ADR-0027](0027-evaluate-every-agent-with-twenty-acceptance-scenarios.md) | v0 | Implemented | Evaluate every agent with twenty acceptance scenarios |
| [ADR-0028](0028-require-a-seventy-five-percent-evaluation-threshold.md) | v0 | Implemented | Require a seventy-five percent evaluation threshold |
| [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md) | v0 | Implemented | Instrument model usage costs and distributed traces |
| [ADR-0030](0030-use-a-command-dispatch-makefile-interface.md) | v0 | Implemented | Use a command-dispatch Makefile interface |
| [ADR-0031](0031-formalize-tekos-as-the-v0-vertical-slice.md) | v0 | Implemented | Formalize Tekos as the v0 vertical slice |
| [ADR-0032](0032-propagate-trusted-identity-end-to-end.md) | v0 | Implemented | Propagate trusted identity end to end |
| [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md) | v0 | Implemented | Derive user identity only from validated tokens |
| [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md) | v0 | Implemented | Compute effective classification from the complete context |
| [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md) | v0 | Implemented | Prevent restricted internal context from reaching external models |
| [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md) | v0 | Implemented | Enforce the complete MCP authorization intersection in the gateway |
| [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md) | v0 | Implemented | Protect MCP servers with network and workload identity boundaries |
| [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md) | v0 | Implemented | Use standards-compliant OKF v0.2 Markdown bundles |
| [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md) | v0 | Implemented | Make Agent Runtime execute the OKF agent contract |
| [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md) | v0 | Implemented | Separate agent entitlement from business role authorization |
| [ADR-0041](0041-remove-nominative-demo-identities-and-static-passwords-from-git.md) | v0 | Implemented | Remove nominative demo identities and static passwords from Git |
| [ADR-0042](0042-use-opaque-browser-sessions-with-server-side-token-storage.md) | v1 | Implemented | Use opaque browser sessions with server-side token storage |
| [ADR-0043](0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md) | v1 | Implemented | Use standard MCP protocol behind the Zuno MCP Gateway |
| [ADR-0044](0044-use-patternfly-react-for-the-agent-frontend.md) | v0 | Implemented | Use PatternFly React for the agent frontend |
| [ADR-0045](0045-stream-responses-end-to-end-with-sse.md) | v0 | Implemented | Stream responses end to end with SSE |
| [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md) | v0 | Implemented | Make RAG retrieval metadata-aware and bilingual |
| [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md) | v0 | Implemented | Manage the complete OpenShift AI prerequisite lifecycle |
| [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md) | v0 | Implemented | Discover supported operator channels and serving runtimes at deployment time |
| [ADR-0049](0049-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md) | v1 | To be implemented | Use Zuno as a policy router in front of OpenShift AI MaaS |
| [ADR-0050](0050-abstract-the-rag-backend-and-integrate-openshift-ai-ogx.md) | v1 | Superseded by ADR-0322 | Abstract the RAG backend and integrate OpenShift AI OGX |
| [ADR-0051](0051-use-immutable-and-verifiable-software-supply-chain-artifacts.md) | v0 | Partially implemented | Use immutable and verifiable software supply chain artifacts |
| [ADR-0052](0052-harden-all-workloads-for-openshift-restricted-security-and-secnumcloud-objectives.md) | v0 | Implemented | Harden all workloads for OpenShift restricted security and SecNumCloud objectives |
| [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md) | v0 | Implemented | Make make check an end-to-end acceptance and security gate |
| [ADR-0054](0054-define-the-bff-contract-openapi-first.md) | v0 | Implemented | Define the BFF contract OpenAPI-first |
| [ADR-0055](0055-repository-review-change-set-index.md) | v0/v1 | Implemented | Repository review change-set index |
| [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) | v0 | Implemented | Restructure deployment into Day 0 / Day 1 sequencing |
| [ADR-0101](0100-v1-roadmap.md#adr-0101-provide-ha-for-shared-agent-platform-services) | v1 | Proposed | Provide HA for shared agent platform services |
| [ADR-0102](0100-v1-roadmap.md#adr-0102-target-999-percent-platform-availability) | v1 | Proposed | Target 99.9 percent platform availability |
| [ADR-0103](0100-v1-roadmap.md#adr-0103-persist-resumable-long-running-agent-workflows) | v1 | Proposed | Persist resumable long-running agent workflows |
| [ADR-0104](0100-v1-roadmap.md#adr-0104-introduce-controlled-semantic-caching) | v1 | Proposed | Introduce controlled semantic caching |
| [ADR-0105](0100-v1-roadmap.md#adr-0105-automate-monthly-knowledge-ingestion) | v1 | Proposed | Automate monthly knowledge ingestion |
| [ADR-0106](0100-v1-roadmap.md#adr-0106-enforce-okf-bundle-signing-and-validation) | v1 | Proposed | Enforce OKF bundle signing and validation |
| [ADR-0107](0100-v1-roadmap.md#adr-0107-introduce-automated-model-quality-gates) | v1 | Proposed | Introduce automated model quality gates |
| [ADR-0108](0100-v1-roadmap.md#adr-0108-automate-model-evaluation-with-lm-eval) | v1 | Proposed | Automate model evaluation with LM-Eval |
| [ADR-0109](0100-v1-roadmap.md#adr-0109-implement-source-freshness-and-trust-scoring) | v1 | Proposed | Implement source freshness and trust scoring |
| [ADR-0110](0100-v1-roadmap.md#adr-0110-automate-document-acl-synchronization) | v1 | Proposed | Automate document ACL synchronization |
| [ADR-0111](0100-v1-roadmap.md#adr-0111-strengthen-secnumcloud-oriented-security-controls) | v1 | Proposed | Strengthen SecNumCloud-oriented security controls |
| [ADR-0112](0100-v1-roadmap.md#adr-0112-implement-production-grade-backup-and-recovery) | v1 | Proposed | Implement production-grade backup and recovery |
| [ADR-0201](0200-v2-roadmap.md#adr-0201-introduce-agent-to-agent-communication) | v2 | Proposed | Introduce agent-to-agent communication |
| [ADR-0202](0200-v2-roadmap.md#adr-0202-adopt-a2a-as-the-inter-agent-protocol) | v2 | Proposed | Adopt A2A as the inter-agent protocol |
| [ADR-0203](0200-v2-roadmap.md#adr-0203-propagate-user-identity-across-agent-to-agent-calls) | v2 | Proposed | Propagate user identity across agent-to-agent calls |
| [ADR-0204](0200-v2-roadmap.md#adr-0204-introduce-controlled-shared-agent-memory) | v2 | Proposed | Introduce controlled shared agent memory |
| [ADR-0205](0200-v2-roadmap.md#adr-0205-expose-agent-delegation-traces-to-users) | v2 | Proposed | Expose agent delegation traces to users |
| [ADR-0206](0200-v2-roadmap.md#adr-0206-limit-recursive-agent-delegation) | v2 | Proposed | Limit recursive agent delegation |
| [ADR-0207](0200-v2-roadmap.md#adr-0207-add-specialized-task-oriented-frontend-views) | v2 | Proposed | Add specialized task-oriented frontend views |
| [ADR-0208](0200-v2-roadmap.md#adr-0208-automate-removal-of-inaccessible-private-rag-content) | v2 | Proposed | Automate removal of inaccessible private RAG content |
| [ADR-0209](0200-v2-roadmap.md#adr-0209-introduce-advanced-human-approval-workflows) | v2 | Proposed | Introduce advanced human approval workflows |
| [ADR-0301](0301-introduce-lora-and-peft-model-customization.md) | v3 | To be implemented | Introduce LoRA and PEFT model customization |
| [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md) | v3 | To be implemented | Build dataset-to-model MLOps pipelines |
| [ADR-0303](0300-v3-roadmap.md#adr-0303-support-dynamic-lora-adapter-loading) | v3 | Proposed | Support dynamic LoRA adapter loading |
| [ADR-0304](0300-v3-roadmap.md#adr-0304-optimize-model-selection-using-quality-cost-and-latency) | v3 | Proposed | Optimize model selection using quality cost and latency |
| [ADR-0305](0300-v3-roadmap.md#adr-0305-introduce-automated-model-benchmarking) | v3 | Proposed | Introduce automated model benchmarking |
| [ADR-0306](0300-v3-roadmap.md#adr-0306-expand-the-agent-catalog-beyond-the-initial-five-agents) | v3 | Proposed | Expand the agent catalog beyond the initial five agents |
| [ADR-0307](0300-v3-roadmap.md#adr-0307-support-self-service-agent-onboarding) | v3 | Proposed | Support self-service agent onboarding |
| [ADR-0308](0300-v3-roadmap.md#adr-0308-expand-agent-lifecycle-management-through-the-aiagent-operator) | v3 | Proposed | Expand agent lifecycle management through the AIAgent Operator |
| [ADR-0309](0300-v3-roadmap.md#adr-0309-introduce-policy-driven-autonomous-optimization) | v3 | Proposed | Introduce policy-driven autonomous optimization |
| [ADR-0310](0310-manage-static-kubernetes-resources-as-per-role-kustomize-directories.md) | v0 | Implemented | Manage static Kubernetes resources as per-role kustomize directories |
| [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md) | v0 | Implemented | Stop applying the root App-of-Apps from Ansible bootstrap tasks |
| [ADR-0312](0312-route-operator-installs-through-argocd-applications.md) | v0 | Implemented | Route operator installs through ArgoCD Applications |
| [ADR-0313](0313-move-day1-schema-jobs-and-llm-provider-secrets-behind-argocd.md) | v0 | Implemented | Move Day 1 schema Jobs and LLM provider secret seeding behind ArgoCD/Vault |
| [ADR-0314](0314-convert-admin-context-to-a-d0-d1-argocd-application-pair.md) | v0 | Implemented | Convert admin_context to a -d0/-d1 ArgoCD Application pair |
| [ADR-0315](0315-dedicated-keycloak-postgresql-database.md) | v0 | Implemented | Dedicated Keycloak database/role on the shared PostgreSQL cluster |
| [ADR-0316](0316-keycloak-route-tls-via-cert-manager.md) | v0 | Implemented | Keycloak's Route gets a cert-manager-issued certificate via a hand-authored Ingress |
| [ADR-0317](0317-install-connectivity-link-and-leaderworkerset-operators.md) | v0 | Implemented | Install the Red Hat Connectivity Link and LeaderWorkerSet operators as OpenShift AI prerequisites |
| [ADR-0318](0318-install-custom-metrics-autoscaler-and-jobset-operators.md) | v0 | Implemented | Install the Custom Metrics Autoscaler and JobSet operators as OpenShift AI prerequisites |
| [ADR-0319](0319-target-openshift-4-22.md) | v0 | Implemented | Target OpenShift 4.22 |
| [ADR-0320](0320-pre-provision-openshift-users-rbac-and-console-favorites-via-keycloak.md) | v0 | Implemented | Pre-provision OpenShift users, RBAC and Console favorites via Keycloak |
| [ADR-0321](0321-delegate-kueue-lifecycle-to-the-red-hat-build-of-kueue-operator.md) | v0 | Implemented | Delegate Kueue lifecycle to the Red Hat build of Kueue Operator |
| [ADR-0322](0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md) | v0/v1 | To be implemented | Migrate from Llama Stack configuration to the OpenShift AI OGX Operator |
| [ADR-0323](0323-establish-canonical-generated-and-validated-platform-documentation.md) | v0 | Implemented | Establish canonical generated and validated platform documentation |
| [ADR-0324](0324-reconcile-the-ci-build-inventory-with-the-repository-component-lifecycle.md) | v0 | Implemented | Reconcile the CI build inventory with the repository component lifecycle |
| [ADR-0325](0325-complete-the-openshift-ai-maas-governance-plane-integration.md) | v1 | To be implemented | Complete the OpenShift AI MaaS governance plane integration |
| [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md) | v1 | To be implemented | Generalize the Tekos vertical slice to the four remaining agents |
| [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md) | v1 | To be implemented | Define the AIAgent CRD reconciliation contract before implementing the operator |
| [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) | v0 | To be implemented | Separate the OpenShift AI control plane from AI build and run workload namespaces |
| [ADR-0329](0329-consolidate-agent-workloads-into-the-shared-zuno-ai-run-namespace.md) | v0 | Implemented | Consolidate agent workloads into the shared zuno-ai-run namespace |
| [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md) | v0/v1 | Partially implemented | Integrate the rag-ingestion pipeline as a Day 1 component with persona-scoped Confluence access |

## Standard clauses

Every ADR is implicitly bound by the clauses below unless it explicitly overrides one inline. This keeps identical boilerplate from being repeated in every file - an ADR that says nothing more than "see Standard clauses" is not skipping a step, it is accepting these defaults as-is.

- **Context** (when not stated otherwise): Zuno Demo requires an explicit, reviewable architecture decision so implementation, security and roadmap work remain aligned across the MVP and future releases.
- **Alternatives considered** (when not stated otherwise): Alternatives remain valid when documented in implementation discussions, but the ADR records the selected direction for the stated target release.
- **Alternatives considered** (ADR-0031–0054, when not stated otherwise): Keep the current implementation unchanged and rely on conventions or documentation - rejected because the reviewed code shows that implicit contracts already diverge from intended behavior; or defer the decision until all five agents are implemented - rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.
- **Consequences** (when not stated otherwise): Implementation and documentation must follow the decision. Any material change requires a superseding ADR and an explicit migration/evolution note.
- **Security considerations** (when not stated otherwise): Security implications must be evaluated during implementation. A decision must not weaken identity propagation, data classification, least privilege, secret management or auditability.
- **Operational considerations** (when not stated otherwise): Operational checks, observability and rollback/diagnostic procedures must be added as the corresponding capability becomes executable.
- **Migration / evolution** (when not stated otherwise): Future changes must be documented by a new ADR using `Supersedes ADR-NNNN` when applicable.
- **Acceptance criteria** (extended-template ADRs, when not stated otherwise):
  - The implementation is merged through the normal repository review process.
  - Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
  - `make check` or component-specific automated tests demonstrate the behavior described in the ADR.
  - Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.
- **Implementation state** (extended-template ADRs still `To be implemented`, when not stated otherwise): This ADR records an agreed architectural change identified during the 2026-08-05 repository review. No implementation is claimed by this ADR. The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.
- **Review evidence** (extended-template ADRs, when not stated otherwise): The decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository; paths named in the ADR's own Context/Decision sections identify the primary implementation evidence.
- **Related ADRs** (when not stated otherwise): See this index.
