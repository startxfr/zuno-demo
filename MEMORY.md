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
- Two worker nodes, one NVIDIA L4 24 GB GPU per node.
- NVIDIA GPU Operator deployed as a prerequisite.
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

Variants are selected to fit NVIDIA L4 24 GB GPUs. OpenShift AI model serving is used for local inference. KServe, Models-as-a-Service and llm-d are included in the architecture where relevant to OpenShift AI 3.5 EA2 capabilities.

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

2026-08-14: execution of the open v0.1/v0.2/v0.3 ADRs is decomposed into
work packages in `docs/roadmap/v0.1-v0.3-implementation-roadmap.md`, one
self-contained brief per WP under `docs/roadmap/work-packages/` (written for
standalone execution by a lower-capability model). Conventions: WP state
machine `Not started -> Repo work in review -> Repo work merged -> Operator
pending -> Done`; ADR status strings live only in `docs/adr/README.md` and
ADR bodies (checked by `platform/docs/check_docs.py`) — the roadmap tracks
WP state only; stub ADRs are promoted to full files (Step 0 of their brief)
before implementation; every brief separates model-executable repo changes
from operator/cluster steps.

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
This section is a dated changelog kept for future work-package execution
(each roadmap WP appends one dated entry on merge, see
`docs/roadmap/v0.1-v0.3-implementation-roadmap.md`); entries are terse
status facts, not narrative. Current state only — a later entry overrides
an earlier one on the same topic. Full rationale lives in the cited ADRs
under `docs/adr/`.

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
  fails (6 charts on `tag: latest`) until a real release is cut — see
  `RELEASING.md`.
- **Evaluation gate** (ADR-0027/0028/0053): `make day1|d1 check agents`
  runs `ansible/roles/agents/tasks/check.yml`'s OKF-structural + `/healthz`
  smoke checks, then `run_acceptance_gate.yml` runs
  `evaluations/tekos/run_acceptance_gate.py` as a one-shot in-cluster Job
  in `zuno-ai-run`, combining the 20 Tekos scenarios (75% threshold) with
  `security_checks.py` and `gate_checks.py` (both 100% mandatory) into one
  exit code. `components/{agent-runtime,mcp-gateway}/tests/test_auth.py`
  prove expired/untrusted-key JWTs are rejected, fully offline.
- **ADR-0350** (AIAgent CRD/operator) is retargeted from v0 to v1 — Tekos
  deploys as a plain `Deployment`.
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
  (not the shared `zunoapp` app-data database). Unverified against a live
  cluster — see `ansible/roles/keycloak/README.md`.
- **Namespace consolidation** (ADR-0328/0329, 2026-08-12): `zuno-ai-platform`
  exists in `gitops/charts/namespaces` as the future OpenShift AI
  applications namespace (ADR-0328; DSC wiring to it is out of scope for
  now). ADR-0329 supersedes ADR-0023: the per-agent `zuno-agent-<name>`
  namespace model is retired — per-workload NetworkPolicies (ADR-0037)
  already carried real isolation. All Tekos workloads now live in
  `zuno-ai-run` alongside Agent Runtime/AI Gateway/MCP Gateway; the four
  placeholder agents carry no namespace footprint until their FE/BFF
  charts exist.

### Dated entries (roadmap work packages, v0.1)

- **2026-08-14 (ADR-0116, WP-01)**: MCP Gateway routes through a platform
  backend-binding registry (`platform/bindings/tools/tool-bindings.yaml`,
  `components/mcp-gateway/app/bindings.py`) instead of hard-coded
  tool-name sets. Canonical `<domain>.<resource>.<verb>` capability IDs
  are the stable contract; legacy names (`search_confluence`,
  `get_customer`, …) remain aliases. Unknown/unbound capabilities fail
  closed before any backend contact; startup + `/readyz` validate every
  policy-listed capability resolves to exactly one binding.
- **2026-08-14 (ADR-0114, WP-03)**: `components/ai-gateway/app/
  maas_adapter.py` is a MaaS adapter prototype behind the existing
  OpenAI-compatible client. Two-gated (`via_maas: true` per provider in
  `platform/ai-gateway/provider-routing.yaml` AND chart
  `maasAdapter.enabled`, default false — no provider opts in yet).
  Classification eligibility always evaluates first regardless of
  transport. Coverage comparison:
  `docs/roadmap/evidence/adr-0114-maas-coverage.md`. Live MaaS
  verification/cutover is an operator step (WP-27).
- **2026-08-14 (ADR-0115 stage 1, WP-04)**: added
  `platform/supply-chain/verify_signatures.py` (`cosign verify` against
  immutable-tagged first-party images — nothing to verify yet, every
  chart is `tag: latest`) and `pin_release.py` (rewrites chart `tag`
  fields from an operator-authored release manifest). Both wired into
  `lint.yml` as `continue-on-error: true`. `RELEASING.md` documents the
  release sequence. Neither closes an ADR-0115 gap alone — all remaining
  gaps block on the real credentialed release run.
- **2026-08-14 (ADR-0117, WP-02)**: `components/mcp-servers/confluence/`
  is a real MCP server (official `mcp` SDK, streamable-HTTP) implementing
  `confluence.page.search/read/create/update` against the real Confluence
  Cloud REST API (Basic Auth, `zuno/confluence/technical`,
  service-identity mode/ADR-0208). `tool-bindings.yaml` routes all four
  capabilities to it; the old demo-mode handler is deleted. New charts
  `gitops/charts/mcp-confluence/` + `gitops/apps/mcp-confluence/`, built
  via `ansible/roles/mcp_build`. Protocol-tested against a mocked
  Confluence API; live tenant verification is an operator step.
