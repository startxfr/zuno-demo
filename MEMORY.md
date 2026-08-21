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
- Two CPU worker nodes; GPU capacity per ADR-0351: one permanent
  g7e.4xlarge node (NVIDIA RTX PRO 6000 Blackwell 96GB, MIG-partitioned
  `all-balanced` = 2x 1g.24gb + 1x 2g.48gb slices for the three inference
  workloads) plus a scale-from-zero tainted burst node (whole GPU, for
  training) and a replicas-0 AZ-failover MachineSet - all managed by
  `gitops/charts/machines`.
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

LoRA/PEFT is an architectural future capability. Comage is the first candidate. Desired benefits are lower response time, lower token consumption and improved relevance.

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
- DAT output may include architecture diagrams, with Lucidchart integration planned.
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

The provided source is a legacy phpMyAdmin schema dump for MySQL 5.0.95. It is a schema reference, not the PostgreSQL target implementation. The demo must provide a PostgreSQL migration/bootstrap path and load the separate approved demo data dump.

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

The PostgreSQL target migration should preserve the business semantics, introduce explicit constraints where safe, map identity to Keycloak, and support controlled demo writes.

## 11. Sales database access policies

- Comage normally sees deals for the authenticated sales owner; `sales_admin` may see all permitted sales records.
- Advantage sees business at client-PO-received / administration states and later.
- Finage sees billable (`A facturer`) and invoiced states.
- Comage, Advantage and Finage may perform controlled writes, at minimum approved state transitions.
- SQL tools should be deterministic where possible and stored with the GitOps agent definition.
- Arbitrary model-generated writes are not trusted. The AI platform validates tool, operation, user authorization, business rule and state transition before execution.
- The repository contains no real SXA data. Only anonymized/synthetic fixtures may be committed.

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
- **Data**: from-scratch PostgreSQL-native SXA schema (`data/sxa/schema/`,
  §10), synthetic fixtures, sales-db MCP server.
- **AI/model layer**: local Qwen2.5-7B-Instruct serving; AI Inference
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
  one precise per-workload NetworkPolicy instead (ADR-0037 requires
  `sales-db-mcp` to reject same-namespace neighbors too). `sales-db-mcp`
  also validates a shared `X-Zuno-Gateway-Token` workload-identity secret
  independent of the network boundary.
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
  filled in by WP-063. Repo work merged; live cluster confirmation
  (`make d2 test` against a real cluster) still pending.
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
- **ADR-0115 stage 1 (WP-04)**: supply-chain tooling merged
  (`platform/supply-chain/verify_signatures.py`, `pin_release.py`), wired
  into `lint.yml` non-blocking. No credentialed release has run yet — see
  `RELEASING.md` for the release process and current blocker.
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
  summary once a token budget is exceeded (default 1800 tokens, sized for
  qwen2.5-7b's 8192 context; Arkos overrides to 6000 since its
  C3/local-only path uses gpt-oss-20b's 32768 context). Compaction stays
  local-only for C2/C3 conversations (mirrors the existing
  `app/memory.py` rule) and is tagged `zuno-internal`, filtered out of
  the user-visible SSE stream. New `app/graph/history.py` +
  `app/graph/classification.py` (split out to avoid a circular import).
  Partially implemented, WP-060 Operator pending (repo work merged) —
  residual gap is live two-turn verification on the real cluster, not yet
  attempted.

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
- **ADR-0305 / ADR-0304 (WP-40)**: `evaluations/benchmark.py` (LM-Eval
  snapshot -> versioned artifact, `--check-policy` enforces
  no-artifact-no-promotion) and `evaluations/routing_report.py` (routing
  recommendations as a report only, never a policy write). Repo-complete.
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
Salesforce, Aramis, rag-S3, MaaS key.
