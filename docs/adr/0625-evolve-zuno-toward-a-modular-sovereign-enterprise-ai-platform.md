# ADR-0625: Evolve Zuno toward a modular, sovereign enterprise AI platform

- **Status:** Proposed
- **Target:** v0.19
- **Date:** 2026-11-20
- **Decision owners:** Zuno Demo architecture team (review pending)
- **Related:** [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md),
  [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md),
  [ADR-0540](0540-express-guardrail-policy-as-nemo-rails-configuration.md),
  [ADR-0547](0547-parameterize-every-cluster-specific-value-in-ansible.md),
  [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md),
  [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md),
  [ADR-0568](0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md),
  [ADR-0602](0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md),
  [ADR-0603](0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md),
  [ADR-0606](0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md),
  [ADR-0612](0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md),
  [ADR-0613](0613-close-the-three-remaining-live-hardening-items-of-adr-0603-in-mid-december.md),
  [ADR-0619](0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)

> This record is an open architectural proposal. Every recommendation, candidate technology, deployment profile and
> roadmap item below is subject to review. It approves no decision, no implementation commitment and no change to the
> current platform. The target band (v0.19) is provisional: the review decides the band, or splits the record.
>
> 2026-11-21: the owner's upload of the proposal (dated 2026-11-20) was compared with this record, section by section.
> It carries no recommendation that this record lacks. This pass added the table "Existing records each recommendation
> builds on", moved the record from v0.17 to its own band, and opened the proposed work packages listed at the end.

## Context

Zuno Demo already provides a reusable AI platform on Red Hat OpenShift AI that combines:
- local and external model serving, and Models-as-a-Service (MaaS);
- inference governance;
- agent orchestration, with MCP and A2A gateways;
- RAG and MLOps;
- identity, artifact trust and observability.

The proposed next stage deepens the platform's sovereignty guarantees and operational maturity rather than adding
components. It has four complementary objectives:

- Extend governance to the complete lifecycle of data, models and AI artifacts.
- Offer explicit deployment profiles for different sovereignty requirements.
- Reduce the operational complexity of deploying and maintaining the platform.
- Establish a progressive path from a demonstration platform to qualified enterprise deployments.

Existing capabilities are reused wherever possible. Candidate technologies are illustrative, not selected products.

### Findings

What the platform depends on today, read from the repository and from demo333 on 2026-11-20. These facts bound what
each profile of section 3 has to replace.

