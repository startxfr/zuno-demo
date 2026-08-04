# Zuno Demo Project Memory

> This file is the repository-level working memory for the project. It records agreed project context and source-derived SXA schema knowledge. It must contain no credentials, secrets, real business records, or nominative commercial data.

## 1. Project objective

Zuno Demo is an internal MVP built on Red Hat OpenShift AI. It has three simultaneous objectives:

1. demonstrate OpenShift AI capabilities;
2. deliver five usable internal AI agents;
3. establish a reusable agentic platform and catalog for future agents.

The MVP target is seven days with two contributors. Documentation and architecture deliverables are written in English Markdown. GitHub `startxfr/zuno-demo` is the intended canonical repository.

## 2. Platform target

- OpenShift Container Platform 4.20, AWS IPI.
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

- Bootstrap: `make precheck`/`prepare`/`configure`/`install`/`check` from
  exactly one credential (OpenShift API endpoint + cluster-admin token),
  via ArgoCD + External Secrets Operator + a self-bootstrapping Vault
  (ADR-0022, ADR-0024).
- Identity: the `zuno` Keycloak realm with the 11 named personas across all
  five agents' groups (section 9's agent catalog), real Google IdP broker
  federation (section 8, ADR-0014), and the policy-intersection data files
  (`policies/tools/tool-policy.yaml`, `policies/data-classification/classification.yaml`).
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
  the validated token, never the request body (ADR-0033) -
  `evaluations/tekos/security_checks.py` covers both with security-
  negative checks kept separate from the fixed 20-scenario acceptance
  suite (ADR-0027).
- Agent surface: OKF definitions for all five agents (Tekos `active`, the
  rest `placeholder`), Tekos's frontend/BFF, and namespace-per-agent
  isolation (`gitops/charts/namespaces`) for all five even though only
  `zuno-agent-tekos` runs workloads. ADR-0031 formalizes this as the
  target shape, not an in-progress gap: Tekos is the only mandatory
  end-to-end business path for v0, and `make check` (`ansible/roles/agents`)
  structurally validates the four catalog-only agents' `agent.okf.yaml`
  files rather than leaving them unchecked.
- Evaluation: the 20 Tekos acceptance scenarios and 75%-threshold runner
  (`evaluations/tekos/`, ADR-0027/ADR-0028).
- ADR-0026 (AIAgent CRD/operator) is retargeted from v0 to v1 - Tekos
  deploys as a plain `Deployment` instead.

All four Python services (`agent-runtime`, `ai-gateway`, `mcp-gateway`,
`rag-service`) instrument themselves with OTel per
`ansible/roles/observability/README.md` - `ai-gateway` now owns the
per-provider model-call spans/token/cost metrics that used to live in
`agent-runtime`, moved there as part of implementing ADR-0009.
The cluster's real apps domain is auto-discovered from
`Ingress.config.openshift.io/cluster`, persisted to Vault
(`secret/zuno/platform/cluster-domain`), and substituted into every GitOps
`Application` that needs it - no manual edit required (see
`ansible/tasks/resolve_cluster_base_domain.yml`, `gitops/apps/README.md`).
Everything here was built and validated (Helm lint/template, YAML/JSON/Python
syntax) without a live OpenShift cluster to run it against.
