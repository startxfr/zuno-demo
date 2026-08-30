# Zuno Demo Project Memory

> This file is the repository-level working memory for the project. It records agreed project context and source-derived SXA schema knowledge. It must contain no credentials, secrets, real business records, or nominative commercial data.

## 1. Project objective

Zuno Demo is an internal MVP built on Red Hat OpenShift AI. It has three simultaneous objectives:

1. demonstrate OpenShift AI capabilities;
2. deliver five usable internal AI agents;
3. establish a reusable agentic platform and catalog for future agents.

The MVP target is seven days with two contributors. Documentation and architecture deliverables are written in English Markdown. GitHub `startxfr/zuno-demo` is the intended canonical repository.

## 2. Platform target

- OpenShift Container Platform 4.22, AWS IPI.
- Red Hat OpenShift AI 3.5 EA2.
- Internet-connected cluster.
- Two CPU worker nodes; GPU capacity per ADR-0351 as amended by WP-083:
  TWO permanent g7e.4xlarge nodes (NVIDIA RTX PRO 6000 Blackwell 96GB
  each, both MIG-partitioned `all-balanced` = 2x 1g.24gb + 1x 2g.48gb),
  `zuno-gpu-a` in eu-west-2a and `zuno-gpu-c` in eu-west-2c. They are
  symmetric on purpose: either one alone holds all three inference
  workloads, which is what makes the loss of a GPU node survivable - the
  earlier replicas-0 AZ-failover design could not work, because the
  ClusterAutoscaler never sees `nvidia.com/mig-*` capacity and so could
  never have been triggered by a Pending MIG-slice pod. Both carry
  `nvidia.com/gpu=true:PreferNoSchedule` (soft - it stops platform pods
  creeping back, it does not dedicate the nodes). Plus a scale-from-zero
  tainted burst node (whole GPU, for training) - all managed by
  `gitops/charts/machines`. The installer's IPI `workergpu` machineset is
  back at replicas 0, as ADR-0351 decision 7 always intended.
- NVIDIA GPU Operator deployed as a prerequisite (ClusterPolicy
  `mig.strategy: mixed` via ansible overlay, ADR-0351).
- OpenShift AI Operator and required dependencies deployed as prerequisites.
- DataScienceCluster configured as part of platform preparation/configuration.
- Keycloak, Vault, PostgreSQL and observability are demo prerequisites.
- S3 is available.
- Network reference: 10 Gbps.
- Initial scale: 50 users, about 10 concurrent users, about 5 concurrent active conversations.
- Interactive objective: first token in less than 6 seconds.
- Long document workflows may take up to 10 minutes.
- 99.9% availability is an industrialized-target objective, not an MVP prerequisite.

## 3. Agent platform architecture constraints

- Generic agentic platform with five initial instances.
- One PatternFly frontend and one BFF deployment per agent.
- Frontend static assets served by a lightweight Go server; backend API endpoint supplied through environment configuration and exposed to JavaScript runtime configuration.
- BFFs expose versioned APIs with OpenAPI/Swagger.
- Shared Agent Runtime and shared AI/Inference Gateway are separate responsibilities.
- Agent Runtime owns task orchestration, conversation state, LangChain/LangGraph workflows, RAG and MCP invocation.
- AI/Inference Gateway owns model selection, routing, measurement, quotas, cost, fallback, inference security and response streaming.
- All LLM calls traverse the AI/Inference Gateway.
- A central MCP Gateway fronts shared MCP servers.
- MCP is the standard integration contract for tools.
- Effective tool permission is derived from agent definition, user/group authorization, data classification and platform policies.
- Namespace-per-agent isolation is required, with separate service accounts, quotas and NetworkPolicies.
- `AIAgent` CRD and an operator are part of the project rather than a future-only idea.

## 4. Agent definition and OKF

- Open Knowledge Format v0.2 is the base declarative format.
- Zuno extends OKF to describe agent operational behavior where OKF does not prescribe runtime semantics.
- Agent definitions include identity metadata, UI metadata, tasks, prompts, model preferences, model/data classifications, RAG sources, MCP tools, policies, expected I/O schemas and task permissions.
- Definitions are GitOps-managed and reviewed through pull requests.
- Changes require human approval.
- Git commits/tags and agent bundles are intended to be signed.
- Stale knowledge should be down-ranked and explicitly signaled to the user rather than silently discarded.
- An agent definition can be enabled or disabled without developing a new runtime.
- The objective is to add a sixth agent mainly by adding a declarative definition and configuration.

## 5. Identity and security

- Keycloak is a prerequisite and central identity service.
- Google Workspace is federated with Keycloak.
- Access groups follow `agent_<name>` naming, for example `agent_comage` and `agent_tekos`.
- `sales_admin` is a Keycloak group.
- A user may access multiple agents.
- Task-level authorization is supported.
- End-user identity is propagated through platform calls; downstream services may revalidate authorization against Keycloak.
- Service-to-service identities use dedicated service accounts when appropriate.
- Google Workspace uses delegated per-user OAuth2 rather than domain-wide service-account impersonation.
- Google credentials/session material may be retained for up to five days and must be revocable by the user.
- Vault stores application secrets.
- Data classification policy:
  - C1: SaaS model use allowed.
  - C2: SaaS allowed with restrictions and context filtering.
  - C3: local models only.
- Confluence content is C2.
- DAT workflows marked sovereign are local-model-only; non-sovereign projects may use approved SaaS models.
- Sensitive logs must mask protected content.
- Default prompt/response retention: one month.
- Security target should align toward SecNumCloud-oriented controls during industrialization.
- Agents must not send email externally or impersonate the user's mailbox for outbound mail. Scheduled reporting uses a technical SMTP identity and internal recipients.

## 6. Model strategy

Local model families:

- IBM Granite;
- Qwen;
- Llama.

Variants are selected to fit a 24 GB GPU memory envelope (originally
NVIDIA L4 cards; since ADR-0351 the equivalent 1g.24gb MIG slices of the
RTX PRO 6000, with the chat model on the roomier 2g.48gb slice).
OpenShift AI model serving is used for local inference. KServe,
Models-as-a-Service and llm-d are included in the architecture where
relevant to OpenShift AI 3.5 EA2 capabilities.

Approved external provider preference and default fallback order:

1. OpenAI;
2. Gemini;
3. Anthropic;
4. Mistral.

Routing considers quality, cost, latency, availability, classification and agent/task rules. If no destination satisfies classification policy, the request must fail rather than violate policy.

LoRA/PEFT is an architectural capability. Comage remains the first candidate agent, but ADR-0526 (WP-087) replaced the objective: it is a **style** adaptation (contemporary French urban register), not the sales-jargon **domain** adaptation ADR-0301 originally scoped, and the trained adapter is **merged** into a standalone checkpoint served as its own model rather than loaded onto the shared runtime. The original desired benefits — lower response time, lower token consumption, improved relevance — do not apply to that objective and are no longer what this capability is measured on; the measure is register conformance plus an unchanged acceptance gate. The domain-adaptation objective was abandoned because the data for it does not exist: Comage's two declared knowledge domains hold zero rows.

## 7. RAG strategy

PostgreSQL with pgvector is preferred. A dedicated PostgreSQL instance hosts logically isolated schemas/databases per agent. Hybrid vector plus full-text search is required.

Tekos initial knowledge includes:

- official OpenShift documentation for 4.20, 4.21 and 4.22/latest where available;
- latest two GA versions for Keycloak and other selected products;
- official Kubernetes documentation;
- Go documentation;
- Red Hat Satellite;
- Red Hat Developer Hub / IDP;
- Red Hat Ansible Automation Platform;
- Helm;
- Argo CD;
- Git command fundamentals;
- Linux fundamentals;
- internal Confluence content.