| # | Finding | Evidence |
|---|---|---|
| F1 | Platform state lives on AWS: model sources, MLflow and MLOps artifacts, the internal Quay registry and the backups are S3 buckets in eu-central-1; persistent volumes are EBS (`gp3-csi`); nodes are AWS machines. | ansible/clusters/demo333.yml (`zuno_*_s3_bucket`, `s3.eu-central-1.amazonaws.com`); [ADR-0612](0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md); [ADR-0614](0614-split-the-cluster-into-infra-general-worker-and-gpu-node-pools.md) |
| F2 | Key management and PKI trust depend on AWS: Vault unseals with AWS KMS (`seal "awskms"`), and the ACME wildcard certificate is issued through a Route 53 DNS challenge. | `oc get cm zuno-vault-config -n zuno-vault` (vault-pki scenario, step 5:00); ansible/confidential.example.yml (`zuno_vault_kms_*`, `zuno_aws_route53_*`, `zuno_certmanager_*`) |
| F3 | External inference is configured for several international SaaS providers, next to European ones and the local fleet. Classification routing already keeps C2/C3 content local. | ansible/confidential.example.yml (`zuno_llm_provider_{openai,gemini,anthropic,mistral,mistral_codestral,ovhcloud}_api_key`); [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md); [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md) |
| F4 | Artifacts still come from public registries at build or mirror time (quay.io, registry.redhat.io, public.ecr.aws). Pod start no longer depends on them for the images already mirrored. | ansible/clusters/demo333.yml (`awsCli: public.ecr.aws/...`); [ADR-0611](0611-mirror-the-admitted-okf-release-into-the-internal-registry.md), [ADR-0612](0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md) |
| F5 | A content guardrail exists (NeMo Guardrails in the ai-gateway path). No DLP detector covers prompts, attachments, retrieved passages and tool results as one capability. | gitops/charts/trustyai-config/templates/nemoguardrails.yaml; [ADR-0540](0540-express-guardrail-policy-as-nemo-rails-configuration.md), [ADR-0567](0567-move-trustyai-guardrails-into-the-ai-gateway.md) |
| F6 | A safety control can depend on a model's ability to produce structured output. On 2026-11-20, OpenShift Lightspeed's tool-result screening, which classifies each tool result with the active model in strict JSON, failed about one call in two, because gpt-oss-20b on vLLM 0.24 returned an empty answer. The screening was switched off on demo333 to keep the console assistant usable. A vLLM-side option made it worse (0 of 10 valid). | OLSConfig `spec.ols.guardrails.toolResultInspection` (lightspeed-config, dc0e1419); docs/demo/scenarios/rhoai/lightspeed.md (Limits) |
| F7 | A deployment can silently fall back to a weaker configuration. Until 2026-11-20, an AAP job or a run from a worktree re-applied Argo CD Applications at the manifests' `main`, because the branch pin lived only in the gitignored confidential.yml. The fix (572ada00) moves the pin into the committed cluster file. | ansible/tasks/resolve_gitops_target_revision.yml; AAP job 1482 |
| F8 | One cluster, one inventory. demo222 was retired on 2026-10-23. Per-cluster values are split between ansible/clusters/demo333.yml, the inventory group_vars and confidential.yml. A per-cluster inventory layout is planned after the 2026-11-24 demo. | de7c36a4; [ADR-0547](0547-parameterize-every-cluster-specific-value-in-ansible.md); ansible/inventories/demo/ |
| F9 | Day-0 services can already run in internal or external mode. This is the existing switch a profile would set. | [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md); `zuno_keycloak_mode`, `zuno_mariadb_mode`, `zuno_redis_mode`, `zuno_external_secrets_mode`, `zuno_cert_manager_mode` |

### Existing records each recommendation builds on

Added on 2026-11-21. The existing records below are context: this proposal neither supersedes nor amends them. Where a
recommendation overlaps a record, the record keeps what it decided, and this proposal claims only the last column.

