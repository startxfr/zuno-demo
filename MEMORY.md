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

### Comage

Audience: sales.

Tasks:

- identify who should be followed up;
- list current deals that have not yet received a client purchase order;
- generate weekly sales synthesis.

Follow-up priority considers deal age, quote date, last email and urgency using LLM reasoning constrained by task guidance. Comage uses sales data plus Gmail. It can write controlled sales status changes but outbound communication is never automatic from the user's mailbox. Weekly reporting can be scheduled for Sunday evening using the technical SMTP identity.

### Tekos

Audience: technical consultants.

Tekos is the first vertical slice. It validates frontend, BFF, Keycloak, runtime, AI gateway, RAG, MCP Confluence, local/external model routing, streaming and citations. The MVP uses RAG/embedding over official documentation; it does not require model fine-tuning.

### Arkos

Audience: architects.

Tasks:

- create a DAT;
- prepare an Odyssey architecture workshop.

Arkos uses the same technology RAG and MCP knowledge sources as Tekos rather than invoking Tekos as an agent in v1. Agent-to-agent communication is deferred to v2.

### Advantage

Audience: sales administration.

Tasks:

- identify new business whose client purchase order has been received during the last three rolling days;
- monthly reporting of in-progress sales.

Reporting includes sales and margin by state, customer and technology, with text/table output and PDF delivery. Advantage may perform controlled status writes.

### Finage

Audience: finance.

Tasks:

- identify business ready to invoice;
- monthly invoicing reporting.

Finage accesses business at `A facturer`/billable and later states, including invoice information. Reporting may include revenue, outstanding amounts, delay and forecast. Finage may perform controlled status writes but must not execute financial transactions.

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
As of the v0 build pass, the following is real, reviewed code rather than
planning narrative - see README.md's "v0 build status" for a summary:

- Bootstrap: `make day0|d0 check|install|configure|all` (cluster
  prerequisites) then `make day1|d1 check|build|configure|run|all`
  (build + run the platform) from exactly one credential (OpenShift API
  endpoint + cluster-admin token), via ArgoCD + External Secrets Operator
  + a self-bootstrapping Vault (ADR-0022, ADR-0024, ADR-0056).
- Identity: the `zuno` Keycloak realm with 13 anonymized synthetic personas
  (ADR-0041 - no nominative demo identity or hardcoded password in Git; the
  shared password is vault-generated at `zuno/keycloak/demo-personas`)
  across all five agents' groups (section 9's agent catalog), real Google
  IdP broker federation (section 8, ADR-0014), and the policy-intersection
  data files (`policies/tools/tool-policy.yaml`,
  `policies/data-classification/classification.yaml`).
- Data: a from-scratch PostgreSQL-native schema for section 10's SXA
  domain (`data/sxa/schema/`), synthetic fixtures, and the sales-db MCP
  server.
- AI/model layer: local Qwen2.5-7B-Instruct serving, the AI Inference
  Gateway (`components/ai-gateway`, ADR-0009) owning provider routing/
  fallback/classification-eligibility (section 6) behind an
  OpenAI-compatible API, the MCP Gateway, RAG service, and the Tekos
  LangGraph workflow (`components/agent-runtime`, now a thin
  `ai-gateway` client with no provider secret of its own).
- Identity now genuinely propagates Frontend -> BFF -> Agent Runtime ->
  AI Gateway (ADR-0032): the BFF forwards the same validated end-user
  bearer token to the Runtime (previously not forwarded at all - every
  BFF -> Runtime call was silently unauthenticated), and the Runtime
  forwards it again to `ai-gateway` instead of the `"not-required"`
  placeholder. The Runtime also now derives `user_sub` exclusively from
  the validated token, never the request body (ADR-0033).
- Data classification is now computed per turn instead of a static
  constant (ADR-0034): `effective_classification` starts at the
  technical-docs baseline (C1) and escalates to C2 the moment Confluence
  content enters context, never downgrading. Confluence is corrected from
  C1 to C2 in both policy files and gains a source-level
  `external_model_policy.allow_context: false` (ADR-0035) that forces
  local-only inference for the rest of that turn regardless of what C2's
  own SaaS-eligibility would otherwise permit - enforced via a new
  `X-Zuno-Local-Only` header the MCP Gateway's tool response, Agent
  Runtime and AI Gateway all now understand.
  `evaluations/tekos/security_checks.py` covers all four ADRs (0032-0035)
  with checks kept separate from the fixed 20-scenario acceptance suite
  (ADR-0027).
- Agent entitlement and business role are now two orthogonal Keycloak group
  dimensions (ADR-0040): `agent_<name>` groups gate frontend/BFF access to
  an agent, while `sales`/`consultant`/`adv`/`finance`/`board` (plus a
  `sales_admin` subgroup, reserved for Comage) gate tool/data permissions
  once inside. Each agent's BFF now enforces the entitlement claim
  server-side (`components/agent-bff/main.go`, 403 if missing) rather than
  relying on frontend tile visibility. `agents/*/agent.okf.md`'s
  `zuno.access.groups` was updated from the business group to the matching
  `agent_<name>` group accordingly.