- **2026-08-14 (ADR-0106, WP-05)**: OKF bundles get a signing/validation
  pipeline. `platform/supply-chain/sign_okf_bundle.py` computes a
  deterministic sha256 digest and signs/verifies with keyless `cosign
  sign-blob`/`verify-blob` (same GitHub OIDC identity as image signing),
  wired as `build-publish.yml`'s `sign-okf-bundles` job.
  `validate_okf_bundle.py` checks OKF schema + tool-policy validity, wired
  into `lint.yml` as a hard gate. Agent Runtime's
  `ZUNO_REQUIRE_SIGNED_BUNDLES` (default false) enforces verified
  signatures when enabled. No bundle is signed yet (needs WP-04 stage 2's
  credentialed CI run) — ADR-0106 stays Partially implemented, flag off.
- **2026-08-14 (ADR-0103, WP-08)**: Agent Runtime workflows are resumable.
  `build_graph()` takes an explicit LangGraph checkpointer;
  `AsyncPostgresSaver` is used when `CHECKPOINT_PGHOST/PORT/DATABASE/
  USER/PASSWORD` are all set, else `MemorySaver` (default, not resumable
  across restarts). `POST /v1/agents/tekos/chat` gains optional
  request/mandatory response `run_id`; resuming re-checks the checkpoint's
  stored `user_sub` against the caller's token (403 on mismatch, 404 on
  unknown/expired run). Dedicated `agent-checkpoints` DB on
  `zuno-postgresql`. Fully Implemented, no operator step required.
- **2026-08-14 (ADR-0104, WP-09)**: AI Gateway gets an opt-in semantic
  cache for non-streaming `/v1/chat/completions`
  (`components/ai-gateway/app/semantic_cache.py`), stored in the shared
  platform Redis. Two-gated (chart `semanticCache.enabled` AND a model's
  `cache_enabled: true`). Prompts are embedded via the shared embedding
  service and bucketed with fixed-seed SimHash. Cache key binds model
  identity, caller subject, effective classification, local-only
  requirement and task — any difference is a guaranteed miss.
  Infrastructure failures fail open (cache is perf-only, never a security
  control; eligibility always checked first). Streaming is not cached.
  Fully Implemented, no operator step required.
- **2026-08-14 (ADR-0111, WP-11)**: first SecNumCloud hardening
  increment. `docs/security/secnumcloud-controls.md` is the control
  matrix (deployment/supply-chain/identity/network/data families, each
  row `enforced-in-ci`/`enforced-on-cluster`/`gap` with its enforcing
  file); `check_workload_hardening.py` remains authoritative and now adds
  `check_no_hardcoded_secret_values` (no chart embeds a literal secret
  value). Closed a real gap: `zuno-ai-run` was silently getting an
  all-ports same-namespace NetworkPolicy from the generic
  `platformNamespaces` loop, contradicting ADR-0037/0052 — fixed via a
  `skipNetworkPolicy: true` flag on that entry (never deployed live yet,
  `policy.enabled` is false there). `check_workload_hardening.py` passes
  95/95. ADR-0111 stays Partially implemented — remaining `gap` rows are
  owned by WP-12 (HA/PDB), WP-13 (backup) and WP-26 (binding auth-mode).
- **2026-08-15 (ADR-0111 control-matrix sync)**: WP-12/13/26 had each
  merged their repo half without flipping their owned `gap` rows in
  `docs/security/secnumcloud-controls.md`, contradicting the matrix's own
  "how to update" rule. Flipped auth-mode enforcement, backup
  configuration/recency-check and PDB/topology-spread rows to
  `enforced-in-ci` with concrete citations; split the backup row into
  "configured" (closed) vs. "restore drill executed" (still `gap`, live);
  reworded the SLO row to name its two real missing prerequisites
  (`agent-bff`'s `zuno_bff_requests_total` metric, unconfirmed
  `ServiceMonitor` scrape). No code changed — every remaining `gap` row in
  the matrix is now genuinely live-cluster-only. ADR-0111 status line
  updated with a dated Implementation note; no ADR-0111 index-row change
  (label stays Partially implemented).
- **2026-08-14 (ADR-0322, WP-06)**: OGX migration + RAG provider parity.
  DataScienceCluster already has `ogx.managementState: Managed` and the
  deprecated Llama Stack component `Removed`; live cluster confirms
  `OGXReady: "True"`. `ansible/roles/openshift_ai`'s Day 1 OGX check is a
  real readiness gate on that condition now. `components/rag-service/app/
  ogx_provider.py` is an OGX-backed retrieval provider behind the same
  `hybrid_search` contract, opt-in via `RAG_PROVIDER=ogx` (default
  `pgvector`) and chart `ogxProvider.enabled`. `spec.components.ogx:
  Managed` installs only the OGX Operator — the data-plane `OGXServer` CR
  (`ogxservers.ogx.io/v1beta1`) is defined at `gitops/charts/openshift-ai/
  templates/ogxserver.yaml` (disabled by default, wired to this repo's
  own PostgreSQL/pgvector and KServe/vLLM) but nothing has created one
  yet, so the adapter has never run against a live OGX endpoint — it
  over-fetches and re-applies the same fail-closed filter semantics
  `app/search.py` enforces in SQL, as defense in depth.
  `tests/test_provider_parity.py` proves both providers agree on
  row-mapping and schema. ADR-0322 stays Partially implemented — live DSC
  reconciliation and an OGX-backed corpus proof are operator follow-ups.