| Section | Already decided or implemented | What this proposal adds |
|---|---|---|
| 1.1 AI DLP | The effective classification is computed from the whole context ([ADR-0034](0034-compute-effective-classification-from-the-complete-context.md)) and can only be raised ([ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md)). Restricted internal context stays on local inference ([ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)). The guardrails run in the ai-gateway as NeMo rails, in `observe` or `block` mode per classification level ([ADR-0540](0540-express-guardrail-policy-as-nemo-rails-configuration.md), [ADR-0567](0567-move-trustyai-guardrails-into-the-ai-gateway.md)). The MCP tools carry signed classification markers ([ADR-0594](0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md)). | Detection of content (personal data, secrets, identifiers) as one shared capability, masking before an eligible external call, a detector qualified for its own reliability, and the fail-closed rule. |
| 1.2 Data governance | Document ACLs are the source's groups, applied fail closed at query time by the UnifAI RAG ([ADR-0110](0110-automate-document-acl-synchronization.md), [ADR-0568](0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md)). Knowledge access is a policy intersection over knowledge domains ([ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md)). | A catalog, lineage, licences and purposes, retention, deletion propagation, data quality and dataset versioning. No record covers them today. |
| 1.3 Policy as code | Tool authorization is a policy intersection, enforced in the MCP gateway ([ADR-0011](0011-define-tool-authorization-as-policy-intersection.md), [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md)). Tasks and policies are declarative and reviewed in Git ([ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)). The corp policies live in the agents repository and ship in a signed release ([ADR-0576](0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md), [ADR-0580](0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md)). The ai-gateway is the policy router ([ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md)). | Only an assessment: a shared decision engine (OPA or Cedar) compared with the native implementation, plus policy simulation and decision explanations. Policy as code itself is already the rule. |
| 1.4 Sovereign services | Day-0 services run in internal or external mode ([ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md), partially implemented). Buckets follow one per-cluster convention ([ADR-0546](0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md)). The internal Quay stores its blobs in an AWS S3 bucket ([ADR-0612](0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md)). Vault holds the application secrets ([ADR-0024](0024-use-vault-for-application-secrets.md)). The wildcard certificate comes from an ACME issuer through Route 53 ([ADR-0211](0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md)). Backup and recovery are defined and drilled ([ADR-0112](0112-implement-production-grade-backup-and-recovery.md)). | Object storage, Vault unseal and certificate issuance that need no AWS service, an independent failure domain for the backups, and the offline artifact path. |
| 1.5 European models | Local and external providers coexist under classification routing ([ADR-0020](0020-support-both-local-and-external-llm-providers.md), [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)). Mistral models are consumed as a service: Codestral ([ADR-0417](0417-consume-codestral-via-mistral-api.md)) and `mistral-large-latest` as a MaaS ExternalModel ([ADR-0541](0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md)). Local models get hardware profiles ([ADR-0537](0537-integrate-rhoai-hardware-profiles-and-maas-external-models.md)). | European-origin weights served locally, a qualification matrix, and model bills of materials. |
| 1.6 Substitutability | The Git-forge MCP server already speaks GitHub and GitLab ([ADR-0120](0120-implement-a-multi-provider-git-forge-mcp-server-for-github-and-gitlab.md)). RHTAS is the in-cluster trust service ([ADR-0535](0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md)). Pre-GA dependencies are tracked in a known-good file ([ADR-0607](0607-pin-gate-and-schedule-pre-ga-dependencies.md)). | A full dependency inventory, the licence assessment and the documented exit paths. |
| 2 Profiles | Day-0 modes ([ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md)), per-cluster values in Ansible ([ADR-0547](0547-parameterize-every-cluster-specific-value-in-ansible.md)) and classification routing ([ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)). | Named profiles, their enforcement and the live profile check. |
| 3 Modularity | An experience is admitted with a definition of done and a limit per band ([ADR-0606](0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)). Every demo runs through one lifecycle ([ADR-0616](0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)). | The three layers, their overlays and the promotion criteria between them. |
| 4 Roadmap | The trust-boundary hardening and its remaining windows ([ADR-0602](0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md), [ADR-0603](0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md), [ADR-0613](0613-close-the-three-remaining-live-hardening-items-of-adr-0603-in-mid-december.md)). Immutable, verifiable artifacts: [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md) is `Deferred`, the in-cluster release ledger of [ADR-0549](0549-close-the-secnumcloud-supply-chain-gap-with-an-in-cluster-release-ledger.md) and the image verification of [ADR-0586](0586-verify-the-unifai-runtime-images-by-digest-signature-and-attestations-before-deploying-them.md) are implemented. HA ([ADR-0101](0101-provide-ha-for-shared-agent-platform-services.md)), backup ([ADR-0112](0112-implement-production-grade-backup-and-recovery.md)) and the stress campaign ([ADR-0624](0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)). | Work packages that extend these records. None reopens them. |

One gap this comparison shows: OKF artifacts and the UnifAI images are signed keyless with a GitHub OIDC identity
([ADR-0578](0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0586](0586-verify-the-unifai-runtime-images-by-digest-signature-and-attestations-before-deploying-them.md)), and verified offline against a committed trusted root. The European, Sovereign and
Air-Gapped profiles ask for an internal signing and trust chain (section 2), so the build-time signer is part of the
dependency inventory (1.6).

## Decision

**Proposed, not decided: deepen sovereignty through data and model governance, explicit and testable deployment
profiles, and a Core / Enterprise / Labs modular split, qualified by evidence before any new user experience.**

Sections 1 to 5 below are the proposal under review. Section 6 lists the questions the review must answer.

### 1. Recommended capability extensions

#### 1.1. AI Data Loss Prevention (AI DLP)

**Recommendation:** introduce a shared data protection capability at the relevant trust boundaries, integrated with the
existing Zuno gateways and ingestion paths.

Proposed capabilities:

- Detect personal data, credentials, secrets, confidential identifiers and sensitive business information in:
  - prompts and attachments;
  - retrieved documents and tool results;
  - generated responses.
- Combine content detection with the existing C1/C2/C3 classification policies, the signed MCP markers and the OKF
  agent and task classification floors.
- Let detection raise the classification, never silently lower it ([ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md)).
- Prefer local inference for unclassified or ambiguous content. Refuse external transmission when the applicable policy
  cannot be established.
- Apply policy-driven masking, redaction or pseudonymization before an eligible external model call, and only where the
  transformation is explicitly authorized.
- Record DLP decisions and policy violations without keeping unnecessary sensitive payloads in logs or traces.
- Evaluate detection quality, false positives, false negatives, latency and multilingual coverage.
- **(Added at intake) Fail closed, with a measured detector.** A DLP or screening control that cannot reach a verdict
  blocks or escalates. It never passes content through, and it is never switched off to keep a feature working without
  a recorded exception.
  - The detector's own reliability (rate of empty or unparseable verdicts) is part of its qualification.
  - Finding F6 shows the failure mode this prevents.
  - Where the detector is a model, a deterministic detector or a model qualified for structured output backs it up.

**Candidate implementation:**
- Microsoft Presidio, complemented by deterministic secret detection and organization-specific classifiers.
- The existing NeMo Guardrails integration, reused where appropriate (F5).
- A local classifier, evaluated for the cases deterministic rules do not cover.

**Expected benefit:** prevention of accidental data disclosure to external providers, including when users paste
sensitive information into general-purpose chat interfaces.

#### 1.2. Data governance and knowledge lifecycle

**Recommendation:** introduce a governance layer for knowledge sources, RAG corpora, datasets and model-training inputs.

Proposed capabilities:

- Maintain a catalog of data sources, knowledge domains, datasets, owners and classifications.
- Track origin, ingestion history, transformations, embedding versions and downstream use.
- Record licensing conditions, authorized purposes and retention periods.
- Preserve source-system permissions, and reconcile ACL changes into derived indexes (UnifAI RAG on Qdrant,
  [ADR-0568](0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md)).
- Propagate deletion and revocation events to vector indexes, caches and derived datasets, subject to retention and
  legal-hold policies.
- Introduce data quality checks and dataset versioning, to support reproducible fine-tuning and evaluation.
- Expose data lineage and governance evidence to authorized administrators and auditors.

| Capability | Candidates to evaluate |
|---|---|
| Data catalog and governance | OpenMetadata or DataHub |
| Lineage | OpenLineage / Marquez, or native catalog capabilities |
| Data quality | Great Expectations |
| Dataset versioning | DVC or lakeFS |
| Distributed processing | Apache Spark, where justified by workload scale |
| Sensitive data detection | The shared AI DLP capability (1.1) |

**Expected benefit:** traceable, authorized and reproducible use of enterprise knowledge throughout the AI lifecycle.
Prefer a minimal integrated toolset over deploying every candidate.

#### 1.3. Unified policy as code

**Recommendation:** assess whether a shared policy decision layer can reduce duplication and inconsistencies across the
AI, MCP and A2A gateways, while keeping enforcement at each trust boundary
([ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md)).

Proposed capabilities:

- Represent organization-wide rules and agent and task restrictions as versioned, reviewable policy artifacts.
- Preserve the existing OKF policy model, the corporate ceilings and the signed release process.
- Give consistent decisions based on user identity, group, workload, agent, task, model, tool and data classification.
- Preserve monotonic classification, explicit deny semantics, signed delegation and fail-closed behaviour.
- Support policy simulation, regression tests, decision explanations and versioned rollback.
- Evaluate latency, availability, policy distribution and failure behaviour before introducing a shared runtime
  dependency.

**Candidates:** Open Policy Agent (OPA) or Cedar. Compare both with keeping and improving the native Zuno policy
implementation. Introduce an external policy engine only where it brings demonstrable value.

**Expected benefit:** auditable and consistent policy decisions, with less duplicated authorization logic and no
weakening of the existing gateway controls.