- The OKF agent definition format is now real OKF v0.2 Markdown bundles
  (ADR-0038): `agents/<name>/agent.okf.yaml` (a single Kubernetes-style
  file) is replaced by `agent.okf.md` (YAML frontmatter + Markdown body)
  plus one linked Markdown document per task under `tasks/*.md` and, for
  Tekos, a system prompt under `prompts/*.md`. Agent Runtime now executes
  this contract instead of hardcoding it (ADR-0039): a new
  `app/registry.py` `AgentRegistry` resolves classification ceiling, RAG
  `top_k`, allowed tools and the system prompt from the bundle at startup,
  replacing what used to be Python constants in `app/graph/nodes.py`
  (`components/agent-runtime/tests/test_registry.py` is the acceptance
  test proving a bundle edit changes behavior with no code change). The
  MCP Gateway now enforces the full ADR-0011 five-factor intersection
  (ADR-0036): the `agent_declaration` and `task_rights` factors (via a new
  `app/agent_declarations.py`, reading the same bundles) were previously
  deferred as "no per-agent OKF tool declarations exist yet" - no longer
  true once ADR-0038 landed. Agent Runtime now declares
  `X-Zuno-Agent`/`X-Zuno-Task` on every `/v1/tools/*/invoke` call
  accordingly. Fixing this also surfaced and fixed a real, unrelated
  pre-existing bug in `components/mcp-gateway/app/policy.py`:
  `PolicyStore.reload()` iterated `tool-policy.yaml`'s raw parsed dict
  instead of its `tools:` list, so every real load of that file raised and
  every tool call failed closed.
- Agent surface: OKF definitions for all five agents (Tekos `active`, the
  rest `placeholder`), Tekos's frontend/BFF, and namespace-per-agent
  isolation (`gitops/charts/namespaces`) for all five even though only
  `zuno-agent-tekos` runs workloads. ADR-0031 formalizes this as the
  target shape, not an in-progress gap: Tekos is the only mandatory
  end-to-end business path for v0, and `make day1|d1 check agents`
  (`ansible/roles/agents`) structurally validates the four catalog-only
  agents' `agent.okf.md` bundles rather than leaving them unchecked.
- Every workload this repo directly controls now runs the OpenShift
  restricted-compatible baseline (ADR-0052): non-root, no privilege
  escalation, all Linux capabilities dropped, `seccompProfile:
  RuntimeDefault`, read-only root filesystem with an explicit `/tmp`
  `emptyDir`, no autonomously-mounted service account token, and a
  dedicated least-privilege `ServiceAccount` per workload
  (`gitops/charts/{tekos,agent-runtime,ai-gateway,mcp-gateway,
  mcp-sales-db,rag-service}`). Operator/third-party-managed workloads
  (Keycloak, KServe's vLLM container, Crunchy Postgres Operator, the upstream Vault chart) get a
  documented partial treatment instead of a guessed-at CRD/chart field -
  see ADR-0052's implementation note. `zuno-auth`/`zuno-data`/
  `zuno-telemetry` gained a namespace-level default-deny `NetworkPolicy`
  baseline (`gitops/charts/namespaces`); `zuno-ai-run` instead gets one precise
  `NetworkPolicy` per workload, because ADR-0037 requires `sales-db-mcp` to
  reject even same-namespace neighbors like `agent-runtime` - a namespace
  baseline would have silently defeated that. `sales-db-mcp` additionally
  validates a shared `X-Zuno-Gateway-Token` workload-identity secret
  (vault-generated, `zuno/mcp/gateway-workload-token`) on every
  call, independent of the network boundary. `platform/security/
  check_workload_hardening.py` statically verifies the whole baseline
  against every chart's rendered manifests (70 checks, no live cluster
  needed).
- The agent frontend is now a real PatternFly React application (ADR-0044)
  instead of hand-rolled CSS approximating it:
  `components/agent-frontend/web` (Vite + React + TypeScript, real
  `@patternfly/react-core`) builds static assets that the unchanged Go
  server resolves via a Vite manifest reader (`internal/assets`) and mounts
  into a thin per-request HTML shell, with session/tile state injected as
  JSON rather than server-templated HTML. Chat streaming now runs the full
  chain (ADR-0045): Agent Runtime's pre-existing LangGraph SSE stream is
  relayed byte-for-byte (chunked, flushed per-read, never buffered) through
  `agent-bff` and `agent-frontend` to a `fetch()`-based browser client,
  gaining a new `event: tool` status frame and an `X-Zuno-Request-Id`
  correlation header propagated across all three hops along the way.
  `evaluations/tekos/scenarios.yaml`'s pre-existing scenario 8
  (`chat_first_token_latency`, `max_seconds: 6`) already covered ADR-0045's
  required TTFT performance test.