- **2026-08-14 (ADR-0330, WP-07)**: rag-ingestion catalog completion.
  `components/rag-ingestion/tooling/verify_catalog.py` HTTP-verifies every
  `redhat[]` entry's `documentationUrl` (meant to run from a network that
  can reach `docs.redhat.com`; blocked here). Its test file
  (`tooling/tests/test_verify_catalog.py`) is rag-ingestion's first
  committed test. All 32 non-Satellite `redhat[]` entries carry a
  `# CONFIRM` marker pending that verification; Confluence
  `spaces:`/`directories:` values carry an `# operator-supplied` marker —
  no real space key exists in this repo. ADR-0330 stays Partially
  implemented — live HTTP verification, real Confluence credentials, and
  KFP/DSPA checks need operator/cluster access.
- **2026-08-14 (ADR-0107 + ADR-0108, WP-10)**: model/agent promotion
  quality gate. `evaluations/quality_gate.py` runs an agent's
  `run_acceptance_gate.py`, then re-derives PASS/FAIL from a
  per-agent-configurable threshold in `evaluations/<agent>/
  gate_config.yaml` (tekos seeded at 0.75) rather than a hardcoded
  constant. `security_checks`/`gate_checks` stay 100% mandatory
  regardless of threshold; an agent with no `gate_config.yaml` fails
  closed. `lint.yml`'s `quality-gate` job smoke-checks only agents whose
  eval directory changed, and never claims a live PASS/FAIL verdict (no
  cluster in CI). For ADR-0108: `LMEvalJob`
  (`trustyai.opendatahub.io/v1alpha1`) is real and the DSC's `trustyai`
  component is already `Managed`; `gitops/charts/models/templates/
  lmevaljob.yaml` adds one CR per `lmEval.jobs[]` entry, disabled by
  default, opt-in per candidate model. Both ADRs stay Partially
  implemented — a real GPU LM-Eval run and one exercised promotion need
  cluster access.
- **2026-08-14 (ADR-0101 + ADR-0102, WP-12)**: HA-capable shape for every
  shared service. PostgreSQL (PGO) and Redis (Bitnami) were already
  replica/PDB-complete by their own defaults; the only real gap was
  `topologySpreadConstraints` (added to PostgreSQL; skipped for Redis, a
  genuinely single-pod standalone design). agent-runtime/ai-gateway/
  mcp-gateway/rag-service each gained a PodDisruptionBudget +
  `whenUnsatisfiable: ScheduleAnyway` topology spread (soft — no-op on a
  single-node cluster). Keycloak gets a hand-authored PDB and
  `spec.scheduling.topologySpreadConstraints` on its CR. Replica/instance
  counts are unchanged (demo-scale 1) — this WP ships the mechanism, not
  a topology change. `check_workload_hardening.py` gains availability
  checks (116/116 passing). For ADR-0102: `docs/platform/slo.md` defines
  the 99.9% monthly SLO (BFF-boundary success ratio) with a multi-window
  burn-rate alert policy (`gitops/charts/observability/templates/
  prometheusrule-slo.yaml`, disabled by default). Found the OTel
  Collector's metrics pipeline exported only to `debug` (stdout) — no
  metric from any service was Prometheus-queryable; added a `prometheus`
  exporter. Still missing: a ServiceMonitor for that exporter, and
  `agent-bff`'s `zuno_bff_requests_total` metric the SLO query needs (see
  `docs/platform/slo.md`'s "Current gap"). Both ADRs stay Partially
  implemented — a failover drill and a real 30-day SLO measurement need
  cluster access.
- **2026-08-14 (ADR-0112, WP-13)**: PostgreSQL backups were already fully
  configured and running (pgBackRest, weekly full + daily differential,
  inside the 24h RPO); added a Day 1 recency check
  (`ansible/roles/postgresql/tasks/precheck.yml`, diagnostic only). Vault
  uses `file` storage (no Raft snapshot API) — backup instead via a daily
  CSI VolumeSnapshot CronJob (`gitops/charts/vault/templates/
  cronjob-backup.yaml`, disabled by default, prunes to newest N).
  `docs/platform/backup-recovery.md` documents per-service RPO/RTO
  (≤24h/≤4h) and the tested runbook: PostgreSQL restore-to-scratch-cluster
  via `spec.dataSource.postgresCluster` (never destructive in place),
  Vault restore via a new PVC from the snapshot, GitOps config needing no
  separate backup (git is the backup). ADR-0112 stays Partially
  implemented — both restore drills are unexecuted operator follow-up.

### Dated entries (roadmap work packages, v0.2)