#### 1.4. Sovereign data and infrastructure services

**Recommendation:** qualify an infrastructure profile that needs neither AWS nor any other external cloud service to
operate the platform (F1, F2).

Proposed capabilities:

- S3-compatible object storage for model weights, datasets, registry artifacts, MLflow artifacts and backups.
- Independent key management, Vault unseal mechanism and PKI, replacing the AWS KMS seal and the Route 53 challenge
  (F2).
- Internal image, operator, Helm and model artifact repositories (F4).
- Backup, restoration and disaster recovery on infrastructure the organization controls, including an independent
  failure domain.
- Portable infrastructure configuration and a reproducible OpenShift bare-metal deployment.
- Offline acquisition, verification, promotion and distribution of the required artifacts for disconnected
  environments.

**Candidates:**
- Red Hat OpenShift Data Foundation / Ceph RGW, for object storage.
- An independently operated KMS, HSM or Transit-based unseal, where appropriate.
- Internal Quay and RHTAS, for artifact distribution and trust.

**Expected benefit:** reduced cloud-provider dependency and a credible path toward strict sovereignty and
disconnected operation.

#### 1.5. European model stack

**Recommendation:** qualify a portfolio of European-origin models with locally deployable weights, to complement the
existing model fleet. Remove no model solely because of its origin before evaluation.

Proposed coverage:

- General-purpose conversation and enterprise RAG.
- Reasoning and multi-step agent workflows.
- Code generation and technical assistance.
- Embeddings and, where justified, reranking.
- Multilingual workloads, including French.

Mistral AI model families are the initial candidates, subject to the availability and suitability of individual
releases. Evaluate each candidate for:
- licence, weight availability and provenance;
- runtime compatibility and GPU footprint;
- performance and quality;
- tool calling and structured output.

Structured output is measured on the serving stack actually used, since the same weights behave differently across
runtimes and parsers (F6).

Distinguish European origin, local hosting and legal and operational control: none of them alone establishes
sovereignty.

Extend the MLOps and supply-chain qualification process to cover:
- model and dataset hashes;
- model bills of materials and licences;
- evaluation evidence;
- reproducible promotion.

Include regression tests for tool calling and RAG after fine-tuning.

**Expected benefit:** wider model choice and less dependence on non-European model providers, with measured rather
than assumed quality and sovereignty guarantees.

#### 1.6. Open-source independence and substitutability

**Recommendation:** establish an inventory of platform dependencies, and identify practical exit or replacement paths
for the strategically significant components.

| Dependency area | Candidate path to evaluate |
|---|---|
| Secrets management | OpenBao as a potential alternative to Vault |
| Source control and CI | Forgejo or self-managed GitLab, according to licence and capability requirements (today: GitHub and GitHub Actions, including the UnifAI release cron) |
| Artifact signing | Independently operated RHTAS / Sigstore trust infrastructure |
| Registry and storage | Internal Quay and S3-compatible storage |
| GPU and runtime | Qualification of non-NVIDIA accelerators, including AMD ROCm, against actual support and performance constraints |
| Business integrations | Self-hosted or otherwise approved alternatives, where the target sovereignty profile requires them |

Assess licences and redistribution rights for source code, container images, operators, runtimes, model weights and
datasets. Document, for each dependency:
- the vendor dependency and the switching cost;
- functional parity and support implications;
- the residual risks.

Prefer standard interfaces where they meet the requirements: OCI, S3, OIDC, Kubernetes APIs, MCP, A2A and
OpenTelemetry.

**Expected benefit:** measurable reversibility and less dependency on any single provider, without losing the value of
the supported Red Hat platform.

### 2. Proposed sovereignty profiles

**Recommendation:** define explicit, testable deployment profiles that share one architectural foundation and differ
in permitted dependencies and operating conditions. Treat them as configuration and qualification deliverables, not
as separate product forks.

