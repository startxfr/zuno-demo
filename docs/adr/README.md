# Architecture Decision Records

ADRs are immutable decision records. When a decision changes, a new ADR supersedes the previous record instead of rewriting history.

Most ADRs below carry only a title, status/target/date, and their unique Decision text - the boilerplate clauses every ADR used to repeat (Context, Alternatives, Consequences, Security/Operational considerations, Acceptance criteria, Review evidence, Migration) now live once in [Standard clauses](#standard-clauses) and apply unless a specific ADR overrides them inline.

Implementation sequencing for the open v0.1/v0.2/v0.3 ADRs is tracked in the [v0.1 – v0.3 implementation roadmap](../roadmap/v0.1-v0.3-implementation-roadmap.md); this index remains the sole authority for ADR status.

**Renumbering note (2026-08-13):** the roadmap reorganization moved open decisions into the v0.1 stream. ADR-0026 -> ADR-0113, ADR-0049 -> ADR-0114, ADR-0051 -> ADR-0115 (unimplemented 00xx records), and ADR-0207 -> ADR-0116, ADR-0210 -> ADR-0117 (promoted from v0.2 as concretely implementable). The old numbers are retired; each moved record carries a `Renumbered:` line.

**Renumbering note (2026-08-15):** three decisions were re-streamed to the version that actually delivers them. ADR-0113 -> ADR-0350 (v0.1 -> v0.3, the CRD/operator is delivered by ADR-0327/ADR-0308), ADR-0348 -> ADR-0211 (v0.1 -> v0.2), ADR-0306 -> ADR-0410 (v0.3 -> v0.4). The old numbers are retired; each moved record carries a `Renumbered:` line.

**Banding note (2026-08-18):** the 05xx band is reserved for the OKF stream (ADR-0501, its own version line OKF v0.1 – OKF v0.3, tracked in the [OKF roadmap](../roadmap/okf-roadmap.md)); a future platform v0.5 stream takes the next free band.

**Retargeting note (2026-08-24, morning):** ADR-0201 (v0.2 -> v0.3) and ADR-0511/ADR-0512 (OKF v0.1 -> v0.3) all retargeted together - the upstream Kuadrant wasm-shim defect blocking WP-27/WP-54 has no repo-side fix, and ADR-0512/WP-55 has a hard `Depends on: WP-54`, so it moves with ADR-0511 rather than sitting blocked inside their original milestones. Numbering (02xx/05xx band) is unchanged; only the `Target` column moves.

**Retargeting note (2026-08-24, afternoon):** three new platform version bands added - v0.5 (make the MaaS governance plane live and used by agents), v0.6 (prove platform automation via a from-scratch redeploy on a new cluster), v0.7 (GitHub-Actions-based release automation). ADR-0201/ADR-0511/ADR-0512 move again, this time from the morning's generic v0.3 catch-all into the dedicated v0.5 MaaS milestone (same root blocker, better-scoped home). ADR-0115 (v0.1 -> v0.7) joins WP-04's GitHub Actions release-pipeline scope. ADR-0517 is a new small ADR authored for v0.6 (demo333 cluster redeploy). No new ADR numbering band was reserved - v0.5/v0.7 reuse existing ADR numbers, and ADR-0517 simply takes the next free sequential number after ADR-0516.

**Retargeting note (2026-08-26):** ADR-0111 (v0.1 -> v0.7, Partially implemented -> Deferred) - its sole remaining gap (immutable chart image tags) is blocked on the same WP-04 external GitHub billing lock that already parked ADR-0115 in Deferred status under the v0.7 milestone; ADR-0111 now groups there alongside it. Numbering (01xx band) is unchanged; only `Target`/`Status` move.

**Retargeting note (2026-08-26):** ADR-0105 (v0.1 -> v0.7) and ADR-0206 (v0.2 -> v0.7) move to the v0.7 band as a separate, unrelated deferred-items group - not part of WP-04's GitHub-Actions release-automation scope already there. Status unchanged for both (`Partially implemented`); only `Target` moves.

**Retargeting note (2026-08-30):** ADR-0517 (v0.6 -> v0.8) - the demo333 from-scratch redeploy is deprioritized behind v0.7's release-automation work. v0.6 was created solely for this ADR and is now a vacant band; a new v0.8 band is opened to carry it (same goal text, unchanged Status/scope). Numbering is unchanged; only `Target` moves.

**Retargeting note (2026-08-30):** v0.7 is split by done-ness into a short-term closeout band and a long-term/harder band. ADR-0105, ADR-0206, ADR-0213 and ADR-0218 (v0.7 -> v0.6) - all four are already closed out (WP-22/WP-23 Done, ADR-0213 Superseded, ADR-0218 Implemented) and only need formal retargeting; they fill the band left vacant by ADR-0517's move to v0.8. ADR-0111 and ADR-0115 stay in v0.7 (externally blocked on the same WP-04 GitHub-billing lock), joined there by ADR-0352 (a large, not-yet-started day-0 tiering effort, previously carried in v0.7's now-removed second table). Numbering is unchanged; only `Target` moves.