- RAG retrieval is now metadata-aware and bilingual (ADR-0046): every
  indexed row's existing `metadata jsonb` column (already present, GIN
  indexed) carries `product`/`version`/`language`/`source_type`/
  `classification`/`acl_groups`/`last_modified`/`stale_after`/`provenance`
  (`data/rag/schema/003_rag_metadata.sql`, extending another track's
  `document_embeddings` table). Agent Runtime's `retrieve_node` now
  extracts a named product/version from the question (e.g. "OpenShift AI
  3.5") and forwards it as a deterministic pre-ranking filter rather than
  trusting similarity alone to pick the right version, forwards a soft
  French-language ranking preference, forwards the caller's groups so
  rag-service enforces ACL-restricted documents server-side (fail closed),
  and escalates `effective_classification` to the highest
  classification among retrieved docs instead of a fixed C1 baseline. A
  new fictional fixture corpus (`data/rag/fixtures/seed.sql`) includes
  deliberately conflicting per-version guidance and an EN/FR document pair
  to exercise this. This phase's sandbox turned out to have container
  registry access too, not just npm/PyPI/Go module access (Phase 6's
  finding) - a real `pgvector/pgvector:pg16` container was used to
  actually run the new schema/fixtures/queries once, which caught a
  genuine pre-existing bug unrelated to this ADR: `rag-service`'s asyncpg
  pool never decoded `jsonb` columns to Python dicts, so any real request
  against a live database would have crashed - fixed in `app/db.py`. The
  agent BFF's contract is now OpenAPI-first
  (ADR-0054): `components/agent-bff/openapi.json` (JSON, not YAML, so its
  own `contract_test.go` - this repo's first Go test suite - can parse it
  with `encoding/json` alone and keep the BFF's zero-Go-dependency
  property) covers the real `/healthz`/`/api/chat` surface including the
  SSE variant, and fails `go test` the moment the Go structs and the spec
  disagree on a field name; `platform/api/lint_openapi.py` validates the
  spec itself against the OpenAPI meta-schema plus two ADR-0054-specific
  conventions.
- Platform lifecycle and supply chain (ADR-0047/ADR-0048/ADR-0115): a new
  `ansible/roles/nfd` role closes a real, previously undeclared gap (the
  NVIDIA GPU Operator's default `ClusterPolicy` relies on NFD node
  labels, and nothing installed NFD before this). Found and fixed a real
  latent bug while implementing this: `openshift_ai`'s `DataScienceCluster`
  requested KServe Serverless mode (`kserve.serving.managementState:
  Managed` + `name: knative-serving`), which implicitly needs Service
  Mesh, Serverless and cert-manager - none of which this repository ever
  installed, so it would never have reached `Ready` on a real cluster.
  Fixed by switching to `Removed` (RawDeployment) - the correct mode for
  this demo's one always-on model, not a workaround. `ansible/roles/models`
  now discovers the vLLM serving-runtime image from OpenShift AI's own
  published `Template` catalog (`redhat-ods-applications`) instead of
  trusting the old hardcoded `quay.io/modh/vllm:rhoai-2.16-cuda` guess,
  and `openshift_ai` discovers its operator channel from the cluster's
  PackageManifest instead of a hardcoded `eus-3.5`; both fail loudly
  rather than silently guessing. Cert-manager/Service Mesh/Connectivity
  Link/LeaderWorkerSet/MaaS are deliberately *not* installed - none of
  them are applicable to this repository's actual v0 feature set (see
  `platform/openshift-ai/README.md`). This repository's first CI workflows
  now exist (`.github/workflows/{build-publish,lint}.yml`): image
  build/SBOM/scan/keyless-cosign-sign on push, and a lint gate running
  every static check built across this whole engagement. Neither has
  actually run (no live Quay credentials/Actions runner in this sandbox);
  `platform/supply-chain/check_no_latest_tags.py` correctly and honestly
  still fails (6 charts still say `tag: latest`) until a real release is
  cut - see `RELEASING.md` for that process, deliberately not fabricated
  by rewriting `targetRevision: main` to a tag that doesn't exist yet.
- Evaluation: the 20 Tekos acceptance scenarios and 75%-threshold runner
  (`evaluations/tekos/`, ADR-0027/ADR-0028), now one layer of ADR-0053's
  combined acceptance/security gate (see below).
- `make day1|d1 check agents` (ADR-0053) is the full layered gate, not a health check:
  `ansible/roles/agents/tasks/check.yml` still does the OKF-structural and
  frontend-`/healthz` smoke checks, then hands off to
  `run_acceptance_gate.yml`, which runs `evaluations/tekos/
  run_acceptance_gate.py` as a one-shot in-cluster Job in `zuno-ai-run`
  (most of what it calls - agent-runtime, mcp-gateway, ai-gateway,
  rag-service - has no Route, only in-cluster Service DNS). That script
  combines the 20 Tekos scenarios (75% threshold) with
  `security_checks.py` and the new `gate_checks.py` (both 100% mandatory)
  into one exit code and one JSON summary line. New `acceptance-gate`
  NetworkPolicy allow-list entries (`gitops/charts/{agent-runtime,
  mcp-gateway,ai-gateway,tekos}`) exist only for this narrowly-scoped
  synthetic-test identity - `sales-db-mcp` deliberately excluded, since
  its ADR-0037 bypass-denial test now depends on that exact exclusion
  (fixed a real bug where a NetworkPolicy-level deny, a connection
  timeout, would have been misreported as the check erroring rather than
  passing). Closed a real ADR-0053 gap ("missing/expired tokens"): new
  fully-offline `components/{agent-runtime,mcp-gateway}/tests/test_auth.py`
  mint their own RSA keypair and prove, by execution, that an expired or
  untrusted-key-signed JWT is rejected - no live Keycloak needed, now in
  CI. Surfaced but deliberately did not fix (out of this ADR's scope, and
  already-"Implemented" elsewhere): `keycloak.<domain>` is the Keycloak
  CR's real hostname, while the tekos frontend's OIDC issuer URL and every
  eval script's `KEYCLOAK_URL` default assume `sso.<domain>`, which no
  Route in this repository creates - a real bug in ADR-0032/0033's
  identity plumbing, flagged in ADR-0053's Implementation state.
- ADR-0113 (AIAgent CRD/operator) is retargeted from v0 to v1 - Tekos
  deploys as a plain `Deployment` instead.