Official vendor sources are preferred for product facts. Technical answers include concise citations. Public and internal corpora remain logically separated. Internal embeddings are calculated locally. External web searches must not leak internal context.

Automated documentation ingestion runs monthly and can also be triggered manually. Kubernetes CronJob/Job is acceptable for the MVP; pipeline-based evolution may follow.

## 8. Google Workspace and architecture-agent workflows

A shared Google Workspace MCP server uses delegated end-user OAuth2.

- Comage reads the user's Gmail mailbox but never sends mail as the user. It may propose a subject and body for manual use in Gmail.
- Arkos reads and writes authorized Google Drive content and can create/update Google Docs.
- Google Drive authorization must preserve the user's effective source permissions.
- Long-lived project contexts may vectorize only explicitly useful documents rather than the complete Drive.
- Arkos `/dat` requires an existing and selected project Drive folder. If no project folder is known, DAT generation must refuse to start.
- DAT workflow: collect -> outline -> explicit user review -> generation -> review -> final Google Doc.
- Intermediate workflow state is persistent and resumable.
- DAT output may include architecture diagrams, generated in-cluster from LLM-authored Mermaid via the `generate_diagram` tool (ADR-0516), which supersedes the originally-planned Lucidchart integration.
- Odyssey workshop preparation starts from an existing project Google Sheet and Google Slides template library in Drive and produces workshop material, architecture/build/run roadmap, slides and workshop reports.

## 9. Agent details

- **Comage** (sales): identify who to follow up; list deals without a
  client PO; generate weekly sales synthesis. Priority weighs deal age,
  quote date, last email and urgency (LLM-constrained). Uses sales data +
  Gmail; can write controlled status changes but never sends mail
  automatically as the user. Weekly report may be scheduled Sunday
  evening via the technical SMTP identity.
- **Tekos** (technical consultants): the first vertical slice — validates
  frontend, BFF, Keycloak, runtime, AI gateway, RAG, MCP Confluence,
  local/external model routing, streaming and citations. RAG/embedding
  over official documentation; no model fine-tuning required.
- **Arkos** (architects): create a DAT; prepare an Odyssey architecture
  workshop. Uses the same technology RAG/MCP sources as Tekos rather than
  invoking Tekos as an agent in v1 (agent-to-agent is deferred to v2).
- **Advantage** (sales administration): identify new business with a
  client PO received in the last 3 rolling days; monthly in-progress
  sales report (margin by state/customer/technology, text/table + PDF).
  May perform controlled status writes.
- **Finage** (finance): identify business ready to invoice; monthly
  invoicing report. Accesses `A facturer`/billable and later states
  including invoice info; report may include revenue, outstanding
  amounts, delay and forecast. May perform controlled status writes but
  must not execute financial transactions.

## 10. SXA commercial database - source-derived schema memory

The provided source is a legacy phpMyAdmin schema dump for MySQL 5.0.95. It is a schema reference for reading the corpus, not a target implementation: ADR-0219 (2026-08-26) settled that SXA is the company's closed pre-2021 record, served through retrieval only. `load-sxa-dump` parses the S3 `schema.sql`/`data.sql` pair in pure Python and writes one document per row into the `knowledge.sxa-legacy` pgvector index. There is no PostgreSQL or MariaDB SXA database anywhere in the platform.

### Core commercial flow

The actual domain chain is:

`affaire -> devis -> commande -> facture`

with corresponding line-item tables:

- `devis_produit`;
- `commande_produit`;
- `facture_produit`.

Important source tables include:

- `entreprise`: company/customer identity and address/business metadata;
- `contact`: contacts linked to companies;
- `affaire`: opportunity/business case, owner, status, budget, deadlines and Drive reference;
- `devis`: quote, opportunity link, status, commercial owner, total, client PO and Drive reference;
- `devis_produit`: quote line items, quantity, rebate and sales price;
- `commande`: order, originating quote, status, commercial owner, sales total, supplier total, client PO and Drive reference;
- `commande_produit`: order line items including sales price/rebate and supplier `prixF`/`remiseF`, useful for margin calculation;
- `facture`: invoice, originating order, status, sales owner, amount, payment conditions, send/payment dates, invoice type and Drive reference;
- `facture_produit`: invoice line items;
- `produit`: product catalog, family, price and Red Hat-oriented product classification metadata;
- `produit_fournisseur`: supplier-specific product price and rebate;
- `actualite`: activity/event journal referencing companies, contacts, opportunities, quotes, orders and invoices and their states;
- `appel`: calls and reminders, including user and opportunity references;
- `projet`: legacy project/context object;
- `user`: legacy SXA user table keyed by `login`;
- `ref_statusaffaire`, `ref_statusdevis`, `ref_statuscommande`, `ref_statusfacture`: state reference tables.

### Important source columns

`affaire`:

- `id_aff` primary identifier;
- `entreprise_aff`, `contact_aff`;
- `status_aff`;
- `commercial_aff`, `technique_aff`;
- `detect_aff`, `echeance_aff`, `budget_aff`;
- `gdrive_aff`.

`devis`:

- `id_dev` primary identifier;
- `affaire_dev`;
- `status_dev`;
- `commercial_dev`;
- `sommeHT_dev`;
- `BDCclient_dev`;
- `entreprise_dev`, `contact_dev`;
- `datemodif_dev`, `daterecord_dev`;
- `gdrive_dev`.

`commande`:

- `id_cmd` primary identifier;
- `devis_cmd`;
- `status_cmd`;
- `commercial_cmd`;
- `sommeHT_cmd`, `sommeFHT_cmd`;
- `BDCclient_cmd`;
- `entreprise_cmd`, `contact_cmd`;
- `daterecord_cmd`;
- `gdrive_cmd`.

`commande_produit` contains both customer pricing (`prix`, `remise`) and supplier pricing (`prixF`, `remiseF`), so margin calculations should be derived from real order economics rather than adding an artificial product `cost_price` unless later analysis proves necessary.

`facture`:

- `id_fact` primary identifier;
- `commande_fact`;
- `status_fact`;
- `commercial_fact`;
- `sommeHT_fact`;
- `dateenvoi_fact`, `datereglement_fact`;
- `entreprise_fact`, `contact_fact`;
- `type_fact`;
- `gdrive_fact`.

`user`:

- `login` is the primary identifier;
- contains identity/profile fields including email;
- the PostgreSQL demo model should map authenticated Keycloak subject/email to the legacy sales owner identity rather than trust the legacy password column.

### PostgreSQL migration requirements

The source schema contains MySQL-specific and legacy constructs that require explicit conversion, including:

- `AUTO_INCREMENT`;
- `enum('0','1')`;
- legacy integer display widths;
- `tinyint` semantics;
- MySQL zero dates such as `0000-00-00`;
- legacy timestamp/default behavior;
- implicit logical relationships that are indexed but not necessarily represented as foreign keys.

The section below records the source's business semantics because they are how the corpus reads, not because anything migrates them. Should a live commercial store ever be needed, it would be a new decision against a real system - ADR-0206 reserves the `sales.*` capability namespace for exactly that.

## 11. Sales database access policies

**ADR-0219 (2026-08-26) made this section read-only.** SXA has no tool path
and no writes: `knowledge.sxa-legacy` retrieval is the only access, gated by
`allowed_groups: [sales, board, adv, finance]` and `min_classification: C3`.
The role intents below are retained because they describe what each agent is
*asking about*, not a permission model that a SQL tool still enforces.