**Retargeting note (2026-08-24, evening):** ADR-0354 (Add Ansible Automation Platform as a new Day 0 component, v0.3) is amended in place - it was never implemented, so this is a correction rather than a superseding decision. Placement moves from a Day 0 sequence ADR-0060 has since retired (`... keycloak → aap → machines ...`) to Day 1, immediately after `openshift_oauth`; scope is split into two components (`aap` for the platform itself, `aap-config` for repository/Job-Template registration, mechanism decided from a live CRD inventory rather than assumed); sizing is explicitly non-HA; `Target` moves v0.3 -> v0.2. The file is renamed to `0354-add-ansible-automation-platform-as-a-day-1-component.md` to keep the filename in sync with the corrected title. ADR-0355 is a new companion ADR (v0.3) covering the follow-on `mcp-aap` server that lets agents launch/read AAP. ADR-0418 (execute Day 0/Day 1 operations as AAP Job Templates, v0.4) is unchanged.

## version 0

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
| [ADR-0016](0016-migrate-the-legacy-sxa-schema-to-postgresql.md) | v0 | Superseded by ADR-0219 | Migrate the legacy SXA schema to PostgreSQL |
| [ADR-0017](0017-access-sales-data-through-controlled-mcp-tools.md) | v0 | Implemented | Access sales data through controlled MCP tools |
| [ADR-0018](0018-use-ogx-with-langchain-and-langgraph-for-agentic-workflows.md) | v0 | Superseded by ADR-0322 | Use OGX with LangChain and LangGraph for agentic workflows |
| [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md) | v0 | Implemented | Use OpenShift AI model serving for local inference |
| [ADR-0020](0020-support-both-local-and-external-llm-providers.md) | v0 | Implemented | Support both local and external LLM providers |
| [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md) | v0 | Implemented | Route models according to C1 C2 C3 classification |
| [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md) | v0 | Implemented | Use GitOps-managed declarative agent tasks and policies |
| [ADR-0023](0023-use-a-namespace-per-agent-isolation-model.md) | v0 | Superseded by ADR-0329 | Use a namespace-per-agent isolation model |
| [ADR-0024](0024-use-vault-for-application-secrets.md) | v0 | Implemented | Use Vault for application secrets |
| [ADR-0025](0025-keep-sensitive-and-real-commercial-data-outside-the-public-repository.md) | v0 | Implemented | Keep sensitive and real commercial data outside the public repository |
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
| [ADR-0042](0042-use-opaque-browser-sessions-with-server-side-token-storage.md) | v0.1 | Implemented | Use opaque browser sessions with server-side token storage |
| [ADR-0043](0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md) | v0.1 | Implemented | Use standard MCP protocol behind the Zuno MCP Gateway |
| [ADR-0044](0044-use-patternfly-react-for-the-agent-frontend.md) | v0 | Implemented | Use PatternFly React for the agent frontend |
| [ADR-0045](0045-stream-responses-end-to-end-with-sse.md) | v0 | Implemented | Stream responses end to end with SSE |
| [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md) | v0 | Implemented | Make RAG retrieval metadata-aware and bilingual |
| [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md) | v0 | Implemented | Manage the complete OpenShift AI prerequisite lifecycle |
| [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md) | v0 | Implemented | Discover supported operator channels and serving runtimes at deployment time |
| [ADR-0050](0050-abstract-the-rag-backend-and-integrate-openshift-ai-ogx.md) | v0.1 | Superseded by ADR-0322 | Abstract the RAG backend and integrate OpenShift AI OGX |
| [ADR-0052](0052-harden-all-workloads-for-openshift-restricted-security-and-secnumcloud-objectives.md) | v0 | Implemented | Harden all workloads for OpenShift restricted security and SecNumCloud objectives |
| [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md) | v0 | Implemented | Make make check an end-to-end acceptance and security gate |
| [ADR-0054](0054-define-the-bff-contract-openapi-first.md) | v0 | Implemented | Define the BFF contract OpenAPI-first |
| [ADR-0055](0055-repository-review-change-set-index.md) | v0.1 | Implemented | Repository review change-set index |
| [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) | v0 | Implemented | Restructure deployment into Day 0 / Day 1 sequencing |
| [ADR-0057](0057-introduce-day-2-agent-availability-test-and-stresstest-operations.md) | v0 | Implemented | Introduce Day 2 agent availability-test and stresstest operations |
| [ADR-0058](0058-aggregate-existing-test-content-into-a-bulk-interaction-stresstest.md) | v0 | Implemented | Aggregate existing test content into make d2 stresstest, with a bulk-interaction load mode |
| [ADR-0059](0059-auto-redeploy-on-in-cluster-build-via-image-triggers.md) | v0 | Implemented | Auto-redeploy consuming pods when an in-cluster build completes |
| [ADR-0060](0060-restructure-day-0-day-1-day-2-day-3-deployment-sequencing.md) | v0 | Implemented | Restructure deployment into Day 0 / Day 1 / Day 2 / Day 3 sequencing |