- Deployment sequencing (ADR-0056): the old `precheck`/`prepare`/
  `configure`/`install`/`check` interface is replaced outright by
  `make day0|d0 <check|install|configure|all> [component]` (cluster
  prerequisites) and `make day1|d1 <check|build|configure|run|all>
  [component]` (build + run the platform). New Day 0 components:
  `admin_context` (PriorityClasses, StorageClass existence check,
  ArgoCD ClusterRoleBinding consolidation) and `namespaces` (moved out of
  `agents`, now its own explicit checkable step). `datascience` is merged
  into `openshift_ai` (one role, one conceptual prerequisite); the
  formerly separate `api` role is retired into `agents` (once namespace-
  apply moved out, they did the same thing). `day1_check.yml` special-cases
  `agents` to run the ADR-0053 acceptance gate (what bare `make check` used
  to run) rather than a dependency precheck, so that capability wasn't lost.
  `zuno-ai` is split into `zuno-ai-run` (workloads) and `zuno-ai-build`
  (new: in-cluster image builds via native OpenShift `BuildConfig`/
  `ImageStream`, no new operator - `ansible/roles/{mcp,rag,agent}_build`,
  covering 6 of the 8 CI-matrix images; `ai-gateway` and the pgvector base
  image aren't covered yet, flagged as a follow-up) - a 59-file rename
  landed as its own isolated commit. `zuno-ai-build` gets a default-deny-
  all-ingress baseline (nothing needs inbound access to a build namespace)
  and grants exactly the three consuming namespaces (`zuno-ai-run`,
  `zuno-data`, `zuno-agent-tekos`) scoped `system:image-puller` access,
  created at build time rather than by the Day 0 `namespaces` role to
  avoid a Day0-depends-on-Day1 ordering problem. `make day1|d1 all
  <component>` runs only the check/build/configure stages that actually
  apply to that component, since build components (`mcp, rag, agent`) and
  run components (`llm, models, sql_schema, rag, mcp, agents, mlops`) are
  different, overlapping-but-not-identical sets - most visibly, "agent"
  builds and "agents" runs, a real distinct pair, not a typo.

All four Python services (`agent-runtime`, `ai-gateway`, `mcp-gateway`,
`rag-service`) instrument themselves with OTel per
`ansible/roles/observability/README.md` - `ai-gateway` now owns the
per-provider model-call spans/token/cost metrics that used to live in
`agent-runtime`, moved there as part of implementing ADR-0009.
The cluster's real apps domain is auto-discovered from
`Ingress.config.openshift.io/cluster`, persisted to Vault
(`zuno/platform/cluster-domain`), and substituted into every GitOps
`Application` that needs it - no manual edit required (see
`ansible/tasks/resolve_cluster_base_domain.yml`, `gitops/apps/README.md`).
Everything here was built and validated (Helm lint/template, YAML/JSON/Python
syntax) without a live OpenShift cluster to run it against.

The `sso.<domain>` vs `keycloak.<domain>` mismatch flagged in ADR-0053's
Implementation state (surfaced but deliberately not fixed there) is now
fixed: `tekos.keycloakIssuerUrl`, `agent-frontend`/`agent-bff`'s
`KeycloakIssuerURL` doc comments, and both `evaluations/tekos` scripts'
`KEYCLOAK_URL` defaults all converge on `keycloak.<clusterBaseDomain>`,
matching the Keycloak CR's real Route hostname and
`run_acceptance_gate.yml`'s already-correct value. Separately, the Keycloak
CR (`gitops/charts/keycloak/templates/keycloak.yaml`) now sets
`spec.hostname.strict: true` and `KC_PROXY_HEADERS=xforwarded` explicitly
(previously relied on unverified operator defaults for an edge-terminated
Route) - addresses the admin console's "Timeout when waiting for 3rd party
check iframe message" error, which is caused by Keycloak computing its own
origin as `http://` while the browser's real origin is `https://` behind
the edge-terminated Route. Also, `spec.db` is no longer omitted: Keycloak
now gets its own dedicated `keycloak`/`keycloak` Postgres database/role on
the shared `zuno-postgresql` cluster (not the shared `zunoapp`/`zuno`
app-data database - least-privilege/lifecycle isolation), wired the same
"own ExternalSecret + secretKeyRef" cross-namespace way as `mcp-sales-db`.
Neither the hostname/proxy nor the Postgres wiring has been exercised
against a live cluster - see `ansible/roles/keycloak/README.md`'s "What's
unverified against a real cluster" section.

ADR-0328 (`zuno-ai-platform`, To be implemented) and ADR-0329 (agent
namespace consolidation, Implemented) landed together on 2026-08-12.
`gitops/charts/namespaces` gained a `zuno-ai-platform` platformNamespaces
entry (same shape as `zuno-ai-run`, plus
`opendatahub.io/application-namespace: "true"`) - the future OpenShift AI
applications namespace ADR-0328 targets; wiring `DSCInitialization` and
the DataScienceCluster components to it is deliberately out of scope for
now (`gitops/charts/openshift-ai` still targets `zuno-ai-build`, unchanged).
Separately, ADR-0329 supersedes ADR-0023: the per-agent
`zuno-agent-<name>` namespace model is retired, since real isolation
between agents was already carried by precise per-workload NetworkPolicies
(ADR-0037), not the namespace boundary. `gitops/charts/namespaces` no
longer creates or quotas any `zuno-agent-*` namespace (`namespaces:` key
and its `quota.yaml`/`networkpolicy.yaml` templates removed);
`gitops/charts/tekos` now deploys into `zuno-ai-run` alongside Agent
Runtime/AI Gateway/MCP Gateway. The NetworkPolicies that used to cross the
`zuno-agent-tekos`/`zuno-ai-run` boundary (`agent-runtime`, `tekos`,
`redis` charts) became same-namespace `podSelector` rules or now target
`zuno-ai-run` by name instead of the old generic `zuno.io/agent` namespace
label match. Every other `zuno-agent-tekos` reference (Day 1 build
image-puller RoleBinding, Keycloak realm `agent.namespace` client
attributes, `agent-frontend`'s `BFF_BASE_URL`/OpenAPI default, the Tekos
acceptance-gate scenario, architecture docs) was updated to `zuno-ai-run`
to match. Placeholder agents (Comage, Advantage, Finage, Arkos) now carry
no namespace footprint at all - only their `agent.okf.md` bundle exists
until a future FE/BFF chart deploys for them into `zuno-ai-run`.

- 2026-08-14 (ADR-0116, roadmap WP-01): the MCP Gateway now routes through
  the platform backend-binding registry
  (`platform/bindings/tools/tool-bindings.yaml`, loaded by
  `components/mcp-gateway/app/bindings.py`) instead of hard-coded tool-name
  sets in `app/downstream.py`. Canonical `<domain>.<resource>.<verb>`
  capability IDs are the stable contract (legacy names like
  `search_confluence`/`get_customer` remain explicit aliases;
  `policies/tools/tool-policy.yaml` entries carry both via the new
  `capability` field and answer to either). Unknown names/missing bindings
  fail closed before any backend contact; startup + `/readyz` validate that
  every policy-listed name resolves to exactly one binding; traces/metrics
  record `zuno.capability` and `zuno.binding`. The registry ships in the
  gateway image (repo-root build context) and reloads via
  `/admin/reload-policy`. Tests: `components/mcp-gateway/tests/
  test_bindings.py` plus the migrated streamable-HTTP transport test.

- 2026-08-14 (ADR-0114, roadmap WP-03): `components/ai-gateway` gained a
  MaaS adapter prototype (`app/maas_adapter.py`) behind the existing
  OpenAI-compatible `ChatOpenAI` client, per ADR-0114's "prototype before
  removing current gateway capabilities" requirement. Additive and
  two-gated: a provider only routes through it when its
  `platform/ai-gateway/provider-routing.yaml` entry sets `via_maas: true`
  AND the chart's `maasAdapter.enabled` is true (default false, no shipped
  provider opts in). Classification eligibility (`app/routing.py`) is
  evaluated identically either way and always runs first - the adapter
  changes transport, never eligibility (proven by a security-negative test
  in `components/ai-gateway/tests/test_maas_adapter.py`). Feature-coverage
  comparison tracked in `docs/roadmap/evidence/adr-0114-maas-coverage.md`;
  live MaaS verification and any cutover decision remain an operator step
  (WP-27).