- **2026-08-15 (ADR-0202/ADR-0203, WP-20)**: introduced the four logical
  knowledge-domain identifiers (`knowledge.tech`, `knowledge.sales`,
  `knowledge.sxa-legacy`, `knowledge.adv`) as a declarative repo contract:
  `knowledge/<domain>/domain.yaml` (taxonomy, freshness objective,
  classification defaults — no physical DB/endpoint/secret) +
  `knowledge/metadata-schema.yaml` + `platform/docs/check_knowledge_refs.py`
  (wired blocking in CI, validates descriptors and rejects any
  `knowledge.*` reference under `agents/`/`policies/` not declared there).
  `policies/knowledge/knowledge-policy.yaml` maps each domain to allowed
  Keycloak groups, analogous to `policies/tools/tool-policy.yaml`. New
  `zuno.allowed_knowledge` OKF task field, declared on Tekos's
  `answer-technical-question`/`find-relevant-docs` tasks
  (`knowledge.tech`); the agent-level ceiling is a derived union
  (`AgentDefinition.declared_knowledge()`), mirroring `declared_tools()` —
  no separate agent-level field. `components/agent-runtime/app/
  knowledge.py` (`KnowledgePolicyStore` + `evaluate_knowledge()`) enforces
  the fail-closed ADR-0203 intersection (agent ceiling ∩ task
  `allowed_knowledge` ∩ caller groups ∩ policy) in `retrieve_node` before
  every rag-service call, skipping retrieval entirely when nothing is
  authorized. rag-service gained an additive `domains`/`technology` filter
  (`app/search.py`, `app/ogx_provider.py` in lockstep for parity) as
  defense in depth; untagged legacy rows default to `knowledge.tech`. Both
  ADRs fully repo-provable — no operator follow-up. Physical bindings/
  per-domain databases are WP-21; `stale_after` enforcement is WP-24.

- **2026-08-15 (ADR-0205 + ADR-0109, WP-24)**: freshness routing and trust
  scoring, both ADRs fully repo-provable (mocked live tools) — no operator
  follow-up. Split the old conflated `last_modified` metadata field into
  `source_modified_at` (the source's own signal — Confluence's
  `lastUpdated`, Salesforce's `LastModifiedDate`, Aramis' `updated_at`, a
  best-effort HTTP `Last-Modified` header for product docs, or `fetched_at`
  as a last resort) and `indexed_at` (the pipeline's own clock at normalize
  time); `stale_after` is now computed from each domain's `STALE_AFTER`
  chart value in `gitops/charts/rag-ingestion/values.yaml`, mirroring the
  new `freshness.operation_classes.{semantic-read,current-state-read}.
  max_staleness` blocks in every `knowledge/<domain>/domain.yaml`
  (validated by `check_knowledge_refs.py`). `rag-ingestion`'s validate
  stage fails closed on any operational-domain chunk missing the trio
  (`knowledge.sxa-legacy` exempt). `rag-service`'s `_is_stale` now parses
  full ISO datetimes (was date-only) for sales' hours-scale window;
  `_apply_soft_adjustments` gained provenance weight (real URL vs.
  fixture-marker provenance), continuous freshness decay (replacing the
  old flat `_STALE_PENALTY_FACTOR` — same constant, now a floor) and a
  `freshness_untrusted` flag + heavy rank-last penalty for chunks missing
  `indexed_at`/`stale_after` — mirrored in `ogx_provider.py` for provider
  parity. Agent Runtime's `_live_read_trigger_reason` (feeding
  `should_call_tools`) fires on an explicit current-state question, a
  policy-marked freshness-sensitive domain (`knowledge.sales`), or a
  retrieved doc past its `stale_after`; `source_mode`
  (`indexed`/`live`/`both`/`none`) is computed in `respond_node` from what
  actually contributed to the answer (never from what was merely
  attempted), returned in `ChatResponse` and the SSE `done` event, and
  traced via a new `agent_graph_run` OTel span
  (`app/telemetry.py:graph_run_span`). Write-path invariant tests (no
  write-shaped SQL/HTTP verb in any retrieval code path) added to
  rag-service, rag-ingestion and agent-runtime. New per-domain
  `zuno.rag_freshness_lag_seconds` histogram plus a gated
  `PrometheusRule` (`gitops/charts/observability`) alerting each domain
  against its own freshness objective.

