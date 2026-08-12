# ADR-0330: Integrate the rag-ingestion pipeline as a Day 1 component with persona-scoped Confluence access

- **Status:** Partially implemented
- **Target:** v0/v1
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

**Not implemented by this ADR** (deliberately, same "guarded until
values are fixed" posture the chart already documented before this
change):

- The eight ingestion CLI stage implementations
  (`components/rag-ingestion/src/rag_ingestion.py`) remain guarded -
  they need to parse the new `REDHAT_SOURCES_JSON`/
  `CONFLUENCE_SOURCES_JSON` multi-source config and stamp
  `acl_groups`/directory metadata per chunk, which is application code,
  not chart/GitOps/Ansible wiring.
- KFP recurring-run activation for `schedule.cron`: this
  RHOAI/DataSciencePipelinesApplication version exposes scheduling only
  through the KFP v2beta1 HTTP API, not a Kubernetes-native
  `RecurringRun` CRD - shipping a guessed custom-resource manifest here
  would be worse than leaving it a documented manual step (see
  `gitops/charts/rag-ingestion/README.md`'s "Scheduling" section).
- Real version strings for the non-Satellite `redhat[]` entries
  (OpenShift Container Platform, OpenShift AI, Red Hat build of
  Keycloak) are this chart's current best guess, marked `CONFIRM` in
  `values.yaml` pending verification against docs.redhat.com.
- Real Confluence space keys and page-tree `directories` (currently
  demo placeholders under a single `ARCH` space).

No new Day 0 component was required beyond the additive `models` chart
change: `postgresql`, `keycloak` and `openshift_ai` already existed as
Day 0 components this feature depends on.

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
- `0100-v1-roadmap.md#adr-0105-automate-monthly-knowledge-ingestion` - Automate monthly knowledge ingestion (the v1-roadmap entry this ADR partially advances)