| Requirement | Hybrid AI | European AI | Sovereign AI | Air-Gapped AI |
|---|---|---|---|---|
| Local inference | Required | Required | Required | Required |
| International SaaS inference | Policy-controlled | Prohibited | Prohibited | Prohibited |
| Approved European SaaS inference | Permitted by policy | Permitted by policy | Prohibited | Prohibited |
| US hyperscaler hosting | Possible | Prohibited in the proposed profile | Prohibited | Prohibited |
| Object storage | Approved local or external service | Approved local or European service | Controlled local service | Controlled local service |
| Independent PKI and key management | Optional, subject to risk | Required | Required | Required |
| Internal artifact registry | Required | Required | Required | Required |
| Internal signing and trust chain for admitted releases | Optional, subject to risk | Required | Required | Required |
| Internet connectivity | Controlled | Controlled | Strictly limited | None during operation |
| Autonomous offline installation and updates | Not required | Not required | Recommended | Required |
| External business integrations | Policy-controlled | Approved European services or internal sources | Internal or explicitly authorized controlled interfaces; no prohibited data transfers | Internal only, with controlled offline import and export |

demo333 today is closest to **Hybrid AI**, but it does not meet the column fully. The open gaps:
- the hyperscaler hosting, KMS and object storage of F1 and F2;
- the SaaS providers of F3, already policy-controlled by classification.

#### 2.1. Profile enforcement

Proposed common requirements:

- Express each profile as versioned, reviewable deployment configuration and policy overlays.
  - **(Added at intake)** In this repository, an overlay is a per-cluster inventory (F8): one inventory per deployment,
    which names its profile.
  - Day-0 internal or external modes (F9) and the model provider list are set from the profile, not per role.
- Validate before deployment:
  - the permitted model providers and egress destinations;
  - identity providers, storage backends and registries;
  - trust roots and external integrations.
- Enforce restrictions at gateways, network boundaries and admission controls, rather than relying on UI settings or
  operator instructions.
- Prevent silent degradation to a weaker profile on failure (F7). A profile changes only through an explicit approval
  and promotion process.
- **(Added at intake)** A recurring check compares the live cluster with its declared profile:
  - egress destinations and model providers;
  - registries and trust roots;
  - every guardrail that is switched off.

  A switched-off control (F6) shows as a recorded, dated exception, not as a silent state.
- Provide, for each qualified profile:
  - positive and negative tests;
  - an inventory of external dependencies;
  - evidence of backup and restore.
- For the disconnected profile, demonstrate fresh deployment, normal operation, controlled offline update and disaster
  recovery without Internet access.

#### 2.2. Positioning and limitations

These names and controls are proposals: the exact boundaries, permitted jurisdictions and exceptions remain to be
validated. They are not a SecNumCloud qualification, a regulatory certification or a legal opinion.

A European provider or a locally hosted component must still be assessed for:
- ownership and contractual terms;
- applicable law;
- remote support, telemetry and subprocessors;
- operational control.

### 3. Proposed platform modularity

**Recommendation:** organize Zuno into three composable capability layers, to reduce deployment size, operational
complexity and dependency coupling. The layers are independent from the sovereignty profiles: a small deployment may
need strict sovereignty, and a large deployment may be hybrid.

| Layer | Proposed capabilities | Purpose |
|---|---|---|
| **Zuno Core** | OpenShift AI, local model serving, MaaS, AI and MCP gateway, IAM, secrets, basic RAG, observability, GitOps and baseline security | Minimum governed AI platform for chat, inference and knowledge access |
| **Zuno Enterprise** | UnifAI, agent factory and OKF lifecycle, A2A gateway, advanced MCP connectors, MLOps, RHTAS-based trust, AAP and advanced governance | Enterprise agentic AI and industrialized lifecycle management |
| **Zuno Labs** | World Model, Blender, comparative gateways (Praxis and the other alternative gateways), experimental agent frameworks and optional user experiences | Isolated innovation, experimentation and demonstrations |

#### 3.1. Modularity principles

- Define each capability with its prerequisites, supported versions, operator dependencies, resource requirements,
  exposed interfaces and a responsible owner.
- Make extensions independently deployable through the existing Ansible, Helm and Argo CD mechanisms, with explicit
  dependency validation.