- 2026-08-14 (ADR-0115 stage 1, roadmap WP-04): added the two remaining
  supply-chain tools needed once a real release exists.
  `platform/supply-chain/verify_signatures.py` runs `cosign verify`
  against every immutable-tagged first-party image reference
  (`quay.io/zuno-demo/...`), checking the exact `build-publish.yml`
  keyless GitHub OIDC identity signed it - currently finds nothing to
  verify (every chart is still `tag: latest`) and passes trivially, by
  design. `platform/supply-chain/pin_release.py` mechanically rewrites
  chart `tag` fields from an operator-authored release manifest
  (text-level edits, so existing `values.yaml` comments survive; refuses
  to run unless the manifest covers exactly the current
  `check_no_latest_tags.py` gap set), with a regression suite
  (`tests/test_pin_release.py`) exercised against a throwaway copy of the
  real chart files. Both are wired into `.github/workflows/lint.yml`
  `continue-on-error: true`, same convention as `check_no_latest_tags.py`.
  `RELEASING.md` documents the exact stage 4/5 sequence using these
  tools. Neither closes any ADR-0115 gap by itself - all remaining gaps
  (2, 3, 4, 6) still block on gap 7, the real credentialed release run.

- 2026-08-14 (ADR-0117, roadmap WP-02): built Zuno's first real external
  MCP integration. `components/mcp-servers/confluence/` is a real MCP
  server (same shape as sales-db: official `mcp` SDK, streamable-HTTP,
  mounted at `/mcp`) implementing the four ADR-0116 capabilities
  (`confluence.page.search/read/create/update`) against the real
  Confluence Cloud REST API - HTTP Basic Auth (email + API token from
  `zuno/confluence/technical`), `service-identity` mode (ADR-0208).
  `platform/bindings/tools/tool-bindings.yaml` now routes all four
  capabilities to it (streamable-http, `endpoint.default:
  http://confluence-mcp.zuno-ai-run.svc:8000`); the demo-mode
  `components/mcp-gateway/app/handlers/confluence.py` handler is deleted.
  New chart `gitops/charts/mcp-confluence/` (mirrors mcp-sales-db) and
  `gitops/apps/mcp-confluence/`, applied by `ansible/roles/mcp` alongside
  the gateway itself (name-mismatch pattern, like `sql_schema` does for
  mcp-sales-db); image builds via `ansible/roles/mcp_build` and
  `.github/workflows/build-publish.yml`'s matrix. `policies/tools/
  tool-policy.yaml` gained three new entries (read/create/update, C2,
  consultant+board, `allow_context: false`) alongside the existing
  `search_confluence` entry. Protocol-tested against a mocked Confluence
  API (`components/mcp-servers/confluence/tests/test_mcp_protocol.py`);
  real end-to-end verification against a live Confluence Cloud tenant
  remains an operator step (WP-02), and ADR-0043's status-line update
  ("confluence... migrated") is deferred until then.

- 2026-08-14 (ADR-0106, roadmap WP-05): OKF agent bundles (`agents/<name>/`)
  now have a full signing/validation pipeline. `platform/supply-chain/
  sign_okf_bundle.py` computes a deterministic sha256 digest over a bundle
  tree (sorted relative-path:content-hash pairs) and signs/verifies it
  with keyless `cosign sign-blob`/`verify-blob` (same GitHub OIDC identity
  as ADR-0115's image signing), wired as a new `sign-okf-bundles` job in
  `build-publish.yml` (one signature per agent, uploaded as a build
  artifact - never committed to git). `platform/supply-chain/
  validate_okf_bundle.py` checks schema (OKF structure) and policy
  validity (every declared tool resolves against `tool-policy.yaml`,
  feature-detecting a future `knowledge-policy.yaml`) with no signature
  needed - wired into `lint.yml` as a hard gate and into `ansible/roles/
  agents`' Day 1 check. `components/agent-runtime/app/registry.py` gained
  `ZUNO_REQUIRE_SIGNED_BUNDLES` (default false) - when enabled, refuses
  any bundle without a verified signature and refuses to even start if no
  `cosign` binary is present; imports `sign_okf_bundle.py`'s digest/verify
  logic directly (baked into the image at `app/_sign_okf_bundle.py` by the
  Dockerfile, which now also installs `cosign`) rather than duplicating
  it. No bundle has a real signature yet (needs WP-04 stage 2's
  credentialed CI run), so ADR-0106 stays Partially implemented and the
  flag stays off.

- 2026-08-14 (ADR-0103, roadmap WP-08): Agent Runtime workflows are now
  resumable. `app/graph/build.py`'s `build_graph()` takes an explicit
  checkpointer (LangGraph's `BaseCheckpointSaver`) instead of compiling
  once at import time; `app/main.py`'s new ASGI lifespan builds the graph
  at startup against `AsyncPostgresSaver` when `CHECKPOINT_PGHOST/PORT/
  DATABASE/USER/PASSWORD` are all set, else falls back to `MemorySaver`
  (default, not resumable across restarts - the documented default for
  tests/local dev). `POST /v1/agents/tekos/chat` gained an optional
  `run_id` request field / mandatory `run_id` response field
  (`app/schemas.py`); `_resolve_run_id` mints a fresh run_id when absent,
  and on resume re-fetches the checkpoint's stored `user_sub` and refuses
  (403) if it differs from the validated caller's own token subject -
  ADR-0103's "resumption re-enforces authorization" requirement - and 404s
  an unknown/expired run_id. Dedicated `agent-checkpoints` database/role on
  the shared `zuno-postgresql` PGO cluster
  (`gitops/charts/postgresql`'s `checkpointDatabase`, confirmed the
  hyphenated-name pattern already works against the real cluster
  alongside `rag-tech`), seeded via `ansible/roles/vault`'s existing
  self-generated-credentials block (`agent-runtime/postgresql-app`).
  Pinned `langgraph-checkpoint-postgres==2.0.25` (the last release
  compatible with the already-pinned `langgraph==0.2.39`'s
  `langgraph-checkpoint<3.0.0` constraint - a newer
  langgraph-checkpoint-postgres pulls in langgraph-checkpoint>=4.0.0 and
  conflicts). Tested against `MemorySaver` (same `BaseCheckpointSaver`
  interface as `AsyncPostgresSaver`, so the real production logic is
  proven without needing a live Postgres) in
  `components/agent-runtime/tests/test_checkpointing.py`, including the
  cross-subject-resume security-negative. Repo-provable end to end, so
  ADR-0103 is fully Implemented (no operator step required).

- 2026-08-14 (ADR-0104, roadmap WP-09): AI Gateway gained an opt-in
  semantic cache for non-streaming `/v1/chat/completions` responses
  (`components/ai-gateway/app/semantic_cache.py`), stored in the existing
  platform Redis (same instance agent-frontend already uses for sessions -
  its NetworkPolicy was extended to also allow `app.kubernetes.io/name:
  ai-gateway` pods, a real gap the initial implementation would otherwise
  have hit silently). Two-gate enablement (chart `semanticCache.enabled`
  AND a model's `cache_enabled: true` in provider-routing.yaml), same
  pattern as ADR-0114's MaaS adapter. "Semantic" means the prompt is
  embedded via the same shared embedding InferenceService
  `components/rag-service` uses and bucketed with fixed-seed SimHash
  (locality-sensitive hashing) rather than exact-text matching. The cache
  key binds to model identity, caller subject, effective classification,
  local-only requirement and task identity - any one differing is a
  guaranteed miss, proven by dedicated tests
  (`components/ai-gateway/tests/test_semantic_cache.py`,
  `test_cache_integration.py`). Cache infrastructure failures (Redis or
  the embedding service unreachable) fail open - proceed uncached - since
  caching is a performance optimization, never a security control; the
  classification/eligibility check in `app/routing.py` always runs first,
  structurally guaranteeing a policy denial never reaches the cache.
  Streaming responses are not cached (first-version scope). Repo-provable
  end to end, so ADR-0104 is fully Implemented with no operator step
  required.

- 2026-08-14 (ADR-0111, roadmap WP-11): first SecNumCloud hardening
  increment. `docs/security/secnumcloud-controls.md` is the new control
  matrix (deployment/supply-chain/identity/network/data families, each row
  `enforced-in-ci`/`enforced-on-cluster`/`gap` with the exact enforcing
  file cited) - derived documentation, `platform/security/
  check_workload_hardening.py` remains authoritative.
  `check_workload_hardening.py` itself gained two things: (1) a real BUG
  FIX - `_helm_template()` never passed `--set` overrides, so
  `check_networkpolicies("namespaces", ...)` and `check_keycloak_partial()`
  were silently checking an always-empty render (both charts gate their
  real content behind `enabled: false` defaults); now passes
  `policy.enabled=true`/`keycloak.enabled=true` and both checks
  meaningfully pass. (2) `check_no_hardcoded_secret_values` - a new,
  first-ever automated check that no chart embeds a literal secret value
  (as opposed to `secretKeyRef`) in a rendered manifest (ADR-0024/0041).
  Also added the missing `mcp-confluence` chart (ADR-0117) to both check
  lists - it was never covered.
  **Real security gap found and closed**: `gitops/charts/namespaces`'s
  `zuno-ai-run` entry was silently included in the `platformNamespaces`
  loop that generates an all-ports, same-namespace-allowed NetworkPolicy -
  directly contradicting this same file's own comment and ADR-0037/0052's
  explicit design ("zuno-ai-run must not get a namespace-wide baseline - it
  would defeat mcp-sales-db's own precise, port-8000-only NetworkPolicy",
  since Kubernetes NetworkPolicies are additive). Fixed via a new
  `skipNetworkPolicy: true` flag on that entry, guarded in
  `templates/networkpolicy-platform.yaml` - confirmed via `helm template`
  before/after that only the NetworkPolicy is skipped, not the
  Namespace/ResourceQuota/LimitRange objects the same entry also drives.
  Confirmed against the real cluster this was never actually deployed
  (`policy.enabled` is currently false there; `oc get networkpolicy -n
  zuno-ai-run` returns nothing) - the fix is preventative, not an active
  incident. `check_workload_hardening.py` now passes 95/95 (was silently
  "64/66... 2 failures" before the `_helm_template` fix, both false
  failures on always-empty renders).
  ADR-0111 stays Partially implemented: this WP's own first-increment
  scope is fully closed, but the matrix still tracks `gap` rows owned by
  WP-12 (HA/PDB), WP-13 (backup) and WP-26 (binding auth-mode
  enforcement), plus several live-cluster-only verification items.

- 2026-08-14 (ADR-0322, roadmap WP-06): OGX migration + RAG provider
  parity, Parts A and B. **Part A** turned out to be mostly already done:
  `gitops/charts/openshift-ai/values.yaml`'s `dataScienceCluster.spec`
  already had `ogx.managementState: Managed` and the deprecated Llama
  Stack component already set to `Removed` (commit `cb827edd`, ADR-0343's
  RHOAI 3.5 EA2 pin work, predating ADR-0322's own authoring by a day) -
  confirmed live via `oc get datasciencecluster zuno-dsc`: `status.
  conditions` already carries `type: OGXReady, status: "True"`. Closed the
  gap between "Removed" and the ADR's literal "absent from the rendered
  DataScienceCluster" by deleting the key entirely (not just its value) -
  residual risk (whether the operator treats an omitted managementState
  identically to explicit Removed) is flagged as an operator verification
  step, not assumed. `ansible/roles/openshift_ai/tasks/precheck.yml`'s Day
  1 OGX check was upgraded from diagnostic-only to a real readiness gate
  on the `OGXReady` condition - the CRD-schema gap that check's own
  comment had flagged as blocking this (`status.components.ogx` not
  existing yet) closed between when that comment was written and now, per
  `oc explain`. Corrected two stale docs describing OGX as an informal
  capability grouping rather than the discrete `DataScienceCluster`
  component: `docs/architecture/physical-architecture.md` (was citing
  ADR-0328's `zuno-ai-platform` placement, superseded by ADR-0331 - RHOAI
  operands actually live in `redhat-ods-applications`/
  `rhoai-model-registries`) and `components/rag-service/app/{config,
  embeddings}.py`'s docstrings (were crediting ADR-0018 for the embedding
  backend, which ADR-0322 supersedes for OGX specifically).
  **Part B** added `components/rag-service/app/ogx_provider.py`, an
  OGX-backed retrieval provider prototype behind the exact same
  `(query, top_k, product, version, language, caller_groups) ->
  {results, vector_search_used}` contract `app/search.py:hybrid_search`
  already implements - same additive/opt-in shape as `ai-gateway`'s MaaS
  adapter (WP-03): `RAG_PROVIDER=ogx` (default `pgvector`, unaffected)
  gates it, chart value `ogxProvider.enabled`. Verified via `oc explain`
  that `spec.components.ogx: Managed` on this cluster only installs the
  OGX Operator/controller - the actual data-plane API is a separate
  namespaced `OGXServer` CR (`ogxservers.ogx.io/v1beta1`) nothing has
  created yet, so this adapter has never run against a live OGX endpoint.
  Added a schema-correct (via `oc explain ogxserver.spec...`, every field
  checked) but not-yet-applied `OGXServer` manifest at `gitops/charts/
  openshift-ai/templates/ogxserver.yaml` (disabled by default) wired to
  this repo's existing PostgreSQL/pgvector (`remote::pgvector` provider, a
  new dedicated `ogx`/`ogxserver` database via the same Vault/PGO
  "bring-your-own-password" pattern WP-08's checkpoint database used) and
  existing KServe/vLLM (`remote::vllm` provider, `distribution.name:
  remote-vllm`) rather than inventing new infrastructure. Because OGX's
  own metadata-filter wire format isn't verified against a live endpoint,
  the adapter deliberately does NOT push product/version/ACL filters down
  to OGX - it over-fetches and re-applies the identical fail-closed
  filter semantics `app/search.py:_filter_clause` enforces in SQL, in
  Python, as defense in depth (same posture ADR-0322 requires of OGX's
  own ABAC relative to Zuno's authorization boundary). `tests/
  test_provider_parity.py` proves both providers' row-mapping functions
  agree on classification/language/product/version/staleness/citation
  fields for the same logical document, and that each provider's response
  validates against the same `SearchResponse` schema - real
  retrieval-quality parity against a shared indexed corpus needs a live
  OGXServer, so it's an operator follow-up, not proven here.
  ADR-0322 stays Partially implemented: DSC migration/health-check/docs
  (Part A) and the provider/parity-test scaffolding (Part B) are repo-done,
  but live DSC reconciliation with the key removed and an actual
  OGX-backed corpus proof both need cluster access this session doesn't
  have.

- 2026-08-14 (ADR-0330, roadmap WP-07): rag-ingestion catalog completion -
  the repo-side prep ADR-0330 left open. New
  `components/rag-ingestion/tooling/verify_catalog.py` HTTP-verifies every
  `redhat[]` entry's `documentationUrl` (HEAD, falling back to GET on
  405/501) and reports `OK`/`REDIRECT(final-url)`/`FAIL` - meant to run
  from a network that can reach `docs.redhat.com` (still HTTP 403 here).
  Its own tests (`tooling/tests/test_verify_catalog.py`, 9 cases) are
  rag-ingestion's first committed test file - the ADR's earlier claim of
  "fixture-driven tests" was ad hoc/uncommitted, so `python3 -m pytest
  components/rag-ingestion/ -q` (the WP-07 brief's own acceptance check)
  previously exited 5 ("no tests collected") regardless of correctness;
  it now actually exercises something. Marked all 32 non-Satellite
  `redhat[]` entries with an explicit trailing `# CONFIRM` comment (a
  small script-driven text edit, one per entry's `documentationUrl` line,
  verified 1:1 against the parsed YAML count before writing) so a
  follow-up mechanical pass can find and drop them per the ADR's own
  "drop CONFIRM markers on OK" instruction - previously only one MTC
  entry had the word "CONFIRM" anywhere in the file. Confluence
  `spaces:`/`directories:` demo placeholders now carry an explicit
  `# operator-supplied: replace demo placeholders` marker in both
  `values.yaml` and `values.schema.json`'s new `description` fields - no
  real Confluence space key exists anywhere in this repo, none invented.
  `ansible/roles/rag_ingestion/tasks/install.yml`'s KFP recurring-run
  `rescue:` block previously gave one generic failure message; now
  enumerates its three UNVERIFIED assumptions (Route naming, "version
  index 0 is newest", recurring-run payload field names) individually
  and greppably (`WP-07-UNVERIFIED-ASSUMPTION`) so a real cluster run's
  log names exactly which one to check - caught and fixed a real dead-code
  bug in `verify_catalog.py` along the way (a trailing fallback return
  after the HEAD/GET loop that could never execute, since GET's own
  result always returns directly). ADR-0330 stays Partially implemented -
  live HTTP verification, real Confluence credentials, and the KFP/DSPA
  assumption checks all still need operator/cluster access this session
  doesn't have.

- 2026-08-14 (ADR-0107 + ADR-0108, roadmap WP-10): promoted both stubs to
  full records and built the model/agent promotion quality gate.
  `evaluations/quality_gate.py` invokes an agent's existing
  `evaluations/<agent>/run_acceptance_gate.py` as a subprocess (its own
  directory-relative-import requirement) and parses the JSON summary it
  already prints, but re-derives the PASS/FAIL decision itself using a
  threshold read from a new `evaluations/<agent>/gate_config.yaml`
  (seeded for tekos at 0.75) instead of trusting that script's own
  hardcoded `SCENARIO_THRESHOLD` constant - closes ADR-0107's literal
  "thresholds are data, not code" requirement without touching
  `run_acceptance_gate.py` (still `make check`'s own unrelated ADR-0053
  entrypoint). security_checks/gate_checks stay 100% mandatory regardless
  of the configured threshold - proven by a test where a perfect scenario
  rate still fails the gate on a security regression. An agent with no
  `gate_config.yaml` fails closed. Added a `quality-gate` job to
  `lint.yml` with a hand-rolled `git diff`-based path filter (no new
  third-party Action) that only smoke-checks agents whose
  `evaluations/<agent>/` directory changed - deliberately does NOT claim
  a real PASS/FAIL verdict from a GitHub-hosted runner, since
  `run_scenarios.py`/`security_checks.py` need a live cluster this
  workflow file's own top comment says it never has; it blocks only on
  exit code 2 (a genuine wiring/config defect), not on exit 1 (a correct
  "can't reach a cluster from here" result) - the real verdict is the
  operator follow-up below.
  For ADR-0108: confirmed via `oc explain lmevaljob.spec...` against the
  live test cluster that `LMEvalJob` (`trustyai.opendatahub.io/v1alpha1`)
  is real and that the DSC's `trustyai` component (which provides it) is
  already `managementState: Managed` with `eval.lmeval` configured - no
  DSC change needed, only the missing job *instances*. Added
  `gitops/charts/openshift-ai/templates/lmevaljob.yaml`, one CR per
  `lmEval.jobs[]` values entry, disabled by default with an empty job
  list (opt-in per candidate model, per ADR-0108's "complements - never
  replaces" framing). `ansible/roles/models/tasks/precheck.yml` now
  reports any LMEvalJob's `status.state`/`results` via `make d1 check
  models`, diagnostic only - never gates the models component's own
  install-state, since these are one-shot benchmarking runs, not a
  component this role owns the lifecycle of. Both ADRs stay Partially
  implemented: a real GPU cluster LM-Eval run and one exercised
  blocked/passing promotion both need cluster access this session
  doesn't have.
