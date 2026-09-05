# Architecture Decision Records

ADRs are immutable decision records. When a decision changes, a new ADR
supersedes the previous record instead of rewriting history. Only a record's
`**Status:**` line, its dated gap/progress lists and stub-promotion pointers
are editable.

**This index is the sole authority for ADR status.** Records are grouped by
their `**Target:**` version, so the section heading *is* the target and no
`Target` column repeats it. What each version is *for* lives in
[versions.md](../roadmap/versions.md); the work packages that implement these
decisions live in the
[implementation roadmap](../roadmap/implementation-roadmap.md); how the index
came to look like this - renumberings, retargetings, band changes - lives in
[CHANGELOG.md](CHANGELOG.md).

## Conventions

### Status vocabulary

A closed set. `platform/docs/check_docs.py` rejects anything else, and checks
each row against the ADR body it links to.

| Status | Meaning |
|---|---|
| `Proposed` | Recorded, not yet agreed. |
| `Accepted` | Agreed; implementation not complete. |
| `Partially implemented` | Repo work merged, operator/live steps outstanding. |
| `Implemented` | In effect, and the tree reflects it. |
| `Deferred` | Agreed but blocked outside this repository. |
| `Deprecated` | Withdrawn with no successor record. |
| `Superseded by ADR-NNNN` | Replaced in full. Moves to [Retired](#retired). |
| `Superseded in part by ADR-NNNN` | Partly replaced. **Stays in its version band.** |

Qualifications, dates and evidence pointers belong in the ADR body, not in the
index cell - the index carries the bare status phrase so the tables stay
scannable.

### How a decision changes

Three distinct mechanisms, all in use:

1. **Full supersession** - the successor replaces the whole decision. The
   record's status becomes `Superseded by ADR-NNNN` and it leaves its version
   band for [Retired](#retired).
2. **Partial supersession** - the successor replaces some clauses while others
   remain in force *as this record's own decisions*. Status becomes
   `Superseded in part by ADR-NNNN`, naming the residual scope, and the record
   **stays in its band**, because part of it is still live architecture.
   Clauses that migrate *into* the successor are not a partial supersession:
   ADR-0213's two surviving clauses are reused and extended by ADR-0527, so
   ADR-0213 is superseded in full.
3. **Dated correction note, no supersession** - when records contradict each
   other on a detail while their other decisions all stand. ADR-0518, ADR-0526
   and ADR-0531 disagreed on the fleet default model; only that role moved, so
   each body carries a dated correction note and all three keep
   `Status: Implemented`. Use this only when no decision clause is retired.

A superseding ADR must declare `Supersedes ADR-NNNN`, and the named record's
status must name it back. This reciprocity is enforced; the one standing
exception is recorded in the check itself (ADR-0303 names ADR-0526, which does
not name it back, and ADR-0526's body is immutable).

### Numbering

Sequential - a new ADR takes the next free number. **No band is reserved for
any stream.** The 05xx band was declared reserved for the OKF stream on
2026-08-18; 34 of its 42 records have nothing to do with OKF, so the
convention is retired rather than maintained artificially. Stream membership
is expressed by `Target`, not by number.

ADR-0541 was the sole gap in the 05xx band and has since been taken (see the
[change log](CHANGELOG.md)); there is no free gap currently reserved.
Renumbered records carry a `Renumbered:` line; a published ADR is never
renumbered to close a cosmetic gap.

### Stub records

Ten rows marked *(stub)* have no file of their own: their text lives in
`../roadmap/adr-decisions-v0.*.md` and the link points at the anchor. A stub
is promoted to a real file by Step 0 of the work package that implements it.

## v0

| ADR | Status | Decision |
|---|---|---|
| [ADR-0001](0001-use-a-monorepo-for-the-zuno-agent-platform.md) | Implemented | Use a monorepo for the Zuno agent platform |
| [ADR-0002](0002-use-openshift-4-20-and-openshift-ai-3-5-for-the-mvp.md) | Superseded in part by ADR-0319 | Use OpenShift 4.20 and OpenShift AI 3.5 for the MVP |
| [ADR-0003](0003-use-ansible-and-make-as-the-deployment-entry-point.md) | Implemented | Use Ansible and Make as the deployment entry point |
| [ADR-0004](0004-use-github-as-the-canonical-source-repository.md) | Implemented | Use GitHub as the canonical source repository |
| [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md) | Implemented | Use OKF v0.2 as the declarative agent definition contract |
| [ADR-0006](0006-extend-okf-with-zuno-agent-specific-metadata.md) | Implemented | Extend OKF with Zuno agent-specific metadata |
| [ADR-0007](0007-separate-agent-instances-from-reusable-platform-components.md) | Implemented | Separate agent instances from reusable platform components |
| [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md) | Implemented | Use one frontend and one BFF deployment per agent |
| [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md) | Implemented | Separate Agent Runtime from AI Inference Gateway |
| [ADR-0010](0010-introduce-a-central-mcp-gateway.md) | Implemented | Introduce a central MCP Gateway |
| [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md) | Implemented | Define tool authorization as policy intersection |
| [ADR-0012](0012-use-keycloak-as-the-central-identity-provider.md) | Implemented | Use Keycloak as the central identity provider |
| [ADR-0013](0013-propagate-end-user-identity-through-agent-calls.md) | Implemented | Propagate end-user identity through agent calls |
| [ADR-0014](0014-use-delegated-google-oauth-for-google-workspace-access.md) | Implemented | Use delegated Google OAuth for Google Workspace access |
| [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md) | Implemented | Use PostgreSQL and pgvector as the persistent data platform |
| [ADR-0017](0017-access-sales-data-through-controlled-mcp-tools.md) | Implemented | Access sales data through controlled MCP tools |
| [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md) | Implemented | Use OpenShift AI model serving for local inference |
| [ADR-0020](0020-support-both-local-and-external-llm-providers.md) | Implemented | Support both local and external LLM providers |
| [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md) | Implemented | Route models according to C1 C2 C3 classification |
| [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md) | Implemented | Use GitOps-managed declarative agent tasks and policies |
| [ADR-0024](0024-use-vault-for-application-secrets.md) | Implemented | Use Vault for application secrets |
| [ADR-0025](0025-keep-sensitive-and-real-commercial-data-outside-the-public-repository.md) | Implemented | Keep sensitive and real commercial data outside the public repository |
| [ADR-0027](0027-evaluate-every-agent-with-twenty-acceptance-scenarios.md) | Implemented | Evaluate every agent with twenty acceptance scenarios |
| [ADR-0028](0028-require-a-seventy-five-percent-evaluation-threshold.md) | Implemented | Require a seventy-five percent evaluation threshold |
| [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md) | Implemented | Instrument model usage costs and distributed traces |
| [ADR-0030](0030-use-a-command-dispatch-makefile-interface.md) | Implemented | Use a command-dispatch Makefile interface |
| [ADR-0031](0031-formalize-tekos-as-the-v0-vertical-slice.md) | Implemented | Formalize Tekos as the v0 vertical slice |
| [ADR-0032](0032-propagate-trusted-identity-end-to-end.md) | Implemented | Propagate trusted identity end to end |
| [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md) | Implemented | Derive user identity only from validated tokens |
| [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md) | Implemented | Compute effective classification from the complete context |
| [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md) | Implemented | Prevent restricted internal context from reaching external models |
| [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md) | Implemented | Enforce the complete MCP authorization intersection in the gateway |
| [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md) | Implemented | Protect MCP servers with network and workload identity boundaries |
| [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md) | Implemented | Use standards-compliant OKF v0.2 Markdown bundles |
| [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md) | Implemented | Make Agent Runtime execute the OKF agent contract |
| [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md) | Implemented | Separate agent entitlement from business role authorization |
| [ADR-0041](0041-remove-nominative-demo-identities-and-static-passwords-from-git.md) | Implemented | Remove nominative demo identities and static passwords from Git |
| [ADR-0044](0044-use-patternfly-react-for-the-agent-frontend.md) | Implemented | Use PatternFly React for the agent frontend |
| [ADR-0045](0045-stream-responses-end-to-end-with-sse.md) | Implemented | Stream responses end to end with SSE |
| [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md) | Implemented | Make RAG retrieval metadata-aware and bilingual |
| [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md) | Superseded in part by ADR-0317 | Manage the complete OpenShift AI prerequisite lifecycle |
| [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md) | Implemented | Discover supported operator channels and serving runtimes at deployment time |
| [ADR-0052](0052-harden-all-workloads-for-openshift-restricted-security-and-secnumcloud-objectives.md) | Implemented | Harden all workloads for OpenShift restricted security and SecNumCloud objectives |
| [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md) | Implemented | Make make check an end-to-end acceptance and security gate |
| [ADR-0054](0054-define-the-bff-contract-openapi-first.md) | Implemented | Define the BFF contract OpenAPI-first |
| [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) | Implemented | Restructure deployment into Day 0 / Day 1 sequencing |
| [ADR-0057](0057-introduce-day-2-agent-availability-test-and-stresstest-operations.md) | Implemented | Introduce Day 2 agent availability-test and stresstest operations |
| [ADR-0058](0058-aggregate-existing-test-content-into-a-bulk-interaction-stresstest.md) | Implemented | Aggregate existing test content into make d2 stresstest, with a bulk-interaction load mode |
| [ADR-0059](0059-auto-redeploy-on-in-cluster-build-via-image-triggers.md) | Implemented | Auto-redeploy consuming pods when an in-cluster build completes |
| [ADR-0060](0060-restructure-day-0-day-1-day-2-day-3-deployment-sequencing.md) | Implemented | Restructure deployment into Day 0 / Day 1 / Day 2 / Day 3 sequencing |
| [ADR-0310](0310-manage-static-kubernetes-resources-as-per-role-kustomize-directories.md) | Implemented | Manage static Kubernetes resources as per-role kustomize directories |
| [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md) | Implemented | Stop applying the root App-of-Apps from Ansible bootstrap tasks |
| [ADR-0312](0312-route-operator-installs-through-argocd-applications.md) | Implemented | Route operator installs through ArgoCD Applications |
| [ADR-0313](0313-move-day1-schema-jobs-and-llm-provider-secrets-behind-argocd.md) | Implemented | Move Day 1 schema Jobs and LLM provider secret seeding behind ArgoCD/Vault |
| [ADR-0314](0314-convert-admin-context-to-a-d0-d1-argocd-application-pair.md) | Implemented | Convert admin_context to a -d0/-d1 ArgoCD Application pair |
| [ADR-0315](0315-dedicated-keycloak-postgresql-database.md) | Implemented | Dedicated Keycloak database/role on the shared PostgreSQL cluster |
| [ADR-0316](0316-keycloak-route-tls-via-cert-manager.md) | Implemented | Keycloak's Route gets a cert-manager-issued certificate via a hand-authored Ingress |
| [ADR-0317](0317-install-connectivity-link-and-leaderworkerset-operators.md) | Implemented | Install the Red Hat Connectivity Link and LeaderWorkerSet operators as OpenShift AI prerequisites |
| [ADR-0318](0318-install-custom-metrics-autoscaler-and-jobset-operators.md) | Implemented | Install the Custom Metrics Autoscaler and JobSet operators as OpenShift AI prerequisites |
| [ADR-0319](0319-target-openshift-4-22.md) | Implemented | Target OpenShift 4.22 |
| [ADR-0320](0320-pre-provision-openshift-users-rbac-and-console-favorites-via-keycloak.md) | Superseded in part by ADR-0332 and ADR-0349 | Pre-provision OpenShift users, RBAC and Console favorites via Keycloak |
| [ADR-0321](0321-delegate-kueue-lifecycle-to-the-red-hat-build-of-kueue-operator.md) | Implemented | Delegate Kueue lifecycle to the Red Hat build of Kueue Operator |
| [ADR-0323](0323-establish-canonical-generated-and-validated-platform-documentation.md) | Implemented | Establish canonical generated and validated platform documentation |
| [ADR-0324](0324-reconcile-the-ci-build-inventory-with-the-repository-component-lifecycle.md) | Implemented | Reconcile the CI build inventory with the repository component lifecycle |
| [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) | Superseded in part by ADR-0331 and ADR-0548 | Separate the OpenShift AI control plane from AI build and run workload namespaces |
| [ADR-0329](0329-consolidate-agent-workloads-into-the-shared-zuno-ai-run-namespace.md) | Implemented | Consolidate agent workloads into the shared zuno-ai-run namespace |
| [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md) | Implemented | Revert OpenShift AI to the default applications namespace |
| [ADR-0333](0333-separate-product-managed-ai-infrastructure-from-zuno-build-run-and-shared-platform-namespaces.md) | Superseded in part by ADR-0548 | Separate product-managed AI infrastructure from Zuno build, run, and shared platform namespaces |

## v0.1

| ADR | Status | Decision |
|---|---|---|
| [ADR-0042](0042-use-opaque-browser-sessions-with-server-side-token-storage.md) | Implemented | Use opaque browser sessions with server-side token storage |
| [ADR-0043](0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md) | Implemented | Use standard MCP protocol behind the Zuno MCP Gateway |
| [ADR-0055](0055-repository-review-change-set-index.md) | Implemented | Repository review change-set index |
| [ADR-0101](0101-provide-ha-for-shared-agent-platform-services.md) | Implemented | Provide HA for shared agent platform services |
| [ADR-0102](0102-target-99-9-percent-platform-availability.md) | Implemented | Target 99.9 percent platform availability |
| [ADR-0103](0103-persist-resumable-long-running-agent-workflows.md) | Implemented | Persist resumable long-running agent workflows |
| [ADR-0104](0104-introduce-controlled-semantic-caching.md) | Implemented | Introduce controlled semantic caching |
| [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md) | Implemented | Enforce OKF bundle signing and validation |
| [ADR-0107](0107-introduce-automated-model-quality-gates.md) | Implemented | Introduce automated model quality gates |
| [ADR-0108](0108-automate-model-evaluation-with-lm-eval.md) | Implemented | Automate model evaluation with LM-Eval |
| [ADR-0109](0109-implement-source-freshness-and-trust-scoring.md) | Implemented | Implement source freshness and trust scoring |
| [ADR-0110](0110-automate-document-acl-synchronization.md) | Implemented | Automate document ACL synchronization |
| [ADR-0112](0112-implement-production-grade-backup-and-recovery.md) | Implemented | Implement production-grade backup and recovery |
| [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md) | Implemented | Decouple logical tool capabilities from physical backend bindings |
| [ADR-0117](0117-implement-confluence-as-the-first-real-external-mcp-integration.md) | Implemented | Implement Confluence as the first real external MCP integration |
| [ADR-0118](0118-keep-the-ai-gateway-as-policy-router-and-defer-maas-delegation.md) | Implemented | Keep the AI Gateway as policy router and defer MaaS delegation to the governance plane |
| [ADR-0119](0119-introduce-mcp-server-scaffolding-and-conformance-tooling.md) | Implemented | Introduce MCP server scaffolding and conformance tooling |
| [ADR-0120](0120-implement-a-multi-provider-git-forge-mcp-server-for-github-and-gitlab.md) | Implemented | Implement a multi-provider Git-forge MCP server for GitHub and GitLab |
| [ADR-0121](0121-restrict-git-forge-write-and-private-access-by-visibility.md) | Implemented | Restrict git-forge write and private access by visibility |
| [ADR-0322](0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md) | Implemented | Migrate from Llama Stack configuration to the OpenShift AI OGX Operator |
| [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md) | Implemented | Integrate the rag-ingestion pipeline as a Day 1 component with persona-scoped Confluence access |
| [ADR-0343](0343-complete-the-maas-and-ray-prerequisites-on-the-datasciencecluster.md) | Implemented | Complete the MaaS and Ray prerequisites on the DataScienceCluster |
| [ADR-0344](0344-track-blocked-resources-and-add-a-day-0-reconcile-verb.md) | Implemented | Track blocked resources and add a Day 0 reconcile verb |
| [ADR-0345](0345-make-self-generated-vault-credentials-idempotent.md) | Implemented | Make self-generated Vault credentials idempotent across ansible re-runs |
| [ADR-0346](0346-trust-the-ingress-router-ca-and-absorb-the-startx-cluster-auth-oauth-settings.md) | Implemented | Trust the ingress router CA and absorb the startx cluster-auth OAuth settings |
| [ADR-0347](0347-trust-the-vault-pki-root-for-the-oauth-openid-idp.md) | Implemented | Trust the Vault PKI root for the OAuth OpenID IDP |
| [ADR-0349](0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md) | Implemented | Restructure demo personas, ocp-* cluster-access groups and two new agents |

## v0.2

| ADR | Status | Decision |
|---|---|---|
| [ADR-0202](0202-introduce-logical-knowledge-domains.md) | Implemented | Introduce logical knowledge domains |
| [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md) | Implemented | Enforce knowledge authorization as policy intersection |
| [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md) | Superseded in part by ADR-0218 | Generalize the RAG platform to multiple isolated knowledge domains |
| [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md) | Implemented | Prefer indexed knowledge for read and live tools for freshness and write |
| [ADR-0208](0208-standardize-enterprise-tool-authentication-and-delegation.md) | Implemented | Standardize enterprise tool authentication and delegation |
| [ADR-0209](0209-introduce-project-scoped-agent-memory.md) | Implemented | Introduce project-scoped agent memory |
| [ADR-0211](0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md) | Implemented | Publicly-trusted wildcard TLS via cert-manager, Let's Encrypt and Route53 DNS-01 |
| [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md) | Implemented | Introduce persistent, navigable chat conversations |
| [ADR-0214](0214-refresh-agent-frontend-chrome-branding-footer-and-menu-icons.md) | Implemented | Refresh agent-frontend chrome: branding, footer and menu icons |
| [ADR-0215](0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md) | Implemented | Carry conversation history into agent prompts with budgeted compaction |
| [ADR-0219](0219-serve-sxa-only-as-a-historical-rag-corpus.md) | Implemented | Serve SXA only as a pre-2021 historical RAG corpus |
| [ADR-0354](0354-add-ansible-automation-platform-as-a-day-1-component.md) | Implemented | Add Ansible Automation Platform as a new Day 1 component |

## v0.3

| ADR | Status | Decision |
|---|---|---|
| [ADR-0301](0301-introduce-lora-and-peft-model-customization.md) | Superseded in part by ADR-0526 | Introduce LoRA and PEFT model customization |
| [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md) | Superseded in part by ADR-0526 | Build dataset-to-model MLOps pipelines |
| [ADR-0304](0304-optimize-model-selection-using-quality-cost-and-latency.md) | Implemented | Optimize model selection using quality cost and latency |
| [ADR-0305](0305-introduce-automated-model-benchmarking.md) | Implemented | Introduce automated model benchmarking |
| [ADR-0308](0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md) | Implemented | Expand agent lifecycle management through the AIAgent Operator |
| [ADR-0309](0309-introduce-policy-driven-autonomous-optimization.md) | Implemented | Introduce policy-driven autonomous optimization |
| [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md) | Implemented | Generalize the Tekos vertical slice to the four remaining agents |
| [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md) | Implemented | Define the AIAgent CRD reconciliation contract before implementing the operator |
| [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md) | Implemented | Extend business-role authorization with CDP and scoped capabilities |
| [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md) | Implemented | Support multiple agent graph shapes in Agent Runtime |
| [ADR-0350](0350-provide-an-aiagent-kubernetes-crd-and-operator.md) | Implemented | Provide an AIAgent Kubernetes CRD and operator |
| [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md) | Implemented | Share RTX PRO 6000 GPUs via NVIDIA MIG with scale-from-zero burst capacity |
| [ADR-0353](../roadmap/adr-decisions-v0.3.md#adr-0353-support-an-optional-external-registry-as-the-first-party-runtime-image-source) *(stub)* | Proposed | Support an optional external registry as the first-party runtime image source |
| [ADR-0355](0355-expose-aap-audits-to-agents-through-an-mcp-aap-server.md) | Implemented | Expose AAP audits to agents through an mcp-aap server |
| [ADR-0532](0532-accept-knowledge-adv-as-sourceless-pending-a-replacement-adapter.md) | Implemented | Accept `knowledge.adv` as sourceless pending a replacement adapter |

## v0.4

| ADR | Status | Decision |
|---|---|---|
| [ADR-0401](../roadmap/adr-decisions-v0.4.md#adr-0401-introduce-agent-to-agent-communication) *(stub)* | Proposed | Introduce agent-to-agent communication |
| [ADR-0402](../roadmap/adr-decisions-v0.4.md#adr-0402-adopt-a2a-as-the-inter-agent-protocol) *(stub)* | Proposed | Adopt A2A as the inter-agent protocol |
| [ADR-0403](../roadmap/adr-decisions-v0.4.md#adr-0403-propagate-user-identity-across-agent-to-agent-calls) *(stub)* | Proposed | Propagate user identity across agent-to-agent calls |
| [ADR-0404](../roadmap/adr-decisions-v0.4.md#adr-0404-introduce-controlled-shared-agent-memory) *(stub)* | Proposed | Introduce controlled shared agent memory |
| [ADR-0405](../roadmap/adr-decisions-v0.4.md#adr-0405-expose-agent-delegation-traces-to-users) *(stub)* | Proposed | Expose agent delegation traces to users |
| [ADR-0406](../roadmap/adr-decisions-v0.4.md#adr-0406-limit-recursive-agent-delegation) *(stub)* | Proposed | Limit recursive agent delegation |
| [ADR-0407](../roadmap/adr-decisions-v0.4.md#adr-0407-add-specialized-task-oriented-frontend-views) *(stub)* | Proposed | Add specialized task-oriented frontend views |
| [ADR-0408](../roadmap/adr-decisions-v0.4.md#adr-0408-automate-removal-of-inaccessible-private-rag-content) *(stub)* | Proposed | Automate removal of inaccessible private RAG content |
| [ADR-0409](../roadmap/adr-decisions-v0.4.md#adr-0409-introduce-advanced-human-approval-workflows) *(stub)* | Proposed | Introduce advanced human approval workflows |
| [ADR-0411](0411-trust-the-vault-pki-root-for-the-tekos-frontend-oidc-client.md) | Implemented | Trust the Vault PKI root in every agent frontend's OIDC client |
| [ADR-0413](0413-consolidate-grafana-dashboards-into-six-platform-views.md) | Implemented | Consolidate Grafana dashboards into six platform views |
| [ADR-0414](0414-consolidate-zuno-ai-run-into-three-tiered-mig-predictors.md) | Implemented | Consolidate zuno-ai-run into three tiered MIG predictors |
| [ADR-0415](0415-consume-stable-diffusion-xl-via-ovhcloud-ai-endpoints.md) | Implemented | Consume stable-diffusion-xl via OVHcloud AI Endpoints |
| [ADR-0416](0416-consume-gpt-oss-120b-via-ovhcloud-ai-endpoints.md) | Implemented | Consume gpt-oss-120b via OVHcloud AI Endpoints |
| [ADR-0417](0417-consume-codestral-via-mistral-api.md) | Implemented | Consume Codestral via the Mistral API |
| [ADR-0418](0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md) | Implemented | Execute Day 0 and Day 1 operations as AAP Job Templates |
| [ADR-0419](0419-split-model-preference-into-preferred-fallback-with-prompt-slot-overrides.md) | Implemented | Split model preference into preferred/fallback, with prompt-slot overrides |
| [ADR-0421](0421-reshape-day-0-day-1-boundaries-around-always-on-infra.md) | Implemented | Reshape Day 0/Day 1 boundaries around an "always-on infra" core |
| [ADR-0516](0516-generate-diagrams-with-self-hosted-mermaid-rendering.md) | Implemented | Generate diagrams with self-hosted Mermaid rendering, alongside SDXL image generation |
| [ADR-0518](0518-modernize-local-models-qwen36-chat-qwen3-embeddings-qwen35-training.md) | Implemented | Modernize the local model fleet: Qwen3.6-27B chat, Qwen3-Embedding-0.6B RAG, Qwen3.5-9B training base |
| [ADR-0519](0519-parallelize-and-shortcut-the-rag-ingestion-fetch-stages.md) | Implemented | Parallelize and short-circuit the RAG ingestion fetch stages (fetch-redhat, fetch-sxa) |
| [ADR-0520](0520-parallelize-the-detect-changes-read-stage.md) | Implemented | Parallelize the detect-changes read stage's per-document S3 GETs |
| [ADR-0524](0524-integrate-openshift-lightspeed-with-the-zuno-ai-platform.md) | Implemented | Integrate OpenShift Lightspeed as a consumer of the Zuno AI platform |
| [ADR-0525](0525-batch-index-pgvector-writes-and-size-ivfflat-from-real-rows.md) | Implemented | Batch index-pgvector writes and size the ivfflat index from real row counts |
| [ADR-0526](0526-fine-tune-and-serve-a-french-urban-register-model-variant.md) | Implemented | Fine-tune and serve a French urban-register model variant (`-wesh`) beside its base |
| [ADR-0527](0527-introduce-the-project-as-the-sharing-and-context-boundary.md) | Implemented | Introduce the project as the sharing and context boundary |
| [ADR-0528](0528-rekey-project-binding-quota-and-telemetry-onto-the-zuno-project-id.md) | Implemented | Re-key project binding, quota and telemetry onto the Zuno project id |
| [ADR-0529](0529-stop-the-pgo-external-secrets-write-loop-on-pguser-secrets.md) | Implemented | Stop the PGO/External-Secrets write loop on pguser secrets |
| [ADR-0530](0530-reconcile-keycloak-clients-instead-of-relying-on-a-create-only-realm-import.md) | Implemented | Reconcile Keycloak clients instead of relying on a create-only realm import |
| [ADR-0531](0531-promote-qwen3-5-9b-as-the-fleet-wide-default-and-extend-ovhcloud-reasoning-access.md) | Implemented | Promote qwen3.5-9b to the fleet-wide default model, extend OVHcloud reasoning access from Arkos to Tekos/Comage |
| [ADR-0536](0536-live-node-failover-drill-for-qwen-model-fallback.md) | Implemented | Live GPU-node failover drill for the qwen-normal/qwen-wesh fallback, and a reusable `make d3 scenario-failover-node` command |
| [ADR-0544](0544-bound-every-model-call-at-both-ends.md) | Implemented | Bound every model call at both ends - a prompt-window clamp and a declarative max_tokens |

## v0.5

| ADR | Status | Decision |
|---|---|---|
| [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md) | Implemented | Complete the OpenShift AI MaaS governance plane integration |
| [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md) | Implemented | Define OKF quota policy enforced via Kuadrant |
| [ADR-0512](0512-introduce-project-bound-tasks-with-salesforce-verified-context.md) | Superseded in part by ADR-0528 | Introduce project-bound tasks with Salesforce-verified context |
| [ADR-0521](0521-route-local-model-traffic-through-maas.md) | Implemented | Route ai-gateway's local model traffic through MaaS |
| [ADR-0522](0522-enable-openshift-ai-monitoring-stack-side-by-side.md) | Implemented | Enable OpenShift AI's built-in monitoring stack, side-by-side with the existing observability stack |
| [ADR-0523](0523-dual-export-traces-into-the-rhoai-monitoring-stack.md) | Implemented | Dual-export traces into the RHOAI monitoring stack |
| [ADR-0537](0537-integrate-rhoai-hardware-profiles-and-maas-external-models.md) | Implemented | Integrate RHOAI HardwareProfiles for local models |
| [ADR-0543](0543-propagate-a-per-run-id-across-every-service-span.md) | Implemented | Propagate a per-run id across every service span (documents work implemented 2026-08-23 whose ADR was never written) |

## v0.6

| ADR | Status | Decision |
|---|---|---|
| [ADR-0105](0105-automate-source-specific-knowledge-ingestion.md) | Superseded in part by ADR-0218 | Automate source-specific knowledge ingestion |
| [ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md) | Implemented | Separate current Salesforce knowledge from legacy SXA |
| [ADR-0218](0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md) | Implemented | Drop the Aramis ingestion adapter and defer the Salesforce ingestion cadence |

## v0.7

| ADR | Status | Decision |
|---|---|---|
| [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md) | Deferred | Use immutable and verifiable software supply chain artifacts |
| [ADR-0534](0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md) | Implemented | Integrate TrustyAI for AI evaluation and guardrails |
| [ADR-0538](0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md) | Accepted | Adopt RHOAI 3.5 workload surfaces - MLflow tracking, queued workloads, training-jobs UI |
| [ADR-0539](0539-delegate-lora-training-compute-to-a-kfp-submitted-trainjob.md) | Implemented | Delegate LoRA training compute to a KFP-submitted Kubeflow TrainJob |
| [ADR-0540](0540-express-guardrail-policy-as-nemo-rails-configuration.md) | Implemented | Express guardrail policy as NeMo rails configuration, not in-image detector parameters |
| [ADR-0541](0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md) | Proposed | Integrate mistral and gpt-oss-120b as MaaS ExternalModels |
| [ADR-0542](0542-autoscale-one-served-model-through-llminferenceservice-spec-scaling.md) | Implemented | Autoscale a served model through LLMInferenceService spec.scaling |
| [ADR-0545](0545-scope-remaining-rhoai-kubeflow-component-adoption.md) | Accepted | Scope the remaining RHOAI/Kubeflow component adoption - finalize TrainJob, explore Kueue priority, evaluate InferenceGraph, exclude NIM |

## v0.8

| ADR | Status | Decision |
|---|---|---|
| [ADR-0517](0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md) | Proposed | Redeploy the full platform from scratch on a new demo333 cluster |
| [ADR-0533](0533-consolidate-advantage-and-finage-non-promotion-into-a-dedicated-decision.md) | Implemented | Consolidate Advantage's and Finage's non-promotion into a dedicated decision |
| [ADR-0546](0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md) | Accepted | Introduce a cross-cluster source bucket (`zuno-demo-sources`) and per-cluster S3 bucket convention (`zuno-<cluster>-xxx`) |
| [ADR-0547](0547-parameterize-every-cluster-specific-value-in-ansible.md) | Proposed | Parameterize every cluster-specific value in Ansible, and seed it through Vault when secret |
| [ADR-0548](0548-remove-the-unused-zuno-ai-platform-reserved-namespace.md) | Implemented | Remove the unused zuno-ai-platform reserved namespace |

## v0.9

| ADR | Status | Decision |
|---|---|---|
| [ADR-0307](0307-support-self-service-agent-onboarding.md) | Proposed | Support self-service agent onboarding |
| [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md) | Proposed | Run day-0 platform services in internal or external mode |
| [ADR-0410](0410-expand-the-agent-catalog-beyond-the-initial-five-agents.md) | Proposed | Expand the agent catalog beyond the initial five agents |
| [ADR-0535](0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md) | Implemented | Adopt RHTAS as the artifact trust and supply-chain service |
| [ADR-0549](0549-close-the-secnumcloud-supply-chain-gap-with-an-in-cluster-release-ledger.md) | Accepted | Close ADR-0111's last SecNumCloud gap with an in-cluster release ledger |

## v0.10

| ADR | Status | Decision |
|---|---|---|
| [ADR-0506](0506-extract-okf-content-into-a-standalone-zuno-okf-repository.md) | Proposed | Extract OKF content into a standalone zuno-okf repository |
| [ADR-0507](0507-consume-the-zuno-okf-repository-through-a-single-pinned-reference.md) | Proposed | Consume the zuno-okf repository through a single pinned reference |
| [ADR-0508](0508-isolate-okf-parsing-behind-per-component-adaptation-hooks.md) | Proposed | Isolate OKF parsing behind per-component adaptation hooks |
| [ADR-0509](0509-deliver-okf-content-as-mounted-versioned-artifacts.md) | Proposed | Deliver OKF content as mounted versioned artifacts |
| [ADR-0510](0510-make-the-aiagent-operator-watch-the-zuno-okf-repository.md) | Proposed | Make the AIAgent operator watch the zuno-okf repository |

## OKF v0.1

| ADR | Status | Decision |
|---|---|---|
| [ADR-0501](0501-establish-the-okf-stream-with-its-own-milestones-and-roadmap.md) | Accepted | Establish the OKF stream with its own milestones and roadmap |
| [ADR-0502](0502-formalize-the-two-stage-agent-maturity-model.md) | Implemented | Formalize the two-stage agent maturity model |
| [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md) | Implemented | Make each OKF bundle state its complete authorization contract |
| [ADR-0504](0504-define-the-agent-tests-directory-structure-and-promotion-gate.md) | Implemented | Define the agent tests directory structure and promotion gate |
| [ADR-0513](0513-give-okf-rag-tools-and-policies-directories-a-real-schema.md) | Implemented | Give OKF rag/, tools/ and policies/ directories a real schema |
| [ADR-0514](0514-generalize-arkos-plan-draft-write-for-multiple-document-kinds.md) | Implemented | Generalize Arkos's plan_draft_write shape for multiple document kinds |
| [ADR-0515](0515-per-conversation-tabs-one-browser-tab-per-agent.md) | Implemented | Open per-conversation tabs with one browser tab per agent |

## Retired

Fully superseded or deprecated records, out of the active bands. An ADR
superseded only *in part* is not here - it stays in its version band, because
part of its decision is still in force.

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0016](0016-migrate-the-legacy-sxa-schema-to-postgresql.md) | v0 | Superseded by ADR-0219 | Migrate the legacy SXA schema to PostgreSQL |
| [ADR-0018](0018-use-ogx-with-langchain-and-langgraph-for-agentic-workflows.md) | v0 | Superseded by ADR-0322 | Use OGX with LangChain and LangGraph for agentic workflows |
| [ADR-0023](0023-use-a-namespace-per-agent-isolation-model.md) | v0 | Superseded by ADR-0329 | Use a namespace-per-agent isolation model |
| [ADR-0050](0050-abstract-the-rag-backend-and-integrate-openshift-ai-ogx.md) | v0.1 | Superseded by ADR-0322 | Abstract the RAG backend and integrate OpenShift AI OGX |
| [ADR-0111](0111-strengthen-secnumcloud-oriented-security-controls.md) | v0.7 | Superseded by ADR-0549 | Strengthen SecNumCloud-oriented security controls |
| [ADR-0114](0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md) | v0.1 | Superseded by ADR-0118 | Use Zuno as a policy router in front of OpenShift AI MaaS |
| [ADR-0213](0213-introduce-role-based-conversation-sharing.md) | v0.6 | Superseded by ADR-0527 | Introduce role-based conversation sharing between colleagues |
| [ADR-0216](0216-import-real-sxa-content-via-s3-into-mariadb-served-through-mcp-and-rag.md) | v0.2 | Superseded by ADR-0219 | Import real SXA content via S3 into MariaDB, served through MCP and RAG |
| [ADR-0217](0217-ingest-a-weekly-sxa-corpus-as-a-new-rag-domain.md) | v0.2 | Superseded by ADR-0219 | Ingest a weekly SXA corpus as a new RAG domain |
| [ADR-0303](0303-support-dynamic-lora-adapter-loading.md) | v0.3 | Superseded by ADR-0526 | Support dynamic LoRA adapter loading |
| [ADR-0332](0332-remove-console-favorites-provisioning.md) | v0 | Deprecated | Remove Console favorites provisioning |
| [ADR-0412](0412-serve-gpt-oss-20b-on-the-unmanaged-full-gpu-node.md) | v0.4 | Superseded by ADR-0414 | Serve gpt-oss-20b on the unmanaged full-GPU node |
| [ADR-0420](0420-sign-supply-chain-artifacts-in-cluster-with-vault-transit.md) | v0.4 | Superseded by ADR-0535 | Sign supply-chain artifacts in-cluster with Vault Transit |
| [ADR-0505](0505-open-okf-tasks-as-concurrent-per-agent-frontend-tabs.md) | OKF v0.1 | Superseded by ADR-0515 | Open OKF tasks as concurrent per-agent frontend tabs |

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