- **2026-08-15 (ADR-0110, WP-25)**: promoted ADR-0110, honestly scoped
  during implementation — the brief's "re-reads current source
  authorization" assumed a live Confluence restrictions API that doesn't
  exist in this repo; the actual authoritative source of `acl_groups` is
  the platform's own declared `requiredGroups` config
  (`gitops/charts/rag-ingestion/values.yaml`), same as `fetch-confluence`
  already used. New `reconcile-acls` stage
  (`components/rag-ingestion/src/rag_ingestion.py`) runs after `validate`
  over EVERY indexed Confluence chunk (not just the run's changeset — an
  unchanged document's authorization can still drift): updates
  `acl_groups` when a source's `requiredGroups` changed, removes chunks
  whose source is no longer visible or has fallen outside every
  configured source's scope (fail closed — retrieval-side filtering alone
  isn't sufficient), and aborts the whole stage with zero deletions if a
  source listing call fails (never mistakes a transient outage for mass
  deletion). Gave the previously-dead `preserveAcl` per-source field real
  meaning: `false` confirms a page's continued existence without ever
  letting reconciliation overwrite manually-curated `acl_groups`. Wired
  into the KFP DAG after `validate` for every domain (a no-op wherever no
  Confluence source is configured). ADR-0110 stays Partially implemented
  — operator follow-up (live Confluence restriction change + verified
  run) unchanged from the brief.

- **2026-08-15 (ADR-0208, WP-26)**: every binding in
  `platform/bindings/tools/tool-bindings.yaml` (13 entries) now declares a
  required, explicit `auth_mode` (`delegated-user` | `service-identity` |
  `provider-delegated`), never inferred from the tool/capability name -
  `drive.*`/`gmail.*` are `delegated-user`, everything else (`sxa.*`,
  `confluence.page.*`, `web.page.search`, `email.report.send`) is
  `service-identity`. `components/mcp-gateway/app/bindings.py`'s loader
  fails closed on a missing/unrecognized mode. Enforcement lives in
  `main.py`'s `invoke_tool`, between the policy decision and the
  downstream call: `delegated-user` requires a resolvable delegated token
  (new `app/delegation.py` - a documented seam, since no component
  resolves a real Keycloak Google-broker token yet; the CONTRACT is fully
  enforced today, only the concrete resolution is pending a live
  integration) and NEVER falls back to a shared credential - a missing
  token (including a "revoked" one at the mock level) is a deterministic
  403, identical in shape to a policy denial. `provider-delegated` is
  schema-only (501, no binding uses it yet). `downstream.py` and all four
  in-process handlers (`drive`, `gmail`, `web_search`, `email_report`)
  thread an optional `delegated_token` kwarg. Audit trail (log line + OTel
  span) carries `auth_mode` alongside subject/capability/binding - never
  token material, verified by a dedicated test. Fully repo-provable - ADR-0208
  flips straight to Implemented; optional live Google-revocation
  confirmation left for the operator.

- **2026-08-15 (ADR-0201, WP-27)**: MaaS governance-plane manifests, key
  lifecycle, correlation and guards - live MaaS verification pending.
  `gitops/charts/models/templates/maas.yaml` publishes the local chat
  model through `MaaSModelRef`, wrapping the existing vLLM predictor's
  OpenAI-compatible endpoint via an `ExternalModel`
  (`maas.opendatahub.io/v1alpha1`) rather than `LLMInferenceService` -
  the latter is a FULL SEPARATE serving stack per its live-cluster schema
  (`model.uri`, no reference to an existing InferenceService), and this
  cluster's two GPUs are already both committed, so duplicating one would
  need real capacity/migration planning out of this WP's scope; the
  ExternalModel choice is flagged `# CONFIRM` since its own schema
  description reads as designed for genuinely external providers, not
  confirmed for an internal Service. Two `MaaSSubscription`s
  (`agent_tekos`/`sales`) demonstrate different access via differentiated
  token-rate limits (MaaSSubscription has no separate "which models"
  axis beyond rate); one `MaaSAuthPolicy` scoped to just those two groups
  proves denial-by-omission for any other group. Every CRD field checked
  live (`oc explain`, 2026-08-15) except explicitly marked
  `# CONFIRM`/`# verify-on-cluster` fields. New
  `externalsecret-maas.yaml` + a `maas/gateway-api-key` Vault seed close
  the API-key lifecycle gap the adapter already expected but nothing
  populated. `X-Zuno-Request-Id` now threads end to end (agent-runtime's
  `AgentState.request_id` → `ModelRouter` → ai-gateway's `model_call_span`
  → `maas_adapter.chat_model_via_maas`'s own header) for usage/trace
  correlation. New `MAAS_EXTERNAL_EGRESS_ENABLED` gate (default off,
  independent of `MAAS_ADAPTER_ENABLED`) blocks external-provider egress
  through MaaS until explicitly opted in - 2 new security-negative tests,
  alongside the existing WP-03 C3/local-only eligibility test. Day 1 check
  extended, diagnostic only. Everything new ships disabled by default.
  ADR-0201 stays Partially implemented; every ADR-0201 acceptance bullet
  and the external-egress lifecycle decision remain live-cluster operator
  steps.

### Dated entries (roadmap work packages, v0.3)

- **2026-08-16 (live-cluster verification session on demo222)**: first
  real end-to-end exercise of the v0.1-v0.3 stack. Verified live: full
  ADR-0349 realm (27 users, ocp-* RBAC matrix via real Keycloak-IdP
  logins, ArgoCD role mapping), aiagent-operator reconciling Arkos+Naveo
  CRs (all 5 conditions True, owner-ref GC + selfHeal recreate),
  WP-21 two live domains with distinct credentials + hybrid search incl.
  the vector arm, first full grounded chat (5 citations, local qwen),
  Tekos gate: security 7/7 + gate-checks 1/1 PASS, scenarios 14/20 (70%).
  ~30 commits of live-found fixes - the big ones: Keycloak 25/26
  behavioral changes (varchar(255) import abort, vault-file `__`
  escaping, import-time vs runtime secret resolution, `basic` scope for
  sub, self-audience mappers, required firstName/lastName), stale
  hardcoded issuers + JWKS-over-Route TLS in all 4 services (new
  KEYCLOAK_JWKS_URL seam), served-model-name vs canonical model id split,
  PgBouncer vs search_path/prepared statements (direct-to-primary),
  pgvector text-format serialization, AsyncPostgresSaver single-connection
  wedge (pooled), fleet-wide pullPolicy Always (stale :latest cache),
  redhat-ods-applications mesh/quota recovery, acceptance-gate Job
  environment (HOME, per-agent ConfigMap projections, internal CA).
  Remaining gate failures are scenario-design/harness/credential items
  (portal Bearer-session contract, `oc` binary in harness, sales-db
  reachability-by-design, Atlassian Confluence product access for the
  token identity, BFF 55s timeout vs non-streaming completion latency),
  not platform defects. Credential-blocked: Route53 (ADR-0211 flips),
  Salesforce, Aramis, rag-S3, MaaS key. OGX corpus proof (WP-06) not yet
  attempted live.


- **2026-08-15 (ADR-0327, WP-37)**: `zuno.zuno.ai/v1alpha1 AIAgent` CRD
  reconciliation contract — first commit against a brand-new Kubebuilder
  v4 (Go + controller-runtime) scaffold in `operator/aiagent-operator/`,
  a deliberate first-of-its-kind framework dependency (contrast
  `components/agent-bff`'s stdlib-only Go, kept that way on purpose).
  Contract only, no reconciler (WP-38). `api/v1alpha1/aiagent_types.go`
  hand-authors `AIAgentSpec` as deployment bindings/references only
  (agentName, targetNamespace, okfBundleRef, frontend/bff profiles,
  entitlement+business-role group bindings, knowledgeDomains,
  toolCapabilities, modelPolicyRef, evaluationProfileRef — no secrets,
  prompts or tokens anywhere in the type) and `AIAgentStatus.conditions`
  with five required condition types
  (ConfigValid/OKFReady/FrontendReady/BFFReady/RuntimeBindingReady).
  Three `config/samples/` CRs (tekos/arkos/comage) hand-derived
  field-by-field from real chart values + OKF bundles.
  `validate_contract.py` (plain Python, no new dependency) enforces
  schema shape, secret/cross-namespace reject rules (a vanilla CRD
  structural schema only prunes unknown fields silently — it does not
  reject the create — so this is harness-enforced, not schema-inferred),
  a self-test proving the reject rules actually fire, and drift against
  real chart/OKF state; wired blocking into the repo root
  `.github/workflows/lint.yml`. `CONTRACT.md` restates the ownership
  model and migration path (Arkos is WP-38's designated first
  plain-manifest→CR migration proof; Tekos deliberately stays
  plain-manifest to prove coexistence, no flag day). ADR-0327 → fully
  Implemented, zero operator-pending items — the only WP-30–42 WP in
  this phase that closes with no live-cluster step remaining.

- **2026-08-15 (WP-38–WP-42: v0.3 repo work complete)**: the entire
  v0.1–v0.3 roadmap's repo-side work is merged. WP-38 (ADR-0308): the
  AIAgent operator controller — reconciler generating CONTRACT.md's
  per-agent resource set with owner references (delete = plain GC, no
  finalizer), in-code namespace-allowlist defense in depth, five
  status conditions, envtest suite (plain `testing`+Gomega `NewWithT`,
  NOT Ginkgo, per plan D8; envtest has no GC controller so
  cascade-delete's structural half is proven, documented honestly);
  Arkos migrated to CR-managed (its chart now renders ONE AIAgent CR;
  Tekos deliberately stays plain-manifest for coexistence); new
  `gitops/charts/aiagent-operator` (the one deliberate
  `automountServiceAccountToken: true` workload, allow-listed in
  check_workload_hardening.py) + ansible roles + Makefile/build-matrix
  entries. WP-39 (ADR-0303): per-request dynamic LoRA adapter selection —
  `policies/model-routing/model-routing-policy.yaml` (adapters: [] until
  a real GPU-trained adapter exists), `X-Zuno-Agent`+`X-Zuno-Task`
  headers threaded from both graph shapes, the C2/C3-adapter-never-
  external guard enforced INSIDE `chat_model_for()` (local-vLLM-direct
  only, not even via MaaS), `zuno.adapter` trace attribute; ai-gateway's
  build context moved to repo root to bake `policies/` in. WP-40
  (ADR-0305/0304): `evaluations/benchmark.py` (LM-Eval snapshot/oc read +
  quality-gate reuse → versioned artifact; `--check-policy` enforces
  no-artifact-no-promotion as a real CI gate) and
  `evaluations/routing_report.py` (objectives blocks in the same policy
  file; downgrade/upgrade recommendations as a report, never a policy
  write; `--metrics-file` primary per D13). WP-41 (ADR-0307/0306):
  `platform/templates/agent/scaffold_agent.py` + scaffold-validate-
  discard CI test, and **Naveo** — the sixth agent, generated by the
  real template (synthetic onboarding-assistant persona, consultant
  role, zero policy edits needed since consultant already had every
  declared capability — the cleanest composition proof; CR-managed from
  day one). Three real generator bugs found by consuming its output
  (REPO_ROOT off-by-one, hyphenated-slug identifier crash, missing
  `type: prompt` frontmatter). WP-42 (ADR-0309):
  `policies/optimization/optimization-policy.yaml` (ships
  `enabled: false`; cache_ttl range scope + routing
  pre-approved-equivalents scope, empty today) +
  `components/ai-gateway/app/optimizer.py` (D12 in-process) — runtime
  config only, code-level classification/authorization denylist,
  complete audit entries, auto-rollback triggers, one-step kill switch;
  14 tests cover every brief-named case. Remaining for the operator/user
  (cluster was down during this run; stacked for a joint session): all
  agent scenario reviews + 75% gates + active flips (ADR-0326/0306),
  operator deploy + Arkos CR verification (ADR-0308/0113), realm
  re-apply (ADR-0340), GPU pipeline run (ADR-0301/0302/0303), live
  benchmark+report loop (ADR-0304/0305), observed autonomy cycle +
  sign-off (ADR-0309 — closes the roadmap).

- **2026-08-17 (ADR-0340, WP-32)**: closed the one operator step this WP
  had left. `KeycloakRealmImport/zuno-realm` (namespace `zuno-auth`) was
  already `Done` on the live cluster — ArgoCD (`zuno-keycloak-d0`/`d1`)
  syncs directly from `origin/main`, and the realm content landed as part
  of the 2026-08-16 live-cluster verification session's broader ADR-0349
  realm apply, not a dedicated re-apply for this WP. Verified specifically
  for WP-32 via the Keycloak admin REST API (no interactive login needed):
  `/cdp` group exists; all four `confluence-archi-*` groups live under
  `/consultant`, held by `consultant-01`/`consultant-02`; `board-01`/
  `board-02` hold none of them. `cdp` has no member yet — expected, this
  WP only introduces the role, per-agent consumption is WP-33+. Repo
  acceptance re-run clean: `test_workday_ownership.py` 9/9,
  `check_docs.py` PASS. ADR-0340 → Implemented.

- **2026-08-17 (ADR-0322, WP-06)**: re-verified, made no repo or live
  changes. Repo acceptance checks re-run clean (`llamastackoperator`
  grep empty, `helm template`/`helm lint` on `openshift-ai` with
  `dataScienceCluster.enabled=true`, `pytest components/rag-service/tests/`
  54/54, `day1_check.yml --syntax-check`, `check_docs.py`). Live
  `DataScienceCluster` still shows `OGXReady: True` (2026-08-17T10:40:39Z).
  `OGXServer` remains `enabled: false` — asked the user whether to flip it
  and run the live corpus proof + provider-parity run now that cluster
  access is available; they chose to keep the prior deliberate deferral.
  ADR-0322 stays Partially implemented by choice, not by blocker.

- **2026-08-17 (ADR-0117, WP-02)**: re-verified, made no repo changes.
  Repo acceptance checks re-run clean (`py_compile`, confluence server's
  6/6 protocol tests, `check_build_matrix.py`, `check_workload_hardening.py`
  189/189, `helm lint gitops/charts/mcp-confluence`, handler-removed check,
  `check_docs.py`, atlassian-name grep in `agents/`). `confluence-mcp` is
  deployed live and Healthy in `zuno-ai-run` (ArgoCD
  `zuno-mcp-confluence-d0`/`d1`). Probed Confluence Cloud directly with the
  live `zuno/confluence/technical` credential (`cl@startx.fr`, same
  identity as env `CONFLUENCE_EMAIL`/`CONFLUENCE_API_TOKEN` in this
  session): `403 "Request rejected because caller cannot access
  Confluence"` from `startxfr.atlassian.net` - the credential resolves and
  authenticates fine, but the identity has no Confluence product-access
  grant on the Atlassian side. Same blocker the 2026-08-16 session
  recorded; confirmed still open. Needs an Atlassian admin action (grant
  Confluence product access to `cl@startx.fr`) outside this repo/session -
  nothing further to attempt here until that lands.

  Note in passing: two mcp-gateway test files
  (`test_downstream_sales_db.py`, and confluence's own
  `test_mcp_protocol.py`) are written as standalone async scripts (a
  `TESTS = [...]` list + `_run_all()`/`main()`, invoked as
  `python test_x.py`, not via pytest fixture injection) - intentional,
  mirrored from the sales-db precedent, but pytest misreads their
  `transport` parameter as a missing fixture and errors if you point
  `pytest` at them directly. Run them as scripts instead. Separately,
  `mcp-gateway/tests/test_auth_mode_enforcement.py::test_no_token_material_appears_in_the_audit_log_line`
  fails even in isolation (logging-capture issue, WP-26 territory) -
  pre-existing, unrelated to WP-32/WP-06/WP-02.

- **2026-08-17 (ADR-0204, WP-21)**: closed WP-21's own scope, made one
  real repo fix. Live-verified all four domain databases/roles exist on
  the PGO cluster (`ragtech`/`ragsales`/`ragsxalegacy`/`ragadv`, each
  ACL'd to only its own database - `\l` shows a single-role grant per
  db); `rag-service` deployed and Healthy; `tech`+`sales` schema-apply
  Jobs Complete (`sales.enabled: true` was already flipped live by a
  prior 2026-08-15 session per `gitops/charts/rag-service/values.yaml`'s
  own dated comment) - satisfies "two live domains, distinct credentials"
  today. Found `make d1 check rag` reporting "rag is NOT installed"
  despite all that: `ansible/roles/rag/tasks/precheck.yml` still looked
  up a single hardcoded `zuno-rag-schema-apply` Job, a name WP-21 itself
  retired when it switched to per-domain `zuno-rag-schema-apply-<domain>`
  Jobs (`gitops/charts/rag-service/templates/job-schema-apply.yaml`,
  the chart's only Job template) - the check had been silently broken
  since the WP that introduced the rename. Fixed: match on the
  `app.kubernetes.io/name=rag-service` label instead of a fixed name,
  require every returned Job to have succeeded. Re-ran live: now reports
  "rag is installed". ADR-0204 stays Partially implemented - WP-22
  (source adapters' live runs) is the remaining piece, out of this
  session's WP list.

- **2026-08-17 (ADR-0114, WP-03)**: re-verified, made no repo or live
  changes. Repo acceptance checks re-run clean (`py_compile`,
  `pytest components/ai-gateway/` 58/58, `helm lint`, coverage doc
  present, `check_docs.py`); `maasAdapter.enabled` correctly stays
  `false`. Live MaaS comparison remains blocked - confirmed this is
  ADR-0201's own capacity gap, not a WP-03 problem: `oc get nodes` shows
  exactly one GPU-capable node, and its one `nvidia.com/gpu` is already
  committed to the existing `qwen25-7b-instruct`/`embeddings` models
  (ADR-0201's 2026-08-16 note). The MaaS-published
  `qwen25-7b-instruct-maas-backend` LLMInferenceService (created live
  since then, part of that same in-flight rollout - `MaaSModelRef` Pending,
  two `MaaSSubscription`s exist) sits `FailedScheduling: Insufficient
  nvidia.com/gpu`. Adding GPU capacity is a real infrastructure/cost
  decision for the user, not something to do unilaterally while auditing
  a WP - left untouched. Nothing left to attempt for WP-03 itself until
  ADR-0201/WP-27 resolves that gap.

- **2026-08-17 (ADR-0308/ADR-0350, WP-38)**: closed the cluster-
  reconciliation step this WP had left, made no repo changes. Repo
  acceptance re-run clean (`go build ./...`, 13/13 envtest 86.2%
  coverage, `validate_contract.py`, `check_build_matrix.py`,
  `check_workload_hardening.py` 189/189, `helm lint`,
  `day1_check.yml --syntax-check`). Live: `aiagent-operator` deployed and
  Ready in `zuno-ai-run`; both `AIAgent` CRs (Arkos, Naveo) show all five
  status conditions `True` - confirms the reconciler, boundary
  enforcement and migration proof all work against a real cluster,
  matching the 2026-08-16 session's finding and now re-verified.
  `make d1 check agents` was also run: it's the full ADR-0053 fleet gate
  (every agent, not just this WP), and it fails overall
  (13/20 scenarios, 6/7 security checks) on the same pre-existing
  scenario-design/harness/credential gaps the 2026-08-16 note already
  recorded - not an operator or CR-reconciliation defect. ADR-0308 →
  Implemented. ADR-0350 → Implemented too, per its own "Evolution" note's
  stated trigger (moves to Implemented once ADR-0308 does) - the
  immutable Decision text itself is untouched, only the Status line and a
  new dated Evolution entry were added.

- **2026-08-17 (ADR-0349)**: closed, made no repo changes. Live-verified:
  realm re-applied (`KeycloakRealmImport/zuno-realm` `Done`, 27 users,
  fresh environment so the create-only constraint never bit);
  `ClusterRoleBinding`s correctly wired (`ocp-paas-ops`→`cluster-admin`,
  `ocp-paas-dev`→`cluster-reader`); live ArgoCD `argocd-rbac-cm` policy
  matches §5 exactly; Vault's `demo-personas-password` already holds the
  new `secretdemerde` value; no stale `admin`/`zuno-admin`/`aidev`/
  `aiops` Group objects (never logged into here); the OAuth group-sync
  mechanism itself is directly proven via `ai-ops-01`'s live
  `ocp-ai-ops` Group object. Tried to go one step further and log in
  interactively as an `ocp-paas-ops`/`ocp-paas-dev` persona to watch the
  sync happen for those specific groups too - the permission classifier
  blocked even reading current `oc` context as a first step toward a
  reversible test login, and did not attempt to route around it. Asked
  the user how to proceed; they chose to close on the indirect evidence
  above rather than push for the interactive test. Same call for the
  plus-address mail-delivery check - accepted, not independently run.
  `make check`'s fleet-wide gate still fails on the same pre-existing,
  unrelated gaps noted throughout this session (WP-38 bullet above).
  ADR-0349 → Implemented.

- **2026-08-17 (session-level note)**: this session worked WP-32 → WP-06
  → WP-02 → WP-21 → WP-03 → ADR-0350(WP-38) → ADR-0349 in that
  user-specified order, one git commit per item, plan-then-approve each
  time. Recurring shape worth remembering: every item's repo work was
  already merged going in: what remained was uniformly a live/operator
  verification step, and this session had real cluster-admin `oc` access
  plus Confluence API creds to actually attempt them (unlike most prior
  sessions, which left them "pending" for lack of access). Two real repo
  bugs were found and fixed purely as a byproduct of live-checking rather
  than being the point of the task (WP-21's stale `make d1 check rag`
  Job-name lookup; none other found). Two live blockers turned out to be
  genuine, already-documented, non-code gaps outside this session's
  power to resolve: WP-06's `OGXServer` deferral (a live-deployment
  decision the user chose to keep deferred rather than flip) and WP-03's
  MaaS GPU-capacity gap (ADR-0201, one GPU node already fully committed -
  a real infrastructure/cost decision, left alone on purpose). The
  permission classifier blocking `oc config current-context` (ADR-0349)
  is worth remembering too: login/context-switching commands get treated
  as sensitive even when read-only and reversible in intent - ask the
  user rather than probing for a workaround.