- Comage asks about deals for the authenticated sales owner; `sales_admin` about all permitted sales records.
- Advantage asks about business at client-PO-received / administration states and later.
- Finage asks about billable (`A facturer`) and invoiced states.
- No controlled writes exist. There is no SQL tool, deterministic or otherwise - a frozen pre-2021 record has nothing to write to. Arbitrary model-generated writes were never trusted and are now structurally impossible on this path.
- Any figure an agent reports from this domain is retrieved and must be attributed, never presented as a computed aggregate.
- The repository contains no SXA data of any kind. `data/sxa/` was deleted with the structured stores; the dump lives only in S3 (ADR-0025).

## 12. Evaluation and observability

- 20 acceptance scenarios per agent, approximately 100 initial tests.
- Target success threshold: 75%.
- A release below the required quality threshold should be blocked once automated quality gates are enabled.
- Arkos DAT quality includes human review.
- Measure tokens, cost, latency and usage by user, agent, task, model and provider.
- Distributed tracing uses OpenTelemetry-oriented instrumentation.
- Model routing decisions are observable.
- RAG evaluation includes retrieval quality, groundedness and citation quality.

## 13. Roadmap conventions

Roadmap is represented in two complementary forms:

- product maturity: MVP -> v1 -> v2 -> v3;
- time horizon: 30 / 60 / 90 days.

The roadmap must include platform/OpenShift AI, backend, frontend, OKF/agents, data/RAG, security, observability, testing, documentation and operations, with effort expressed in person-days and parallelism for two contributors.

Execution conventions (established 2026-08-14, extended by the OKF stream 2026-08-18):

- Work is decomposed into self-contained work-package briefs under `docs/roadmap/work-packages/` (v0.1-v0.3, tracked in `docs/roadmap/v0.1-v0.3-implementation-roadmap.md`) and `docs/roadmap/okf-roadmap.md` (OKF stream, WP-43+, 05xx ADR band), each written for standalone execution by a lower-capability model.
- WP state machine: `Not started -> Repo work in review -> Repo work merged -> Operator pending -> Done`.
- ADR status strings live only in `docs/adr/README.md` and ADR bodies (checked by `platform/docs/check_docs.py`); the roadmap tracks WP state only. Stub ADRs are promoted to full files before implementation (Step 0 of their brief).
- ADRs are immutable decision records, with one recorded exception: ADR-0219 (2026-08-26) renamed ADR-0216's and ADR-0217's **files** and rewrote their titles/bodies, because those titles asserted the content was anonymized when `sxa_anonymize.py` had been deleted three days earlier and no path anonymized anything. Renaming an ADR file means updating its `docs/adr/README.md` link (the index regex matches the exact filename) and every cross-reference. Do this only when a title states something factually untrue, never to tidy wording.
- Every brief separates model-executable repo changes from operator/cluster steps.
- Sessions commit one WP at a time and ask the user before attempting any live/cluster validation step.
- OKF-stream-specific: cross-repo single-writer clause (`zuno-demo` stays authoritative, `zuno-okf` is a mirror, from WP-48/WP-50); ADR `Target` header values `OKF v0.1|v0.2|v0.3`; quota precedence project -> user -> group (ADR-0511); `project_required` tasks verify a Salesforce project binding fail-closed before any action (ADR-0512).
- `platform/templates/agent/PROMOTION.md` is the canonical per-agent promotion checklist; `platform/okf/generate_authorization_matrix.py`, `generate_deployment_snapshot.py` and `run_agent_contract_tests.py` are blocking lint steps validating an agent's OKF bundle, rendered deployment shape and test-suite structure respectively.

## 14. Explicitly deferred capabilities

Main v2 candidates:

- agent-to-agent communication using a standard protocol such as A2A;
- delegation tracing;
- recursive delegation controls;
- specialized task-oriented frontend screens;
- stronger automatic synchronization/removal of private RAG content;
- richer human approval workflows.

Main v3 candidates:

- LoRA/PEFT customization;
- end-to-end dataset-to-model MLOps pipelines;
- dynamic adapter loading;
- self-service agent onboarding and broader autonomous platform optimization.

## 15. v0 implementation status

The sections above remain the working memory for the full target vision.
This section tracks current implementation status only: one status bullet
per ADR/WP, grouped by roadmap version band (v0.1/v0.2/v0.3). A later
fact supersedes an earlier one on the same topic — full rationale and
narrative live in the cited ADRs under `docs/adr/` and in git history,
not here.

### Baseline v0 build

- **Bootstrap**: `make day0|d0 check|install|configure|all` (cluster
  prerequisites) then `make day1|d1 check|build|configure|run|all` (build
  + run) from one credential (OpenShift API + cluster-admin token), via
  ArgoCD + External Secrets Operator + self-bootstrapping Vault
  (ADR-0022/0024/0056).
- **Identity**: `zuno` Keycloak realm, 27 anonymized synthetic personas
  (ADR-0349 restructure: 16 named personas with plus-addressed real
  mailboxes `dev+zuno-<user>@startx.fr` + 11 negative-test fixtures;
  ADR-0041 — no nominative identity/hardcoded password in git; shared
  INIT password vault-seeded at `zuno/keycloak/demo-personas`, live
  values diverge in Keycloak's own DB) across all eight agents' groups
  plus the four `ocp-*` cluster-access groups, real Google IdP
  federation (ADR-0014), and the policy-intersection files
  `policies/tools/tool-policy.yaml` +
  `policies/data-classification/classification.yaml`.
- **Data**: PostgreSQL + pgvector per knowledge domain. SXA is a read-only
  pre-2021 RAG corpus (`knowledge.sxa-legacy`), not a database (ADR-0219).
- **AI/model layer**: local Qwen3.6-27B (FP8) serving; AI Inference
  Gateway (`components/ai-gateway`, ADR-0009) owns provider
  routing/fallback/classification-eligibility (§6) behind an
  OpenAI-compatible API; MCP Gateway; RAG service; Tekos LangGraph
  workflow (`components/agent-runtime`, a thin `ai-gateway` client with no
  provider secret of its own).
- **Identity propagation** Frontend → BFF → Agent Runtime → AI Gateway
  (ADR-0032): the validated end-user bearer token is forwarded at every
  hop; `user_sub` is derived exclusively from the validated token, never
  the request body (ADR-0033).
- **Data classification per turn** (ADR-0034): `effective_classification`
  starts C1, escalates to C2 the moment Confluence content enters
  context, never downgrades. Confluence is C2 with
  `external_model_policy.allow_context: false` (ADR-0035), forcing
  local-only inference via an `X-Zuno-Local-Only` header honored by MCP
  Gateway, Agent Runtime and AI Gateway. Covered by
  `evaluations/tekos/security_checks.py` (ADR-0032–0035).
- **Agent entitlement vs. business role** (ADR-0040): `agent_<name>`
  Keycloak groups gate agent access; `sales`/`consultant`/`adv`/
  `finance`/`board` (+ `sales_admin` subgroup) gate tool/data permissions.
  Each BFF enforces entitlement server-side (403 if missing,
  `components/agent-bff/main.go`).
- **OKF v0.2 Markdown bundles** (ADR-0038): `agents/<name>/agent.okf.md`
  (YAML frontmatter + Markdown body) + `tasks/*.md` (+ Tekos
  `prompts/*.md`). Agent Runtime executes this contract at startup
  (ADR-0039, `app/registry.py` `AgentRegistry`: classification ceiling,
  RAG `top_k`, allowed tools, system prompt). MCP Gateway enforces the
  full ADR-0011 five-factor intersection (ADR-0036,
  `app/agent_declarations.py`); Agent Runtime declares
  `X-Zuno-Agent`/`X-Zuno-Task` on every tool invoke.
- **Agent surface**: OKF definitions for all five agents (Tekos `active`,
  rest `placeholder`); Tekos frontend/BFF live; `make day1|d1 check
  agents` structurally validates every agent's bundle (ADR-0031: Tekos is
  the sole mandatory v0 end-to-end path). All agent workloads run in the
  shared `zuno-ai-run` namespace — see ADR-0328/0329 below for why there
  is no per-agent namespace.