- The sovereignty profile decides the mandatory security controls, not the layer.
  - For example, a Sovereign AI Core deployment still gets the mandatory artifact-signing and admission controls, even
    if the advanced RHTAS workflows are packaged as Enterprise capabilities.
- Let a customer deploy a minimal governed chat and RAG solution without installing unrelated agentic, training or
  experimental services.
- Prevent Labs components from weakening the common platform policies or affecting production workload availability.
  Use namespace, identity, network and resource isolation.
- Define promotion criteria for a Labs capability to enter Enterprise or Core, in line with the definition of done of
  [ADR-0606](0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md):
  - a demonstrated use case;
  - a security review;
  - automated validation;
  - lifecycle ownership;
  - documented support boundaries.
- Maintain compatibility and sizing matrices for the qualified combinations. Do not treat every possible combination as
  supported.

**Expected benefit:** lower infrastructure and operational cost, clearer support boundaries, easier upgrades, and more
flexibility for customer-specific architectures.

### 4. Indicative roadmap

**Recommendation:** prioritize policy enforcement, modularity and evidence of sovereignty before more user experiences.

The horizons below count from the start of an approved initiative. They are neither committed calendar dates nor
person-day estimates. Existing work packages and ADRs are reused or extended rather than duplicated, starting with:
- the post-demo hardening list ([docs/roadmap/post-demo-hardening.md](../roadmap/post-demo-hardening.md));
- [ADR-0613](0613-close-the-three-remaining-live-hardening-items-of-adr-0603-in-mid-december.md).

| Horizon | Workstream | Proposed outcomes |
|---|---|---|
| Day 0-30 | Gateway and trust-boundary hardening | Review local-by-default handling, fail-closed behaviour, signed context propagation, non-bypassable control paths, guardrails and privilege boundaries; establish security acceptance tests. |
| Day 0-30 | Core / Enterprise / Labs modularity | Capability inventory, dependency graph, proposed deployment overlays (per-cluster inventories, F8), support boundaries and a minimal Core deployment. |
| Day 30-60 | AI DLP and classification | Evaluate candidate classifiers, including their structured-output reliability (F6); implement a controlled proof of concept and negative tests for sensitive-data disclosure. |
| Day 30-60 | Fully local sovereignty profile | Disable external inference; qualify the required local dependencies and policy enforcement. |
| Day 30-60 | Verifiable supply chain | Extend immutable digest pins, signature and admission coverage, and provenance to models, datasets and deployable artifacts; validate failure behaviour. |
| Day 60-90 | Data governance | Catalog data owners and classifications; establish lineage, versioning, ACL reconciliation and deletion propagation for pilot corpora. |
| Day 60-90 | AWS-independent deployment | Deploy and qualify an OpenShift bare-metal or equivalent independently controlled environment, with local object storage and key management (F1, F2). |
| Day 90-180 | Air-gapped qualification | Build a complete offline artifact inventory; demonstrate disconnected installation, updates, operation and recovery. |
| Day 90-180 | Enterprise operational qualification | Validate HA, disaster recovery, backup and restore, representative load (the Day 3 stress campaign of [ADR-0624](0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)), capacity, SLOs and operational procedures. |

European model qualification and the dependency and licence assessment run across these workstreams. The target
profiles and the measured functional gaps set their priorities.

#### 4.1. Suggested qualification evidence

Each workstream should provide, where relevant, a documented architecture, the implemented configuration, automated
tests and live evidence. Proposed acceptance evidence:

- An attempt to route C3 data, or unclassified sensitive content, to an unauthorized external model is rejected,
  including when local inference is unavailable.
- Direct MaaS access and the alternative gateway paths
  ([ADR-0619](0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)) cannot get
  around the selected profile's restrictions.
- A revoked access to a source document shows in retrieval and in later access to the derived data.
- An admitted release can be rebuilt from verified, immutable artifacts, and rolled back with a documented procedure.
- The Core layer can be deployed and exercised without installing the Enterprise or Labs capabilities.
- The strict and disconnected profiles can be tested against their declared dependency inventory, including failure
  and recovery cases.
- **(Added at intake)** Every safety control the profile requires stays on, or appears as a recorded exception, in the
  live profile check (2.1).