## version 0.1

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0101](0101-provide-ha-for-shared-agent-platform-services.md) | v0.1 | Implemented | Provide HA for shared agent platform services |
| [ADR-0102](0102-target-99-9-percent-platform-availability.md) | v0.1 | Implemented | Target 99.9 percent platform availability |
| [ADR-0103](0103-persist-resumable-long-running-agent-workflows.md) | v0.1 | Implemented | Persist resumable long-running agent workflows |
| [ADR-0104](0104-introduce-controlled-semantic-caching.md) | v0.1 | Implemented | Introduce controlled semantic caching |
| [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md) | v0.1 | Implemented | Enforce OKF bundle signing and validation |
| [ADR-0107](0107-introduce-automated-model-quality-gates.md) | v0.1 | Implemented | Introduce automated model quality gates |
| [ADR-0108](0108-automate-model-evaluation-with-lm-eval.md) | v0.1 | Implemented | Automate model evaluation with LM-Eval |
| [ADR-0109](0109-implement-source-freshness-and-trust-scoring.md) | v0.1 | Implemented | Implement source freshness and trust scoring |
| [ADR-0110](0110-automate-document-acl-synchronization.md) | v0.1 | Implemented | Automate document ACL synchronization |
| [ADR-0112](0112-implement-production-grade-backup-and-recovery.md) | v0.1 | Implemented | Implement production-grade backup and recovery |
| [ADR-0114](0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md) | v0.1 | Superseded by ADR-0118 | Use Zuno as a policy router in front of OpenShift AI MaaS |
| [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md) | v0.1 | Implemented | Decouple logical tool capabilities from physical backend bindings |
| [ADR-0117](0117-implement-confluence-as-the-first-real-external-mcp-integration.md) | v0.1 | Implemented | Implement Confluence as the first real external MCP integration |
| [ADR-0118](0118-keep-the-ai-gateway-as-policy-router-and-defer-maas-delegation.md) | v0.1 | Implemented | Keep the AI Gateway as policy router and defer MaaS delegation to the governance plane |
| [ADR-0119](0119-introduce-mcp-server-scaffolding-and-conformance-tooling.md) | v0.1 | Implemented | Introduce MCP server scaffolding and conformance tooling |
| [ADR-0120](0120-implement-a-multi-provider-git-forge-mcp-server-for-github-and-gitlab.md) | v0.1 | Implemented | Implement a multi-provider Git-forge MCP server for GitHub and GitLab |
| [ADR-0121](0121-restrict-git-forge-write-and-private-access-by-visibility.md) | v0.1 | Implemented | Restrict git-forge write and private access by visibility |