- **Workload hardening baseline** (ADR-0052): every repo-controlled
  workload runs non-root, no privilege escalation, all capabilities
  dropped, `seccompProfile: RuntimeDefault`, read-only rootfs + explicit
  `/tmp` emptyDir, no auto-mounted SA token, dedicated least-privilege
  ServiceAccount. Operator-managed workloads (Keycloak, KServe/vLLM, PGO,
  upstream Vault chart) get a documented partial treatment instead of
  guessed CRD fields. `zuno-auth`/`zuno-data`/`zuno-telemetry` get a
  namespace-level default-deny NetworkPolicy baseline; `zuno-ai-run` gets
  one precise per-workload NetworkPolicy instead (ADR-0037 requires each MCP
  server, e.g. `confluence-mcp`, to reject same-namespace neighbors too).
  Each server also validates a shared `X-Zuno-Gateway-Token` workload-identity
  secret independent of the network boundary.
  `platform/security/check_workload_hardening.py` statically verifies the
  whole baseline against every chart's rendered manifests (no live
  cluster needed).
- **PatternFly frontend + streaming** (ADR-0044/0045):
  `components/agent-frontend/web` is a real Vite + React + TypeScript +
  `@patternfly/react-core` app; the Go server resolves built assets via a
  Vite manifest reader and injects session/tile state as JSON. Chat
  streaming relays Agent Runtime's LangGraph SSE stream byte-for-byte
  through `agent-bff` and `agent-frontend` to the browser, with an
  `event: tool` status frame and an `X-Zuno-Request-Id` correlation
  header propagated across all three hops.
- **RAG metadata-aware + bilingual** (ADR-0046): indexed rows carry
  `product`/`version`/`language`/`source_type`/`classification`/
  `acl_groups`/`last_modified`/`stale_after`/`provenance` in `metadata
  jsonb` (`data/rag/schema/003_rag_metadata.sql`). `retrieve_node`
  extracts a named product/version as a deterministic pre-ranking filter,
  applies a soft French-language preference, forwards caller groups so
  rag-service enforces ACL server-side (fail closed), and escalates
  `effective_classification` to the highest classification among
  retrieved docs. **BFF is OpenAPI-first** (ADR-0054):
  `components/agent-bff/openapi.json` covers `/healthz`/`/api/chat`
  (incl. SSE) and fails `go test` on drift; `platform/api/lint_openapi.py`
  validates the spec itself.
