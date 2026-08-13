# ADR-0330: Integrate the rag-ingestion pipeline as a Day 1 component with persona-scoped Confluence access

- **Status:** Partially implemented
- **Target:** v0/v0.1
- **Date:** 2026-08-12
- **Decision owners:** Zuno Demo architecture team

## Decision

Turn the previously uncommitted, standalone `gitops/charts/rag-ingestion`
chart into a running Day 1 component (ADR-0056) that ingests Red Hat
product documentation and persona-scoped Confluence content into the
pgvector store `rag-service` already queries, reusing existing platform
conventions end to end rather than introducing new ones:

1. **Namespaces** - the BuildConfig/ImageStream and the running KFP
   pipeline both live in `zuno-ai-build`, matching every other build
   component; the original ask for a separate registry namespace in
   `zuno-ai-platform` is dropped in favor of this existing convention
   (cross-namespace ImageStream access would need new RBAC this platform
   doesn't otherwise have).
2. **Build mechanism** - the chart's own ArgoCD-managed `BuildConfig`
   template is removed. The image is built imperatively by a new day1-build
   Ansible role (`ansible/roles/rag_ingestion_build`, `make d1 build
   rag-ingestion`) via the shared `ansible/tasks/apply_openshift_build.yml`
   task, identical to `rag_build`/`mcp_build`/`agent_build`. Image source
   moves from `gitops/charts/rag-ingestion/image/` to
   `components/rag-ingestion/`, matching the `components/<name>` (source)
   vs `gitops/charts/<name>` (manifests) split every other component follows.
3. **PostgreSQL** - a new `rag-tech` database (owner role `ragtech`) is
   added to the *existing* shared `zuno-postgresql` PGO cluster
   (`gitops/charts/postgresql`'s new `ragTechDatabase` block), mirroring
   the dedicated Keycloak database pattern (ADR-0315) exactly - same
   "bring your own password" mechanism, same cross-namespace
   `ExternalSecret` re-materialization. No new PostgresCluster.
4. **Access control** - Red Hat documentation is public to everyone.
   Confluence content is ingested once per source and tagged with
   `document_embeddings.metadata.acl_groups` (ADR-0046) rather than
   ingested separately per persona; `rag-service`'s existing query-time
   `?|` group-intersection filter (`app/search.py`) enforces access with
   **no serving-side code change**. `redhat`/`confluence` become arrays
   in `values.yaml` (one product+version pair per `redhat[]` entry, one
   tech x skill-tier source per `confluence[]` entry, each filterable by
   Confluence Space and, newly, by page-tree directory).
5. **Personas** - 12 new Keycloak groups
   (`confluence-{archi,build,run}-<tech>`, tech in {satellite, openshift,
   openshift-ai, keycloak}) are added as subgroups of the existing
   `/board` (architects, one tier, all four techs) and `/consultant`
   (build and run tiers, per tech) business-role groups
   (`gitops/charts/keycloak/files/realm-zuno.json`), reusing ADR-0040's
   existing entitlement/business-role split rather than inventing a
   parallel identity model. Existing fixture users
   (`board-user-0{1,2}`, `consultant-user-0{1,2,3}`) are assigned a
   representative spread; `consultant-role-only-user-01` is deliberately
   left unchanged as the negative-access test fixture.
6. **Embedding model** - a new, additive `embeddingModel` InferenceService
   (`gitops/charts/models`, KServe/vLLM, `BAAI/bge-small-en-v1.5`,
   384-dim, named `embeddings` so KServe's `-predictor` suffix produces
   `embeddings-predictor.zuno-ai-run.svc`) closes a **pre-existing
   dangling reference**: `gitops/charts/rag-service`'s
   `embeddingServiceUrl` already hardcoded that exact hostname with no
   backing model deployed anywhere in the platform.

## Implementation status (2026-08-12)

Implemented in this change: the chart restructure above (`values.yaml`,
`values.schema.json`, `templates/`, `examples/*.yaml`, `README.md`);
`gitops/apps/rag-ingestion/{application-d0,application-d1}.yaml`
(`-d0` points at `gitops/charts/noop` - no operator of its own, the
DataSciencePipelinesApplication/Pipeline CRDs come from `openshift_ai`'s
`aipipelines` component); `ansible/roles/rag_ingestion` (day1-run) and
`ansible/roles/rag_ingestion_build` (day1-build); `Makefile`'s
`DAY1_RUN_COMPONENTS`/`DAY1_BUILD_COMPONENTS` and
`ansible/playbooks/day1_{install,check,uninstall,build}.yml`'s component
lists; the `postgresql`/`models`/`keycloak` chart additions above.

No new Day 0 component was required beyond the additive `models` chart
change: `postgresql`, `keycloak` and `openshift_ai` already existed as
Day 0 components this feature depends on.

## Follow-up implementation (2026-08-12)

The three items the first cut of this ADR deliberately left undone are
now implemented:

- **All eight ingestion CLI stages** (`components/rag-ingestion/src/
  rag_ingestion.py`) - fetch-redhat (crawls `redhat[]` doc URLs, discovers
  same-book chapter links), fetch-confluence (Confluence Cloud REST API v1
  CQL search, directory/label filtering, `acl_groups` tagging from
  `requiredGroups`), detect-changes (sha256 manifest diffing, new/changed/
  deleted/unchanged), normalize (HTML cleanup preserving code blocks/
  tables), chunk (tiktoken token-aware splitting with overlap, oversized-
  paragraph and code-block-atomicity handling), embed (batches calls
  against the exact same request/response contract as `rag-service`'s own
  `app/embeddings.py`), index-pgvector (upserts into
  `document_embeddings`), validate (fails loudly on incomplete rows).
  Every stage round-trips state through S3 rather than local disk, since
  KFP runs each stage in its own pod. Verified via `py_compile`, and
  fixture-driven tests of the pure logic (HTML normalization, chunk
  splitting including oversized-paragraph and code-block-atomicity edge
  cases, and full new/changed/deleted/unchanged manifest-diffing across
  chained detect-changes -> normalize -> chunk runs) against the real
  `boto3`/`psycopg`/`pgvector`/`tiktoken`/`beautifulsoup4` dependencies -
  **not** exercised against real Red Hat docs, Confluence, or a live
  Postgres/S3 (no network egress to those from the environment this was
  built in).
- **A schema bug found and fixed along the way**: `data/sxa/schema/
  002_pgvector.sql` sized `embedding vector(1536)` for an OpenAI-class
  model, but the model actually wired up everywhere in this repo
  (`rag-service`'s own default, and this ADR's `embeddingModel` addition)
  is 384-dimensional - every real `index-pgvector` write would have
  failed with a dimension mismatch. `data/rag/schema/004_rag_chunking.sql`
  fixes the column width, and - since it was already touching this table -
  also lands the compound `(source, chunk_index)` uniqueness
  `003_rag_metadata.sql`'s own header comment had already flagged as a
  future revisit for real chunked ingestion (replacing the source-only
  uniqueness a single-row-per-document fixture corpus didn't need).
  `data/rag/fixtures/seed.sql`'s `ON CONFLICT` target and the schema-apply
  Job/kustomization (`gitops/charts/rag-service/templates/
  job-schema-apply.yaml`, `ansible/roles/rag/kustomize/schema/`) were
  updated to match.
- **KFP recurring-run activation**, best-effort: a new task block in
  `ansible/roles/rag_ingestion/tasks/install.yml` resolves the DSPA's
  Route and the caller's OpenShift bearer token (`oc whoami -t`), then
  calls the KFP v2beta1 HTTP API (list pipelines -> list versions ->
  create recurring run) to activate `schedule.cron`. Wrapped in a
  `block`/`rescue` so a failure here is logged but never fails the rest
  of the install - genuinely **UNVERIFIED against a live cluster**: the
  Route-naming assumption, the "latest version is index 0" assumption,
  and the exact recurring-run payload shape all need confirming for real.
- **Every non-Satellite `redhat[]` version string reviewed**, expanded
  from 4 products (8 entries) to the full 17-product list the user
  requested (34 entries): OpenShift, OpenStack, Keycloak, Satellite,
  RHEL, Ansible Automation Platform, OpenShift AI, ACM, ACS, Identity
  Management, Quay, OpenShift Virtualization (replacing the now-EOL Red
  Hat Virtualization), MTV, MTA, MTC, ODF, Connectivity Link - each with
  its 2 most recent versions, or the parent product's 2 versions for the
  3 products (IdM, MTC, and effectively RHV/OpenShift Virtualization)
  that have no independent release cadence of their own. Every entry is
  WebSearch-sourced best effort, not HTTP-verified: `docs.redhat.com`
  returns HTTP 403 to this environment's fetch tooling, so individual URL
  verification wasn't possible. Every non-Satellite entry stays marked
  `CONFIRM` in `values.yaml`.

Still not done, and out of scope for this pass: real Confluence space
keys and page-tree `directories` (demo placeholders remain), and the
actual HTTP-verified confirmation of every `CONFIRM`-marked `redhat[]`
entry.

## Security considerations

Confluence ACL enforcement is entirely metadata-driven at query time
(ADR-0046's existing mechanism) - a chunk with no `acl_groups` (all
`redhat[]` sources) is visible to everyone, and a chunk with
`acl_groups` set is visible only to callers whose `caller_groups`
intersects it. This ADR does not change that enforcement point; it only
adds ingestion-side tagging and the Keycloak groups that populate it.
The `consultant-role-only-user-01` fixture (a `/consultant` member with
none of the new `confluence-*` subgroups) exists specifically to prove
the negative case: holding the parent business-role group must not
implicitly grant any tech-scoped Confluence access.

## Operational considerations

Sequencing matters: `postgresql`, `models` and `keycloak` must be
(re-)installed before `rag-ingestion` for the pipeline to have a real
database, embedding endpoint and ACL groups to use - see
`ansible/roles/rag_ingestion/README.md`'s dependency list. The `-d0`
Application being a no-op means `make d1 check rag-ingestion` will
report installed once `zuno-rag-ingestion-d1` is Synced+Healthy and
`rag-dspa`'s `DataSciencePipelinesApplication` CR reports `Ready` - the
exact status-condition shape for that CR is unverified against a live
cluster (flagged inline in `ansible/roles/rag_ingestion/tasks/install.yml`,
same caution `ansible/roles/mariadb` carries for its own CR).

## Evolution (2026-08-13)

This ADR is now the **first physical implementation of `knowledge.tech`**, not the definition of RAG architecture for every agent. ADR-0202 defines the logical domain contract; ADR-0204 generalizes the reusable ingestion/retrieval platform to `knowledge.sales`, `knowledge.adv` and `knowledge.sxa-legacy` with independent bindings, storage credentials and lifecycle.

For technical ingestion, Red Hat web documentation and Confluence must share a normalized `technology` key so they can be filtered as one technology/version corpus while preserving `source`, `source_type`, ACL and provenance. Normal technical reads should use `knowledge.tech`; direct Confluence MCP access is reserved for freshness-sensitive live reads and authorized write actions per ADR-0205.

The current demo mapping that places `confluence-archi-*` groups under `/board` is transitional. ADR-0340 reserves `board` for Direction; architecture/build/run are technical skill scopes, not executive business roles. Technical Confluence ACL groups should therefore be attached to authorized technical/CDP users without using `board` as a proxy for architect status.

See [Standard clauses](README.md#standard-clauses) for Context,
Alternatives, Consequences, Migration/evolution and Acceptance criteria.

## Related ADRs

- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md) - Use PostgreSQL and pgvector as the persistent data platform
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md) - Separate agent entitlement from business role authorization
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md) - Make RAG retrieval metadata-aware and bilingual
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md) - Discover supported operator channels and serving runtimes at deployment time
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) - Restructure deployment into Day 0 / Day 1 sequencing
- [ADR-0315](0315-dedicated-keycloak-postgresql-database.md) - Dedicated Keycloak database/role on the shared PostgreSQL cluster
- [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) - Separate the OpenShift AI control plane from AI build and run workload namespaces
- [ADR-0105](0100-v0.1-roadmap.md#adr-0105-automate-source-specific-knowledge-ingestion) - Automate source-specific knowledge ingestion
- [ADR-0202](0202-introduce-logical-knowledge-domains.md) - Introduce logical knowledge domains
- [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md) - Prefer indexed knowledge for read and live tools for freshness and write
- [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md) - Generalize the RAG platform to multiple isolated knowledge domains
- [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md) - Extend business-role authorization with CDP and scoped capabilities