## version 0.2

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0202](0202-introduce-logical-knowledge-domains.md) | v0.2 | Implemented | Introduce logical knowledge domains |
| [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md) | v0.2 | Implemented | Enforce knowledge authorization as policy intersection |
| [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md) | v0.2 | Implemented | Generalize the RAG platform to multiple isolated knowledge domains |
| [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md) | v0.2 | Implemented | Prefer indexed knowledge for read and live tools for freshness and write |
| [ADR-0208](0208-standardize-enterprise-tool-authentication-and-delegation.md) | v0.2 | Implemented | Standardize enterprise tool authentication and delegation |
| [ADR-0209](0209-introduce-project-scoped-agent-memory.md) | v0.2 | Implemented | Introduce project-scoped agent memory |
| [ADR-0211](0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md) | v0.2 | Implemented | Publicly-trusted wildcard TLS via cert-manager, Let's Encrypt and Route53 DNS-01 |
| [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md) | v0.2 | Implemented | Introduce persistent, navigable chat conversations |
| [ADR-0214](0214-refresh-agent-frontend-chrome-branding-footer-and-menu-icons.md) | v0.2 | Implemented | Refresh agent-frontend chrome: branding, footer and menu icons |
| [ADR-0215](0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md) | v0.2 | Implemented | Carry conversation history into agent prompts with budgeted compaction |
| [ADR-0216](0216-import-real-sxa-content-via-s3-into-mariadb-served-through-mcp-and-rag.md) | v0.2 | Superseded by ADR-0219 | Import real SXA content via S3 into MariaDB, served through MCP and RAG |
| [ADR-0217](0217-ingest-a-weekly-sxa-corpus-as-a-new-rag-domain.md) | v0.2 | Superseded by ADR-0219 | Ingest a weekly SXA corpus as a new RAG domain |
| [ADR-0219](0219-serve-sxa-only-as-a-historical-rag-corpus.md) | v0.2 | Implemented | Serve SXA only as a pre-2021 historical RAG corpus |
| [ADR-0354](0354-add-ansible-automation-platform-as-a-day-1-component.md) | v0.2 | Implemented | Add Ansible Automation Platform as a new Day 1 component |