- Operational objectives are agreed before qualification. Availability, RPO, RTO, throughput and latency are measured,
  not presumed.

### 5. Open questions for architecture review

- Which sovereignty profile and customer use case should be qualified first?
- Which capabilities belong in the mandatory Core, and which are optional extensions?
- What default classification and external-model behaviour should apply to free-form content and attachments?
- Should the policy logic stay native to Zuno or move to a shared policy decision engine?
- Which data sources are the first data governance and DLP pilots?
- Which European model families, licences and hardware configurations enter the first qualification matrix?
- Which external dependencies may remain in each profile, including the build-time trust chain and the business
  connectors?
- What level of operational independence, HA, recovery and disconnected update capability is required?
- What delivery capacity and dependencies must be accounted for before committing to a roadmap?
- **(Added at intake)** Is a second cluster needed to qualify a second profile, or can the profiles be qualified one
  after the other on demo333? This decides whether the per-cluster inventory work (F8) must also cover a real second
  cluster.

## Alternatives considered

- **Keep extending the component inventory.** Adding experiences without profiles, layers or evidence increases the
  operational load that F6 and F7 already show, and does not make any sovereignty claim testable.
- **One fork per profile.** Separate code bases per sovereignty level would duplicate every fix. The proposal keeps one
  foundation with configuration and policy overlays.
- **Certification first.** Seeking a formal qualification (for example SecNumCloud) before the profiles are testable
  would certify a moving target. Section 2.2 keeps the profiles as engineering commitments until they are qualified.

## Consequences

- Each profile and each layer becomes a deliverable with tests, a dependency inventory and an owner. The volume of
  qualification work grows, and the review must size it (section 5, last question).
- Some current switches become profile-driven: day-0 modes, the model provider list, the egress allowlists. Roles stop
  deciding them one by one.
- Controls that today can be switched off silently (F6) or fall back silently (F7) gain a visible, dated exception
  state.

## Security considerations

- The proposal strengthens, and does not relax, the existing rules: monotonic classification
  ([ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md)), fail-closed gateways and the
  trust boundaries of [ADR-0602](0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md) and
  [ADR-0603](0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md).
- New detectors (DLP) see sensitive content by design. They run locally and keep no payload in logs or traces.
- A shared policy engine (1.3) would become a critical dependency. Its failure must deny, and its availability is part
  of its evaluation.
- The repository is public: profile overlays and dependency inventories name no secret, no private endpoint and no
  customer.

## Operational considerations

- Per-cluster inventories (F8) carry the profile. An operator selects one cluster, and its profile, per run.
- The live profile check (2.1) runs on a schedule next to the existing golden-path and Day 2 checks, and reports every
  switched-off control.
- Disconnected operation adds an artifact import and promotion procedure (1.4) to the release runbooks.

## Work packages

Proposed on 2026-11-21, one per workstream of section 4, all `Not started`. They exist so the roadmap shows the size of
the proposal. None is approved: the review accepts, changes or drops each one.

- WP-319: the gateway and trust-boundary review, with its security acceptance tests (Day 0-30).
- WP-320: the capability inventory, the Core / Enterprise / Labs overlays and a minimal Core deployment (Day 0-30).
- WP-321: the AI DLP proof of concept (Day 30-60).
- WP-322: the fully local profile and the live profile check (2.1) (Day 30-60).
- WP-323: the verifiable supply chain for models, datasets and deployable artifacts (Day 30-60).
- WP-324: the data governance pilot (Day 60-90).
- WP-325: the deployment without AWS services (Day 60-90).
- WP-326: the air-gapped qualification (Day 90-180).
- WP-327: the enterprise operational qualification (Day 90-180).
- WP-328: the European model portfolio (across the horizons).
- WP-329: the dependency and licence inventory, with exit paths (across the horizons).

Section 1.3 (unified policy as code) has no work package: section 4 gives it no workstream, and it stays an open
question of section 5.

The per-cluster inventory layout (F8) is separate work, already planned for after the 2026-11-24 demo. WP-320 and WP-322
build on it.