- **Platform lifecycle/supply chain** (ADR-0047/0048/0115):
  `ansible/roles/nfd` installs NFD (required by the GPU Operator's
  default ClusterPolicy). `openshift_ai`'s DataScienceCluster uses KServe
  RawDeployment (`Removed`), not Serverless — Serverless would need
  Service Mesh/Serverless/cert-manager, none of which this repo installs.
  `ansible/roles/models` discovers the vLLM serving-runtime image from
  OpenShift AI's own `Template` catalog; `openshift_ai` discovers its
  operator channel from the cluster's PackageManifest — both fail loudly
  instead of guessing. Cert-manager/Service Mesh/Connectivity
  Link/LeaderWorkerSet/MaaS are deliberately not installed (not needed by
  v0's feature set — see `platform/openshift-ai/README.md`). CI workflows
  exist (`.github/workflows/{build-publish,lint}.yml}`: build/SBOM/
  scan/keyless-cosign-sign, and a lint gate) but have never run (no live
  Quay/Actions credentials); `check_no_latest_tags.py` correctly still
  fails until a real release is cut — see `RELEASING.md`.
- **Evaluation gate** (ADR-0027/0028/0053): `make day1|d1 check agents`
  runs `ansible/roles/agents/tasks/check.yml`'s OKF-structural + `/healthz`
  smoke checks, then `run_acceptance_gate.yml` runs
  `evaluations/tekos/run_acceptance_gate.py` as a one-shot in-cluster Job
  in `zuno-ai-run`, combining the 20 Tekos scenarios (75% threshold) with
  `security_checks.py` and `gate_checks.py` (both 100% mandatory) into one
  exit code. `components/{agent-runtime,mcp-gateway}/tests/test_auth.py`
  prove expired/untrusted-key JWTs are rejected, fully offline.
- **ADR-0350** (AIAgent CRD/operator) is Implemented — see WP-38 below.
- **Deployment sequencing** (ADR-0056): `make day0|d0
  <check|install|configure|all> [component]` (cluster prerequisites) +
  `make day1|d1 <check|build|configure|run|all> [component]` (build +
  run) is the sole interface. Day 0 adds `admin_context`
  (PriorityClasses, StorageClass check, ArgoCD ClusterRoleBinding
  consolidation) and `namespaces` (its own step). `zuno-ai` is split into
  `zuno-ai-run` (workloads) and `zuno-ai-build` (in-cluster image builds
  via OpenShift `BuildConfig`/`ImageStream`, `ansible/roles/{mcp,rag,
  agent}_build`, covering 6 of 8 CI-matrix images — `ai-gateway` and the
  pgvector base image still need one). `zuno-ai-build` default-denies
  ingress and grants only `zuno-ai-run`/`zuno-data`/`zuno-agent-tekos`
  scoped `system:image-puller` access.
- All four Python services instrument with OTel
  (`ansible/roles/observability/README.md`); `ai-gateway` owns
  per-provider model-call spans/token/cost metrics (ADR-0009). Cluster
  apps domain is auto-discovered from `Ingress.config.openshift.io/
  cluster`, persisted to Vault (`zuno/platform/cluster-domain`), and
  substituted into every GitOps `Application` — no manual edit needed
  (`ansible/tasks/resolve_cluster_base_domain.yml`,
  `gitops/apps/README.md`).
- **Keycloak routing/DB**: `keycloak.<domain>` is the real hostname
  everywhere (frontend OIDC issuer, eval scripts' `KEYCLOAK_URL`, the
  Keycloak CR's own Route) — no `sso.<domain>` alias exists. The Keycloak
  CR sets `spec.hostname.strict: true` and `KC_PROXY_HEADERS=xforwarded`
  explicitly (edge-terminated Route), and gets its own dedicated
  `keycloak`/`keycloak` Postgres database/role on `zuno-postgresql`
  (not the shared `zunoapp` app-data database).
- **Namespace consolidation** (ADR-0328/0329, 2026-08-12): `zuno-ai-platform`
  exists in `gitops/charts/namespaces` as the future OpenShift AI
  applications namespace (ADR-0328; DSC wiring to it is out of scope for
  now). ADR-0329 supersedes ADR-0023: the per-agent `zuno-agent-<name>`
  namespace model is retired — per-workload NetworkPolicies (ADR-0037)
  already carried real isolation. All Tekos workloads now live in
  `zuno-ai-run` alongside Agent Runtime/AI Gateway/MCP Gateway; the four
  placeholder agents carry no namespace footprint until their FE/BFF
  charts exist.

### Dated entries (roadmap work packages, v0) — current status per ADR

- **ADR-0057 (WP-062, 2026-08-21)**: `make day2|d2 test|stresstest
  [agents|platform|all]` — the Day 2 chassis, extending ADR-0056's Day
  0/Day 1 Makefile/Ansible dispatch idiom. `test` is availability-only
  (agent frontends' `/healthz` via `ansible/tasks/
  day2_availability_check.yml`, run from the control node since every
  agent frontend has a public Route; the shared platform tier's
  `/healthz`+`/readyz` via a lightweight in-cluster Job,
  `ansible/roles/day2/tasks/platform_health_check.yml`, since those
  services have no Route). Also replaced
  `ansible/roles/agents/tasks/check.yml`'s six hand-copied per-agent
  `/healthz` blocks (Tekos/Arkos/Comage/Advantage/Finage/Naveo) with one
  discovery-driven include (`agents/*/agent.okf.md`, mirroring
  `mcp_build`'s Dockerfile-discovery idiom) — `make day1 check agents`
  now shares the same implementation. Report engine
  (`platform/testing/day2_report.py`, text/json/csv, text always printed)
  is new, shared, and has its own local test suite
  (`platform/testing/tests/test_day2_report.py`, no cluster needed).
  `make d2 stresstest` shipped as a dispatch-only stub in this WP,
  filled in by WP-063. First live `make d2 test` run (2026-08-21) found
  two real bugs, both fixed same-day: (1) `target_component=all` aborted
  the whole play the instant the agents check hit a failure, so the
  platform check never ran - fixed with a shared
  `ansible/tasks/day2_render_and_fail.yml` step (report everything, decide
  once, matching `make d0 check`'s own `record_state.yml` precedent) both
  `test.yml` and `check.yml` now call; (2) the target lists themselves
  were wrong - agent discovery checked `soursage`/`cognos` (no
  deployment at all, ADR-0349 §6) and the platform Job probed all four
  MCP servers directly even though their NetworkPolicies only allow
  `mcp-gateway`'s pod label (ADR-0037) - both fixed by narrowing
  discovery (`gitops/charts/<agent>/` intersection) and the target list.
  Repo work merged; a second live cluster confirmation run is still
  pending.
- **ADR-0058 (WP-063, 2026-08-21)**: `make day2|d2 stresstest` runs
  every existing test layer per agent, generalized off the ADR-0053
  acceptance-gate Job (Tekos-only until now) rather than hardcoded to
  it — the Python layer (`run_scenarios.py`/`run_acceptance_gate.py`)
  was already agent-parameterized since ADR-0342/WP-31 via thin
  per-agent wrappers; what generalized here is the Ansible/Job layer
  (`ansible/roles/day2/tasks/stresstest_job.yml` +
  `stresstest_job_run_one.yml`), one Job per agent, discovered by
  intersecting `agents/*/agent.okf.md` with
  `evaluations/*/run_scenarios.py` — resolves today to all six agents
  with real content (Tekos/Arkos/Comage/Advantage/Finage/Naveo); only
  `gate_checks.py`/`stress_test.py` stay Tekos-only (no wrapper exists
  for either). Contract-test attribution
  (`platform/testing/day2_contract_attribution.py`) runs once from the
  control node (no cluster needed) rather than once per agent, parsing
  `run_agent_contract_tests.py`'s own output — while building it, it
  surfaced a real, pre-existing, unrelated finding: five agents'
  deployment snapshots are stale relative to their current charts
  (`platform/okf/generate_deployment_snapshot.py` needs a re-run) —
  left alone, out of this WP's scope. Bulk-interaction load mode
  (`platform/testing/day2_bulk.py`) replays each agent's own
  `scenarios.yaml` message content, no new prompts authored; the
  Makefile's `make d2 stresstest` prompts interactively for `BULK`
  (skipped when set, or non-interactive, defaulting to 10). `make day1
  check agents` (the ADR-0053 mandatory gate) is untouched — this WP is
  purely additive/informational, never wired into it. Repo work merged;
  live cluster confirmation (`make d2 stresstest` with a real `BULK`
  value) still pending.

### Dated entries (roadmap work packages, v0.1) — current status per ADR

- **ADR-0116 (WP-01)**: MCP Gateway routes tool calls through a
  backend-binding registry (`platform/bindings/tools/tool-bindings.yaml`,
  `components/mcp-gateway/app/bindings.py`) keyed by canonical
  `<domain>.<resource>.<verb>` capability IDs; legacy tool names remain
  aliases. Unbound/unknown capabilities fail closed before any backend
  contact. Implemented.
- **ADR-0114 / ADR-0118 (WP-03)**: ADR-0114 superseded by ADR-0118 — AI
  Gateway stays the policy router, `maas_adapter.py` (MaaS transport)
  stays merged and default-off as a delegation seam. Keep-vs-delegate and
  any cutover deferred to ADR-0201/WP-27, pending RHOAI's upstream MaaS
  mTLS defect fix and available GPU capacity.
- **ADR-0115 (WP-04)**: supply-chain tooling merged
  (`platform/supply-chain/verify_signatures.py`, `pin_release.py`), wired
  into `lint.yml` non-blocking. One real credentialed release did run
  (2026-08-19, `v0.1.0`, run `32273454405` — signed/SBOM'd images
  published to Quay), but cutting charts' `image.repository` over to Quay
  was rejected in favor of staying on the in-cluster BuildConfig path. **2026-08-22:
  closed — deferred.** `build-publish.yml`'s automatic triggers disabled
  (`workflow_dispatch` only); confirmed no chart depends on quay.io for
  deployment; confirmed every zuno-authored component (including `mlops`)
  still has a working in-cluster BuildConfig. Gaps 2/3/4/6 stay genuinely
  open, not resolved — a future ADR will reactivate this stream if needed.
  See `RELEASING.md` and ADR-0115's 2026-08-22 note for the full trace.
- **ADR-0117 (WP-02)**: Confluence MCP server. Real MCP server
  (`components/mcp-servers/confluence/`, official SDK, streamable-HTTP)
  against the live Confluence Cloud REST API; `tool-bindings.yaml` routes
  all four capabilities to it. Live e2e chain (search/read/create-denied/
  update) verified against `startxfr.atlassian.net` once Atlassian
  product access was granted. Implemented. Note: two mcp-gateway test
  files (`test_downstream_sales_db.py`, confluence's
  `test_mcp_protocol.py`) are standalone async scripts — run as `python
  test_x.py`, not via pytest (pytest misreads their `transport` param as
  a missing fixture).
- **ADR-0330 (WP-07)**: rag-ingestion Confluence catalog. `spaces:
  ["SXSI"]` (not `SXS` — corrected after a live space enumeration),
  `directories:` scoped per the real page tree; space-identifying path
  segments were dropped from `_ancestor_path_matches` since it only ever
  sees Confluence page-tree ancestor titles, never the space key.
  Recurring-run installer now lists-and-reconciles existing KFP recurring
  runs instead of blind-creating (the v2beta1 API returns pipeline
  versions oldest-first, and `max_concurrency` has no usable 0 default —
  both were real bugs, fixed in `ansible/roles/rag_ingestion/tasks/
  recurring_run.yml`). `compile_pipeline_version.yml` compiles and
  uploads a `PipelineVersion` before the recurring-run step, so a fresh
  install has something to run against. Done.
- **ADR-0106 (WP-05)**: OKF bundle signing pipeline merged
  (`sign_okf_bundle.py`/`validate_okf_bundle.py`, keyless cosign, wired
  into `build-publish.yml`/`lint.yml`). `ZUNO_REQUIRE_SIGNED_BUNDLES`
  (default false) enforces verification once enabled. Partially
  implemented — no bundle is signed yet (needs a credentialed CI run).
- **ADR-0103 (WP-08)**: Agent Runtime workflows are resumable via an
  explicit LangGraph checkpointer (`AsyncPostgresSaver` when
  `CHECKPOINT_PG*` env is set, else in-memory). `run_id` resumes
  re-validate the checkpoint's stored `user_sub` against the caller's
  token. Implemented.
- **ADR-0104 (WP-09)**: AI Gateway opt-in semantic cache for
  non-streaming completions (`semantic_cache.py`, shared Redis, SimHash
  bucketing). Two-gated (chart flag AND per-model `cache_enabled`); cache
  key binds model/subject/classification/local-only/task; infra failures
  fail open (perf-only, never a security control). Implemented.
- **ADR-0107 + ADR-0108 (WP-10)**: model quality gates + LM-Eval. ADR-0107
  (blocking-promotion gate policy) discharged 2026-08-21 via two real
  `make d1 check agents` runs (blocked, then passing 19/20 = 95%).
  ADR-0108 (LM-Eval mechanism) closed 2026-08-22: the TrustyAI operator
  (OpenShift AI 3.5.0-ea.2) never persists a completed `LMEvalJob`'s real
  status to its own CR (`status.state` stays `Scheduled` forever, even
  though the driver pod's own log shows it computing and logging a correct
  `Complete`/`Succeeded` update) - confirmed live, RBAC ruled out as the
  cause, root cause internal to the operator/driver hand-off and out of
  this repo's control. Fixed with a workaround, not an upstream patch:
  `evaluations/benchmark.py` now reads results directly from the job's own
  `outputs.pvcManaged` PVC (`oc exec` into the still-running driver pod,
  which never exits - falls back to a short-lived reader pod if it's ever
  gone, since the PVC is `ReadWriteOnce` and can't be mounted twice
  simultaneously). Along the way, ruled out a false lead first: a GPU node
  had been cordoned since the prior day, starving every GPU pod
  cluster-wide - that's what made an earlier observation
  (`state: Complete, reason: Failed, message: ContainerStatusUnknown`)
  look like the bug when it was really unrelated infra fallout. Both ADRs
  now Implemented; WP-10 Done.
- **ADR-0111 (WP-11)**: SecNumCloud hardening control matrix
  (`docs/security/secnumcloud-controls.md`) plus
  `check_workload_hardening.py`'s `check_no_hardcoded_secret_values`.
  Partially implemented — remaining gap rows owned by WP-12 (HA/PDB),
  WP-13 (backup) and WP-26 (binding auth-mode), each closed below.
- **ADR-0101 + ADR-0102 (WP-12)**: HA-capable shape for shared services.
  PostgreSQL/Redis were already replica+PDB-complete by default; added
  `topologySpreadConstraints` to PostgreSQL (skipped for Redis, single-pod
  by design); agent-runtime/ai-gateway/mcp-gateway/rag-service gained a
  PodDisruptionBudget + soft topology spread. `docs/platform/slo.md`
  defines the 99.9% monthly SLO with burn-rate alerting (disabled by
  default); fixed the OTel Collector only exporting to stdout (added a
  `prometheus` exporter). Both ADRs closed after a live failover drill and
  a 24h SLO measurement — see `docs/platform/slo.md` for the drill record
  (30-day series completes ~2026-09-17). Implemented.
- **ADR-0112 (WP-13)**: backup/restore. PostgreSQL backups (pgBackRest
  weekly full + daily differential) were already configured; added a Day
  1 recency check. Vault backs up via a daily CSI VolumeSnapshot CronJob
  (disabled by default). Both restore drills executed live (PostgreSQL:
  scratch-cluster restore via `dataSource.postgresCluster`, WAL-replayed
  to near-continuous RPO; Vault: PVC-from-snapshot, unsealed, secret
  verified) — see `docs/platform/backup-recovery.md` for the drill
  record. Implemented.
- **ADR-0322 (WP-06)**: OGX migration + RAG provider parity.
  `rag-service`'s `ogx_provider.py` is an opt-in OGX-backed retrieval
  provider (`RAG_PROVIDER=ogx`) behind the same `hybrid_search` contract;
  the data-plane `OGXServer` CR is defined but disabled by default — kept
  deliberately deferred rather than flipped live. Three real upstream OGX
  operator bugs (schema-enum drift, an anonymous-only OCI-fetch client,
  missing `persistence` field for `remote::pgvector`) were found by
  reading the operator's own Go/Python source and fixed via
  `spec.overrideConfig`; `zuno-ogx` is now genuinely healthy live (2/2
  Running, real pgvector connection confirmed). Partially implemented,
  pending a live OGX-backed corpus proof.

### Dated entries (roadmap work packages, v0.2) — current status per ADR

- **ADR-0219 (WP-084)**: SXA as a RAG-only historical corpus — **Implemented
  / repo work merged 2026-08-26**, operator steps open. Supersedes ADR-0216
  and ADR-0217 in full (both `Abandoned` as WP-065/WP-067) and ADR-0016 in
  full. SXA is the company's pre-2021 commercial record with no live system
  behind it, so the deterministic MCP path had nothing to be authoritative
  about, and the two RAG domains were reading the same bytes from the same
  bucket. `knowledge.sxa-legacy` survives alone, widened to
  `[sales, board, adv, finance]` (the union of both domains' grants, so no
  agent lost reach — this amends ADR-0340's access-intent row and retires
  WP-35's Advantage negative test, which now guards `knowledge.sales`).
  `load-sxa-dump` keeps its name and parses the S3 dump in pure Python.
  Deleted: the five `sxa.*` capabilities, `sales-db`, the `sql-schema` Day-2
  component, `data/sxa/`, the MariaDB `sxa` database, `knowledge.sxa`.
  Two things worth remembering: deleting a tool binding turns its probes from
  403 into **404** (the gateway resolves bindings before policy), which
  silently broke ten negative scenarios across six agents including three
  unrelated to SXA; and the uninstall tasks were **kept** as retired-resource
  cleanup rather than deleted, so `make d2 uninstall` still reclaims the
  orphans on clusters installed before this landed.

- **ADR-0354 (WP-072/WP-073)**: Ansible Automation Platform. WP-072
  (`aap`) and WP-073 (`aap-config`) are both `Done`, live-verified on
  `demo222` (2026-08-25): Gateway/Controller/Hub/EDA Running, RHN
  subscription auto-attached, organization `zuno` plus its Project/
  Inventory/Credential/Job Template CRs reconciled, Keycloak SSO
  authenticator wired (API-confirmed, browser login flow still
  unverified). Four dedicated Crunchy databases confirmed live (the
  unified CR does NOT take one shared external-database secret,
  correcting the ADR's original open question). See
  `ansible/roles/aap/README.md` and `ansible/roles/aap_config/README.md`
  for the full findings, including the one accepted limitation (vault's
  precheck can't run through the least-privilege machine credential,
  `pods/exec` deliberately not granted).
- **ADR-0202 / ADR-0203 (WP-20)**: four logical knowledge-domain
  identifiers (`knowledge.tech/sales/sxa-legacy/adv`) declared in
  `knowledge/<domain>/domain.yaml`, validated by
  `platform/docs/check_knowledge_refs.py` (blocking in CI).
  `policies/knowledge/knowledge-policy.yaml` maps each domain to allowed
  Keycloak groups; enforcement is a fail-closed intersection (agent
  ceiling ∩ task `allowed_knowledge` ∩ caller groups ∩ policy) in
  `agent-runtime`'s `retrieve_node`. Fully repo-provable, no operator
  follow-up. Physical per-domain databases are WP-21 (below);
  `stale_after` enforcement is WP-24 (below).
- **ADR-0205 + ADR-0109 (WP-24)**: freshness/trust scoring. Metadata
  split into `source_modified_at` (the source's own signal) and
  `indexed_at` (pipeline clock); `stale_after` computed per-domain from
  `domain.yaml`. `rag-service`'s scoring adds provenance weight,
  continuous freshness decay and a `freshness_untrusted` rank-last
  penalty for chunks missing freshness metadata (mirrored in
  `ogx_provider.py` for provider parity). `source_mode`
  (`indexed`/`live`/`both`/`none`) is derived in `respond_node` from what
  actually contributed to the answer, returned in `ChatResponse`/SSE and
  traced via `agent_graph_run`. Fully repo-provable, no operator
  follow-up.
- **ADR-0110 (WP-25)**: ACL reconciliation. New `reconcile-acls` stage in
  `rag-ingestion` re-checks EVERY indexed Confluence chunk's `acl_groups`
  against the source's current `requiredGroups` (not just the run's
  changeset), removing chunks whose source is no longer visible; aborts
  with zero deletions if a source-listing call fails (never mistakes an
  outage for mass deletion). Authoritative ACL source is the platform's
  own declared `requiredGroups` config, not a live Confluence
  restrictions API (none exists here). Partially implemented — needs a
  live Confluence restriction-change + verified run.
- **ADR-0208 (WP-26)**: every tool binding declares an explicit
  `auth_mode` (`delegated-user`/`service-identity`/`provider-delegated`),
  never inferred from the tool name. `delegated-user` requires a
  resolvable delegated token and never falls back to a shared credential
  — a missing token is a deterministic 403. Audit trail carries
  `auth_mode`, never token material. Implemented (concrete live
  Google-token resolution is an optional operator follow-up).
- **ADR-0201 (WP-27)**: MaaS governance plane. `MaaSModelRef` wraps the
  existing vLLM predictor via `ExternalModel` rather than provisioning a
  full separate `LLMInferenceService` stack (both GPUs already
  committed). Two `MaaSSubscription`s (`agent_tekos`/`sales`) demonstrate
  differentiated rate limits; `MAAS_EXTERNAL_EGRESS_ENABLED` (default
  off) gates external-provider egress independent of the adapter flag.
  `X-Zuno-Request-Id` threads end-to-end for usage correlation. Partially
  implemented — blocked on GPU capacity and live MaaS verification.
- **ADR-0215 (WP-060, 2026-08-20)**: Tekos/Comage/Arkos previously lost
  all conversation history between turns (each prompt sent only the
  static system prompt + the newest question). Fixed: three new
  `AgentState` channels (`history`, `summary`, `history_classification`)
  carried across turns via the existing checkpoint mechanism; a shared
  `record_history` terminal node compacts older turns into a running
  summary once a token budget is exceeded (default 1800 tokens - a
  conservative floor predating ADR-0518's 32768-context chat model;
  Arkos overrides to 6000 on its C3/local-only path). Compaction stays
  local-only for C2/C3 conversations (mirrors the existing
  `app/memory.py` rule) and is tagged `zuno-internal`, filtered out of
  the user-visible SSE stream. New `app/graph/history.py` +
  `app/graph/classification.py` (split out to avoid a circular import).
  Partially implemented, WP-060 Operator pending (repo work merged) —
  residual gap is live two-turn verification on the real cluster, not yet
  attempted.

### Dated entries (roadmap work packages, v0.5) — current status per ADR

- **ADR-0511 (WP-54)**: OKF quota policy enforced via Kuadrant —
  **Implemented / Done 2026-08-25.** The 429-exceedance run passed live
  (`intensive` 429 at request 11 against 10/5m, `standard` at 61 against
  60/5m, zero 5xx, `consultant-01` with a real Keycloak token).
  The run itself found three stacked defects, all of which presented as a
  clean `200` on every request while `RateLimitPolicy` reported
  `Accepted`+`Enforced` and Limitador held all six compiled limits:
  (1) the AuthPolicy published no identity dynamic metadata, so
  `auth.identity.*` counters were unresolvable and the wasm-shim skipped
  the rate-limit call entirely; (2) the shim's CEL evaluator does not
  absorb an error in one operand of `||` as the spec requires, and one bad
  expression fails the whole message builder — which broke exactly the
  `standard` class, whose documented default is an *absent* header;
  (3) Kuadrant concatenates every limit's predicate into one `||` chain
  and `?:` binds looser, so an unparenthesized ternary is shredded.
  **Standing lesson: `Accepted`/`Enforced` plus compiled Limitador limits
  are not evidence of enforcement.** Only driving traffic past a threshold
  distinguishes enforcing from silently inert — hence
  `platform/testing/quota_429.py` as a `day2_stresstest.py` layer, and a
  generator lint asserting every `auth.identity.<name>` the counters read
  is actually published by the AuthPolicy.

### Dated entries (roadmap work packages, v0.3) — current status per ADR

- **ADR-0327 (WP-37)**: `AIAgent` CRD contract
  (`operator/aiagent-operator/api/v1alpha1/aiagent_types.go`) —
  deployment bindings/references only, no secrets/prompts/tokens.
  `validate_contract.py` enforces schema shape and reject rules a
  structural CRD schema alone can't (secret/cross-namespace fields),
  wired blocking into `lint.yml`. Implemented, no operator-pending items.
- **ADR-0308 / ADR-0350 (WP-38)**: AIAgent operator reconciler,
  generating each agent's resource set with owner references (plain-GC
  delete, no finalizer) and five status conditions. Arkos is CR-managed
  (its chart renders one `AIAgent` CR); Tekos deliberately stays
  plain-manifest to prove coexistence. Live-verified: `aiagent-operator`
  deployed and Ready, both `AIAgent` CRs (Arkos, Naveo) show all five
  conditions `True`. Both ADRs Implemented.
- **ADR-0303 (WP-39)**: per-request dynamic LoRA adapter selection
  scaffolding (`policies/model-routing/model-routing-policy.yaml`, empty
  `adapters: []` until a real GPU-trained adapter exists); the
  C2/C3-adapter-never-external guard is enforced inside
  `chat_model_for()` (local-vLLM-direct only, never via MaaS).
  Repo-complete, no adapters trained yet.
  - **2026-08-29, explicit descope decision** (not a status change): WP-34,
    the WP meant to deliver a real dynamically-loadable LoRA adapter for
    this mechanism, never ran and was superseded by WP-087/ADR-0526,
    which registered a real candidate (`comage-lora` v6) but deliberately
    serves it as a separate full model via `preferences:`, not through
    vLLM's `--lora-modules` mechanism this ADR requires. There is nothing
    to live-verify and nothing in flight will produce one. Status stays
    `Partially implemented` / `Operator pending` by user decision - don't
    re-attempt closing this pair without a genuinely new
    dynamically-loadable adapter.
  - **2026-08-30, corrected: this is a status change.** ADR-0301 (this
    mechanism's own foundation) already declares its serving-mechanism
    decision unconditionally `Superseded by ADR-0526` - not scoped to the
    wesh case - and ADR-0526's own Alternatives-considered section rejected
    keeping that mechanism intact for general reasons (same GPU cost as a
    separate deployment for one adapter, no adapter-download mechanism
    exists in `gitops/charts/models`), not wesh-specific ones. No v0.4-v0.7
    roadmap item or pre-live agent's `NEXT_STEPS.md` names a future adapter
    need. ADR-0303's Status is now `Superseded by ADR-0526` (matching
    ADR-0301/0302) and WP-39's tracker State is `Closed — deferred`, both
    with the full reasoning written directly into the ADR's own `##
    Evolution` section - not MEMORY.md-only, as the 2026-08-29 entry above
    left it. Reviving this mechanism needs a new ADR decision backed by a
    real non-merged adapter and an actual multi-adapter-sharing need (kept
    honest: ADR-0526's Consequences call this mechanism "neither
    implemented nor contradicted," not dead in principle).
- **ADR-0305 / ADR-0304 (WP-40)**, 2026-08-29, **Implemented/Done**:
  `evaluations/benchmark.py` (LM-Eval snapshot -> versioned artifact,
  `--check-policy` enforces no-artifact-no-promotion) and
  `evaluations/routing_report.py` (routing recommendations as a report
  only, never a policy write). One live loop run: `comage-lora` v6
  (WP-087/ADR-0526) benchmarked from that run's real gate results
  (`overall: PASS`), 4 objectives declared for comage's tasks, the
  report's 4 `upgrade` recommendations reviewed and rejected as
  already-applied — `comage-lora` already routes first via
  `preferences:` (ADR-0412/ADR-0526), a mechanism `routing_report.py`'s
  `adapters:`-only incumbent lookup does not model. Documented
  simplification, not a defect blocking closure.
- **ADR-0307 / ADR-0306 (WP-41)**: `platform/templates/agent/
  scaffold_agent.py` generates a new agent from template. **Naveo** is
  the first agent generated this way (consultant role, zero policy edits
  needed — proves the composition works), CR-managed from day one.
  Repo-complete.
- **ADR-0309 (WP-42)**: `policies/optimization/optimization-policy.yaml`
  + `components/ai-gateway/app/optimizer.py` — runtime-config-only
  optimization with a classification/authorization denylist, full audit
  trail, auto-rollback and a one-step kill switch. Ships `enabled:
  false`. Repo-complete.
- **ADR-0340 (WP-32)**: `confluence-archi-*` groups live under
  `/consultant`; new `cdp` group exists with no members yet (per-agent
  consumption is WP-33+). Implemented.
- **ADR-0349**: Keycloak realm baseline — 27 anonymized personas,
  `ocp-*` RBAC groups, live IdP federation. Live-verified: realm applied,
  ClusterRoleBindings wired, ArgoCD RBAC policy matches, no stale legacy
  Group objects. Implemented.
- **ADR-0204 (WP-21)**: all four domain databases/roles exist on the PGO
  cluster, each ACL'd to only its own database; `tech`/`sales`
  schema-apply Jobs Complete. Fixed a real regression: `make d1 check
  rag`'s precheck looked up a retired hardcoded Job name instead of
  matching on the `app.kubernetes.io/name=rag-service` label — now
  fixed. Partially implemented — WP-22 (source adapters' live runs)
  remains.

**2026-08-16 live-cluster verification session** (demo222) found and
fixed roughly 15 real bugs during the platform's first full end-to-end
exercise — worth remembering since these are the kind of thing that
silently recurs: Keycloak 25→26 behavior changes (varchar(255) import
abort, vault-file `__` escaping, import-time vs runtime secret
resolution, `basic` scope required for `sub`, self-audience mappers,
required firstName/lastName); stale hardcoded issuers + JWKS-over-Route
TLS across all 4 services (new `KEYCLOAK_JWKS_URL` seam); served-model-
name vs canonical model id split; PgBouncer needs direct-to-primary
routing for `search_path`/prepared statements; pgvector text-format
serialization; `AsyncPostgresSaver` needs a pooled (not single)
connection; fleet-wide `imagePullPolicy: Always` is required (stale
`:latest` image cache otherwise); acceptance-gate Job needs `HOME` +
per-agent ConfigMap projections + an internal CA. Remaining gate failures
are scenario-design/harness/credential issues, not platform defects.
Credential-blocked pending operator action: Route53 (ADR-0211),
Salesforce, rag-S3, MaaS key. (Aramis dropped 2026-08-26, ADR-0218.)

**2026-08-21: ADR-0059 formalizes the in-cluster build → auto-redeploy
trigger** (`image.openshift.io/triggers`, shipped by commit `649243c`
hours before this ADR was written) — a `make d1 build <component>` now
rolls a fresh Deployment automatically via an OpenShift annotation-based
controller, with matching ArgoCD `ignoreDifferences` and an
`aiagent-operator` reconcile guard so neither fights the patch. `:latest`
tracking is load-bearing for this: this same session's WP-04 release pin
(`v0.1.0`) briefly broke the trigger for 16 components by repointing
chart `image.tag` off `latest` — confirmed live (another session's fresh
`agent-bff:latest` build sat undeployed) and reverted same-day. Release
pinning is a point-in-time snapshot proof, not a standing chart-tracking
target; revert to `latest` immediately after proving it.

### Dated entries (roadmap work packages, v0.4) — current status per ADR

- **ADR-0525**, 2026-08-30, **Implemented (live-verified)**: batched
  `executemany()` writes (1000-row batches) and ivfflat `lists` sized from
  real row counts in `components/rag-ingestion/src/rag_ingestion.py`'s
  `index-pgvector` stage, plus `007_ivfflat_lists.sql`'s migration for
  existing databases. Live-verified via a real `knowledge.tech` one-off
  run (`5e751c12`): `943/943 documents processed, upserted 65926 chunk
  rows, deleted 0 orphaned rows`, no errors; `ix_document_embeddings_
  embedding_cosine` stayed at `lists='68'` for 68945 -> 68962 rows,
  exactly matching `clamp(rows/1000, 10, 1000)`. The drop/rebuild branch
  didn't trigger in this run (net-new delta far below the 20% threshold)
  but was already independently proven correct by the migration script
  producing the same value. No WP tracks this ADR.
- **ADR-0526 (WP-087)**, 2026-08-27, **Repo work merged**, not yet
  live-verified: a French urban-register variant of ADR-0518's Qwen3.5-9B
  training base — LoRA rank 8, merged into a standalone bf16 checkpoint,
  served as `qwen3.5-9b-wesh` beside its unmodified base on a different
  MIG node. Comage routes to it first on all four of its tasks, Tekos
  second on all four of its own. Supersedes ADR-0301 (decisions 1, 5) and
  ADR-0302 (decisions 2, 4) in part.
  - **It closed the two independent reasons WP-34's pipeline had never
    run**, neither of which was visible without executing it: nothing in
    the repository compiled or uploaded a `PipelineVersion`, and the
    compiled DAG name (`mlops-<agent>`) referenced a `Pipeline` CR that
    was never rendered.
  - **Four defects that neither the ADR nor the brief listed**, each
    fatal on its own: the mlops image never copied `policies/` or
    `platform/ai-gateway/`, which the gate's own checks read via
    `parents[2]`; no persona credentials reached the pod, so
    `run_scenarios.py` raised immediately; the tokenizer step produced no
    `labels`, so `Trainer.train()` had nothing to compute a loss from;
    and `ArtifactStore` had one boto3 client for two buckets in two
    regions, which raises `PermanentRedirect` rather than following.
  - **`target_modules` must be an anchored regex, not a suffix list.**
    `mtp.layers.N.self_attn` carries `q_proj`/`k_proj`/`v_proj`/`o_proj`
    under those exact names, so a suffix list injects LoRA into the
    multi-token-prediction head, and `peft` 0.13 has no `exclude_modules`
    to undo it. Verified against the real `model.safetensors.index.json`:
    the anchored form matches exactly 80 modules and zero `mtp.*` or
    `model.visual.*`.
  - **The register half of the gate cannot be scenarios.** Anything added
    to `scenarios.yaml` lands in the ADR-0028 denominator, where two
    failing additions to twenty still score 91% and report PASS. It is
    computed independently and AND-ed with the acceptance result.
  - **The style corpus is the ground truth for the scorer's thresholds,
    and it caught a real bug.** A first protected-span detector treated
    any line beginning with a tool name as a shell command, so `git garde
    l'historique de ton code… c'est le sang` — a French sentence whose
    subject is git — produced false violations. Shell and YAML now
    require real delimiters. Zero false positives across all 908
    reference responses.

### Dated entries (OKF stream) — current status per ADR

- **ADR-0501**, 2026-08-29, **Accepted**: the OKF stream/roadmap mechanic
  (05xx ADR band, `docs/roadmap/okf-roadmap.md` tracker, WP-43 onward) is
  in force and its OKF v0.1 milestone is done (WP-43/44/45/46/54/56/061,
  all Done). OKF v0.2 (extraction to a standalone `zuno-okf` repo) and
  OKF v0.3 (live reconciliation) remain open future work under this
  stream, not yet started.