## version 0.3

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0301](0301-introduce-lora-and-peft-model-customization.md) | v0.3 | Superseded by ADR-0526 | Introduce LoRA and PEFT model customization |
| [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md) | v0.3 | Superseded by ADR-0526 | Build dataset-to-model MLOps pipelines |
| [ADR-0303](0303-support-dynamic-lora-adapter-loading.md) | v0.3 | Superseded by ADR-0526 | Support dynamic LoRA adapter loading |
| [ADR-0304](0304-optimize-model-selection-using-quality-cost-and-latency.md) | v0.3 | Implemented | Optimize model selection using quality cost and latency |
| [ADR-0305](0305-introduce-automated-model-benchmarking.md) | v0.3 | Implemented | Introduce automated model benchmarking |
| [ADR-0307](0307-support-self-service-agent-onboarding.md) | v0.4 | Proposed | Support self-service agent onboarding |
| [ADR-0308](0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md) | v0.3 | Implemented | Expand agent lifecycle management through the AIAgent Operator |
| [ADR-0309](0309-introduce-policy-driven-autonomous-optimization.md) | v0.3 | Partially implemented | Introduce policy-driven autonomous optimization |
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
| [ADR-0320](0320-pre-provision-openshift-users-rbac-and-console-favorites-via-keycloak.md) | v0 | Superseded by ADR-0332 (Deprecated) | Pre-provision OpenShift users, RBAC and Console favorites via Keycloak |
| [ADR-0321](0321-delegate-kueue-lifecycle-to-the-red-hat-build-of-kueue-operator.md) | v0 | Implemented | Delegate Kueue lifecycle to the Red Hat build of Kueue Operator |
| [ADR-0322](0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md) | v0.1 | Implemented | Migrate from Llama Stack configuration to the OpenShift AI OGX Operator |
| [ADR-0323](0323-establish-canonical-generated-and-validated-platform-documentation.md) | v0 | Implemented | Establish canonical generated and validated platform documentation |
| [ADR-0324](0324-reconcile-the-ci-build-inventory-with-the-repository-component-lifecycle.md) | v0 | Implemented | Reconcile the CI build inventory with the repository component lifecycle |
| [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md) | v0.3 | Implemented | Generalize the Tekos vertical slice to the four remaining agents |
| [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md) | v0.3 | Implemented | Define the AIAgent CRD reconciliation contract before implementing the operator |
| [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) | v0 | Superseded by ADR-0331 | Separate the OpenShift AI control plane from AI build and run workload namespaces |
| [ADR-0329](0329-consolidate-agent-workloads-into-the-shared-zuno-ai-run-namespace.md) | v0 | Implemented | Consolidate agent workloads into the shared zuno-ai-run namespace |
| [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md) | v0.1 | Implemented | Integrate the rag-ingestion pipeline as a Day 1 component with persona-scoped Confluence access |
| [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md) | v0 | Implemented | Revert OpenShift AI to the default applications namespace |
| [ADR-0332](0332-remove-console-favorites-provisioning.md) | v0 | Deprecated | Remove Console favorites provisioning |
| [ADR-0333](0333-separate-product-managed-ai-infrastructure-from-zuno-build-run-and-shared-platform-namespaces.md) | v0 | Implemented | Separate product-managed AI infrastructure from Zuno build, run, and shared platform namespaces |
| [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md) | v0.3 | Implemented | Extend business-role authorization with CDP and scoped capabilities |
| [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md) | v0.3 | Implemented | Support multiple agent graph shapes in Agent Runtime |
| [ADR-0343](0343-complete-the-maas-and-ray-prerequisites-on-the-datasciencecluster.md) | v0.1 | Implemented | Complete the MaaS and Ray prerequisites on the DataScienceCluster |
| [ADR-0344](0344-track-blocked-resources-and-add-a-day-0-reconcile-verb.md) | v0.1 | Implemented | Track blocked resources and add a Day 0 reconcile verb |
| [ADR-0345](0345-make-self-generated-vault-credentials-idempotent.md) | v0.1 | Implemented | Make self-generated Vault credentials idempotent across ansible re-runs |
| [ADR-0346](0346-trust-the-ingress-router-ca-and-absorb-the-startx-cluster-auth-oauth-settings.md) | v0.1 | Implemented (CA source corrected by ADR-0347) | Trust the ingress router CA and absorb the startx cluster-auth OAuth settings |
| [ADR-0347](0347-trust-the-vault-pki-root-for-the-oauth-openid-idp.md) | v0.1 | Implemented | Trust the Vault PKI root for the OAuth OpenID IDP |
| [ADR-0349](0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md) | v0.1 | Implemented | Restructure demo personas, ocp-* cluster-access groups and two new agents |
| [ADR-0350](0350-provide-an-aiagent-kubernetes-crd-and-operator.md) | v0.3 | Implemented | Provide an AIAgent Kubernetes CRD and operator |
| [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md) | v0.3 | Implemented (2026-08-26; amended same day by WP-083 - two permanent MIG nodes, see decisions 5 and 7) | Share RTX PRO 6000 GPUs via NVIDIA MIG with scale-from-zero burst capacity |
| [ADR-0353](../roadmap/adr-decisions-v0.3.md#adr-0353-support-an-optional-external-registry-as-the-first-party-runtime-image-source) | v0.3 | Proposed | Support an optional external registry as the first-party runtime image source |
| [ADR-0355](0355-expose-aap-audits-to-agents-through-an-mcp-aap-server.md) | v0.3 | Implemented | Expose AAP audits to agents through an mcp-aap server |
| [ADR-0532](0532-accept-knowledge-adv-as-sourceless-pending-a-replacement-adapter.md) | v0.3 | Implemented | Accept `knowledge.adv` as sourceless pending a replacement adapter |

## version 0.4

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0401](../roadmap/adr-decisions-v0.4.md#adr-0401-introduce-agent-to-agent-communication) | v0.4 | Proposed | Introduce agent-to-agent communication |
| [ADR-0402](../roadmap/adr-decisions-v0.4.md#adr-0402-adopt-a2a-as-the-inter-agent-protocol) | v0.4 | Proposed | Adopt A2A as the inter-agent protocol |
| [ADR-0403](../roadmap/adr-decisions-v0.4.md#adr-0403-propagate-user-identity-across-agent-to-agent-calls) | v0.4 | Proposed | Propagate user identity across agent-to-agent calls |
| [ADR-0404](../roadmap/adr-decisions-v0.4.md#adr-0404-introduce-controlled-shared-agent-memory) | v0.4 | Proposed | Introduce controlled shared agent memory |
| [ADR-0405](../roadmap/adr-decisions-v0.4.md#adr-0405-expose-agent-delegation-traces-to-users) | v0.4 | Proposed | Expose agent delegation traces to users |
| [ADR-0406](../roadmap/adr-decisions-v0.4.md#adr-0406-limit-recursive-agent-delegation) | v0.4 | Proposed | Limit recursive agent delegation |
| [ADR-0407](../roadmap/adr-decisions-v0.4.md#adr-0407-add-specialized-task-oriented-frontend-views) | v0.4 | Proposed | Add specialized task-oriented frontend views |
| [ADR-0408](../roadmap/adr-decisions-v0.4.md#adr-0408-automate-removal-of-inaccessible-private-rag-content) | v0.4 | Proposed | Automate removal of inaccessible private RAG content |
| [ADR-0409](../roadmap/adr-decisions-v0.4.md#adr-0409-introduce-advanced-human-approval-workflows) | v0.4 | Proposed | Introduce advanced human approval workflows |
| [ADR-0410](0410-expand-the-agent-catalog-beyond-the-initial-five-agents.md) | v0.4 | Proposed | Expand the agent catalog beyond the initial five agents |
| [ADR-0411](0411-trust-the-vault-pki-root-for-the-tekos-frontend-oidc-client.md) | v0.4 | Implemented | Trust the Vault PKI root in every agent frontend's OIDC client |
| [ADR-0412](0412-serve-gpt-oss-20b-on-the-unmanaged-full-gpu-node.md) | v0.4 | Superseded by ADR-0414 | Serve gpt-oss-20b on the unmanaged full-GPU node |
| [ADR-0413](0413-consolidate-grafana-dashboards-into-six-platform-views.md) | v0.4 | Implemented | Consolidate Grafana dashboards into six platform views |
| [ADR-0414](0414-consolidate-zuno-ai-run-into-three-tiered-mig-predictors.md) | v0.4 | Implemented | Consolidate zuno-ai-run into three tiered MIG predictors |
| [ADR-0415](0415-consume-stable-diffusion-xl-via-ovhcloud-ai-endpoints.md) | v0.4 | Implemented | Consume stable-diffusion-xl via OVHcloud AI Endpoints |
| [ADR-0416](0416-consume-gpt-oss-120b-via-ovhcloud-ai-endpoints.md) | v0.4 | Implemented | Consume gpt-oss-120b via OVHcloud AI Endpoints |
| [ADR-0417](0417-consume-codestral-via-mistral-api.md) | v0.4 | Implemented | Consume Codestral via the Mistral API |
| [ADR-0418](0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md) | v0.4 | Implemented | Execute Day 0 and Day 1 operations as AAP Job Templates |
| [ADR-0419](0419-split-model-preference-into-preferred-fallback-with-prompt-slot-overrides.md) | v0.4 | Implemented | Split model preference into preferred/fallback, with prompt-slot overrides |
| [ADR-0420](0420-sign-supply-chain-artifacts-in-cluster-with-vault-transit.md) | v0.4 | Implemented | Sign supply-chain artifacts in-cluster with Vault Transit |
| [ADR-0421](0421-reshape-day-0-day-1-boundaries-around-always-on-infra.md) | v0.4 | Implemented | Reshape Day 0/Day 1 boundaries around an "always-on infra" core |
| [ADR-0516](0516-generate-diagrams-with-self-hosted-mermaid-rendering.md) | v0.4 | Implemented | Generate diagrams with self-hosted Mermaid rendering, alongside SDXL image generation |
| [ADR-0518](0518-modernize-local-models-qwen36-chat-qwen3-embeddings-qwen35-training.md) | v0.4 | Implemented | Modernize the local model fleet: Qwen3.6-27B chat, Qwen3-Embedding-0.6B RAG, Qwen3.5-9B training base |
| [ADR-0519](0519-parallelize-and-shortcut-the-rag-ingestion-fetch-stages.md) | v0.4 | Implemented | Parallelize and short-circuit the RAG ingestion fetch stages (fetch-redhat, fetch-sxa) |
| [ADR-0520](0520-parallelize-the-detect-changes-read-stage.md) | v0.4 | Implemented | Parallelize the detect-changes read stage's per-document S3 GETs |
| [ADR-0524](0524-integrate-openshift-lightspeed-with-the-zuno-ai-platform.md) | v0.4 | Implemented | Integrate OpenShift Lightspeed as a consumer of the Zuno AI platform |
| [ADR-0525](0525-batch-index-pgvector-writes-and-size-ivfflat-from-real-rows.md) | v0.4 | Implemented | Batch index-pgvector writes and size the ivfflat index from real row counts |
| [ADR-0529](0529-stop-the-pgo-external-secrets-write-loop-on-pguser-secrets.md) | v0.4 | Implemented | Stop the PGO/External-Secrets write loop on pguser secrets |
| [ADR-0526](0526-fine-tune-and-serve-a-french-urban-register-model-variant.md) | v0.4 | Implemented | Fine-tune and serve a French urban-register model variant (`-wesh`) beside its base |
| [ADR-0527](0527-introduce-the-project-as-the-sharing-and-context-boundary.md) | v0.4 | Implemented | Introduce the project as the sharing and context boundary |
| [ADR-0528](0528-rekey-project-binding-quota-and-telemetry-onto-the-zuno-project-id.md) | v0.4 | Implemented | Re-key project binding, quota and telemetry onto the Zuno project id |
| [ADR-0530](0530-reconcile-keycloak-clients-instead-of-relying-on-a-create-only-realm-import.md) | v0.4 | Implemented | Reconcile Keycloak clients instead of relying on a create-only realm import |
| [ADR-0531](0531-promote-qwen3-5-9b-as-the-fleet-wide-default-and-extend-ovhcloud-reasoning-access.md) | v0.4 | Implemented | Promote qwen3.5-9b to the fleet-wide default model, extend OVHcloud reasoning access from Arkos to Tekos/Comage |

## version 0.5

Goal: make the OpenShift AI MaaS governance plane live and route agent model calls through it end-to-end.

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md) | v0.5 | Implemented | Complete the OpenShift AI MaaS governance plane integration |
| [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md) | v0.5 | Implemented | Define OKF quota policy enforced via Kuadrant |
| [ADR-0512](0512-introduce-project-bound-tasks-with-salesforce-verified-context.md) | v0.5 | Superseded by ADR-0528 | Introduce project-bound tasks with Salesforce-verified context |
| [ADR-0521](0521-route-local-model-traffic-through-maas.md) | v0.5 | Implemented | Route ai-gateway's local model traffic through MaaS |
| [ADR-0522](0522-enable-openshift-ai-monitoring-stack-side-by-side.md) | v0.5 | Implemented | Enable OpenShift AI's built-in monitoring stack, side-by-side with the existing observability stack |
| [ADR-0523](0523-dual-export-traces-into-the-rhoai-monitoring-stack.md) | v0.5 | Implemented | Dual-export traces into the RHOAI monitoring stack |

## version 0.6

Goal: close out the roadmap-reprioritization cluster left over from v0.7 - source-specific ingestion cadences, Salesforce/SXA-legacy separation, and the now-superseded role-based conversation sharing. All four items are already delivered; this band exists to formalize their retargeted status. It reuses the band vacated by ADR-0517's move to v0.8.

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0105](0105-automate-source-specific-knowledge-ingestion.md) | v0.6 | Partially implemented | Automate source-specific knowledge ingestion |
| [ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md) | v0.6 | Partially implemented | Separate current Salesforce knowledge from legacy SXA |
| [ADR-0213](0213-introduce-role-based-conversation-sharing.md) | v0.6 | Superseded by ADR-0527 | Introduce role-based conversation sharing between colleagues |
| [ADR-0218](0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md) | v0.6 | Implemented | Drop the Aramis ingestion adapter and defer the Salesforce ingestion cadence |

## version 0.7

Goal: automate the release/supply-chain pipeline using GitHub Actions (build, sign, publish, promote).

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0111](0111-strengthen-secnumcloud-oriented-security-controls.md) | v0.7 | Deferred | Strengthen SecNumCloud-oriented security controls |
| [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md) | v0.7 | Deferred | Use immutable and verifiable software supply chain artifacts |

Also carried in v0.7, as a separate large-scope effort unrelated to the GitHub-Actions goal above and not yet started:

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md) | v0.7 | Proposed | Run day-0 platform services in internal or external mode |

## version 0.8

Goal: prove the platform's Day 0–3 automation is complete and portable by redeploying the full stack from scratch on a new cluster (retargeted from v0.6, deprioritized behind v0.7's release-automation work).

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0517](0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md) | v0.8 | Proposed | Redeploy the full platform from scratch on a new demo333 cluster |
| [ADR-0533](0533-consolidate-advantage-and-finage-non-promotion-into-a-dedicated-decision.md) | v0.8 | Proposed | Consolidate Advantage's and Finage's non-promotion into a dedicated decision |

## OKF stream

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0501](0501-establish-the-okf-stream-with-its-own-milestones-and-roadmap.md) | OKF v0.1 | Accepted | Establish the OKF stream with its own milestones and roadmap |
| [ADR-0502](0502-formalize-the-two-stage-agent-maturity-model.md) | OKF v0.1 | Implemented | Formalize the two-stage agent maturity model |
| [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md) | OKF v0.1 | Implemented | Make each OKF bundle state its complete authorization contract |
| [ADR-0504](0504-define-the-agent-tests-directory-structure-and-promotion-gate.md) | OKF v0.1 | Implemented | Define the agent tests directory structure and promotion gate |
| [ADR-0505](0505-open-okf-tasks-as-concurrent-per-agent-frontend-tabs.md) | OKF v0.1 | Superseded by ADR-0515 (Abandoned before implementation) | Open OKF tasks as concurrent per-agent frontend tabs |
| [ADR-0506](0506-extract-okf-content-into-a-standalone-zuno-okf-repository.md) | OKF v0.2 | Proposed | Extract OKF content into a standalone zuno-okf repository |
| [ADR-0507](0507-consume-the-zuno-okf-repository-through-a-single-pinned-reference.md) | OKF v0.2 | Proposed | Consume the zuno-okf repository through a single pinned reference |
| [ADR-0508](0508-isolate-okf-parsing-behind-per-component-adaptation-hooks.md) | OKF v0.2 | Proposed | Isolate OKF parsing behind per-component adaptation hooks |
| [ADR-0509](0509-deliver-okf-content-as-mounted-versioned-artifacts.md) | OKF v0.3 | Proposed | Deliver OKF content as mounted versioned artifacts |
| [ADR-0510](0510-make-the-aiagent-operator-watch-the-zuno-okf-repository.md) | OKF v0.3 | Proposed | Make the AIAgent operator watch the zuno-okf repository |
| [ADR-0513](0513-give-okf-rag-tools-and-policies-directories-a-real-schema.md) | OKF v0.1 | Implemented | Give OKF rag/, tools/ and policies/ directories a real schema |
| [ADR-0514](0514-generalize-arkos-plan-draft-write-for-multiple-document-kinds.md) | OKF v0.1 | Implemented | Generalize Arkos's plan_draft_write shape for multiple document kinds |
| [ADR-0515](0515-per-conversation-tabs-one-browser-tab-per-agent.md) | OKF v0.1 | Implemented | Open per-conversation tabs with one browser tab per agent |

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
