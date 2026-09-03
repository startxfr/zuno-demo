# rag-ingestion Helm chart

Helm chart for an incremental RAG ingestion chain on Red Hat OpenShift AI 3.5:

`Red Hat docs + Confluence Cloud -> AWS S3 -> change detection -> normalization -> chunking -> embeddings -> PostgreSQL/pgvector -> validation`

## Project defaults

- OpenShift namespace: `zuno-ai-build` (both the build and the pipeline run here)
- Confluence Cloud site: `https://startxfr.atlassian.net`
- Object storage: AWS S3
- Runtime image: built by the day1-build Ansible role, published to the integrated registry

The runtime image is consumed as:

```text
image-registry.openshift-image-registry.svc:5000/zuno-ai-build/rag-ingestion:latest
```

## Build lifecycle

The image is built imperatively by Ansible via the shared
`ansible/tasks/apply_openshift_build.yml` task, same as every other
component's image here (`rag-service`, `mcp-gateway`, `agent-runtime`,
`ai-gateway`):

```text
make d1 build rag-ingestion
```

See `ansible/roles/rag_ingestion_build`. Image source is at
`components/rag-ingestion/` (Containerfile + CLI) - `gitops/charts/<name>`
holds only chart manifests, `components/<name>` holds application/image
source.

## AWS S3

`s3.type` defaults to `aws`, `pathStyle` is false, and an empty `s3.endpoint` is expanded to:

```text
https://s3.<region>.amazonaws.com
```

Set the real bucket and region in `values.yaml` or an environment-specific values file.

## Red Hat product documentation (`redhat[]`)

An array, one entry per product+version pair. Public to everyone: no
`acl_groups` is stamped on chunks from these sources. Ships with 34 entries (2 latest
versions x 17 techs: Satellite, OpenShift Container Platform, OpenShift
AI, Red Hat build of Keycloak, RHEL, Ansible Automation Platform, ACM,
ACS, Quay, OpenShift Data Foundation, Connectivity Link, Migration
Toolkit for Applications/Virtualization/Containers, OpenStack, OpenShift
Virtualization, and Identity Management). Only the Satellite 6.17/6.16
version strings are confirmed; every other entry stays marked `CONFIRM`
in `values.yaml` pending verification. Identity Management, Migration
Toolkit for Containers, and OpenShift Virtualization have no independent
versioning and are modeled as sub-entries of their parent
RHEL/OpenShift Container Platform doc chapters instead.

## Confluence Cloud (`confluence[]`)

An array, one entry per (tech x skill-tier) source, filterable by Space
(`spaces: []`) and page-tree path (`directories: []`, new). Each entry
carries `requiredGroups` - the `acl_groups` stamped onto every ingested
chunk, enforced at query time by `components/rag-service`'s
`app/search.py` (`?|` against `caller_groups`).

Ships with 12 entries, matching the 12
`confluence-{archi,build,run}-<tech>` Keycloak groups 1:1
(`gitops/charts/keycloak/files/realm-zuno.json`'s `/board`/`/consultant`
subGroups): architects get one tier across all 4 techs, consultants get
`build`/`run` tiers separately per tech. Default site
`https://startxfr.atlassian.net`; auth is materialized by External
Secrets Operator into `Secret/rag-confluence`, shared via a YAML anchor
in `values.yaml` (split per-entry if different credentials are needed).

## PostgreSQL / pgvector

A dedicated `rag-tech` database (owner role `ragtech`) on the shared
`zuno-postgresql` PGO cluster in `zuno-data` (`gitops/charts/postgresql`'s
`ragTechDatabase` block), holding a `rag` schema - not the platform's
shared `zunoapp`/`zuno` database. Vault is seeded out-of-band
(`ansible/roles/vault/tasks/install.yml`, key `rag/postgresql-app`); this
chart's `ExternalSecret` re-materializes that credential in
`zuno-ai-build`, since PGO's generated Secret lives in `zuno-data` and
`secretKeyRef` can't cross namespaces.

## Embedding model

`embedding.endpoint`/`embedding.model`/`embedding.dimensions` point at
`gitops/charts/models`' additive `embeddingModel` (KServe InferenceService
`embeddings`, `Qwen/Qwen3-Embedding-0.6B`, 1024-dim) - the same backing
service `gitops/charts/rag-service` expects by default
(`embeddings-predictor.zuno-ai-run.svc`).

## Secret contract

No sensitive value is stored in Helm. The existing `SecretStore` or `ClusterSecretStore` referenced by `externalSecrets.storeRef` must expose the configured remote keys.

| Target Secret | Default remote key | Kubernetes keys |
|---|---|---|
| `rag-s3` | `rag/s3` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| `rag-postgres` | `rag/postgresql-app` | `PGUSER`, `PGPASSWORD` |
| `rag-confluence` | `rag/confluence` | `CONFLUENCE_TOKEN`, optionally `CONFLUENCE_USERNAME` |
| `rag-embedding` | `rag/embedding` | `EMBEDDING_API_TOKEN` |
| `rag-pipeline-db` | `rag/pipeline-db` | `password` |

## Pipeline lifecycle

OpenShift AI / Kubeflow Pipelines orchestrates the chain. The chart creates one `Pipeline` CR and one config ConfigMap per `techSources` entry (18 product families + confluence, `templates/tech-source-configmaps.yaml`) and per additional domain (`templates/domain-configmaps.yaml`), each carrying an `OSS_DOCS_SOURCES_JSON`/`CONFLUENCE_SOURCES_JSON` pair (family-filtered for tech sources), plus one shared ConfigMap containing the rendered KFP source (`templates/pipeline-source-configmap.yaml`).

## Scheduling

ADR-0105 (WP-22): each domain has its own cadence - `schedule.cron` is
`knowledge.tech`'s (weekly), every `domains.<name>.schedule` block its
own (sales hours-scale, adv daily, sxa-legacy none: on-demand only). The
chart renders **one schedule ConfigMap per scheduled domain**
(`rag-ingestion-schedule-<name>`, label
`zuno.io/rag-ingestion-schedule`);
`ansible/roles/rag_ingestion/tasks/install.yml` discovers those
ConfigMaps and creates one KFP recurring run each via
`ansible.builtin.uri` calls against the DSPA's OAuth-proxied Route
(`ds-pipeline-rag-dspa`) once the pipeline is Ready, since RHOAI exposes
no native `RecurringRun` CRD. This is **best-effort and UNVERIFIED
against a live cluster**; a failure is logged but non-blocking - create
the schedule manually via the dashboard if needed. `TIMEZONE` isn't
passed to the API: this KFP version has no confirmed equivalent field.

Manual refresh (any domain, including sxa-legacy): `make d1 install
rag-ingestion` after uploading/refreshing the domain's source data - the
on-demand path ADR-0105 retains.

## Runtime image / CLI stages

The build context and CLI are at `components/rag-ingestion/`
(`src/rag_ingestion.py`). All eight stages are implemented, each
round-tripping its state through S3 rather than local disk:

```text
fetch-oss-docs    crawls each enabled redhat[] documentationUrl, discovers same-book
                  chapter links, writes raw HTML + metadata to <rawPrefix>/<doc_id>.json
                  (fetchMode: pdf not implemented - logged and skipped)
fetch-confluence  Confluence Cloud REST API v1 (wiki/rest/api/content/search, CQL by
                  space), filters by directories (ancestor-title path match) and
                  excludeLabels, tags each page's acl_groups from its confluence[] entry
detect-changes    diffs raw doc sha256 against a persisted manifest; incremental=false
                  reprocesses everything; corpus.deleteOrphans drives orphan cleanup
normalize         strips nav/script/style, preserves code blocks/tables as atomic
                  fenced/tabular text per chunking.preserveCodeBlocks/preserveTables
chunk             tiktoken (cl100k_base) token-aware splitting at chunking.maxTokens/
                  overlapTokens; whitespace fallback if tiktoken can't load;
                  code-fenced blocks are never split
embed             calls embedding.endpoint in embedding.batchSize batches, using the
                  same request/response contract as rag-service's app/embeddings.py
                  (POST {endpoint}/embeddings, {model, input: [...]})
index-pgvector    upserts into document_embeddings (source, chunk_index) - see
                  data/rag/schema/004_rag_chunking.sql - and deletes orphaned rows
validate          fails (non-zero exit) if any document this run touched has zero rows
                  or any chunk with a NULL embedding
```

Not yet exercised end to end against a live cluster or real credentials -
verified instead via `py_compile`, `helm lint`/`helm template`, and
targeted fixture tests of the pure logic (HTML normalization, chunk
splitting, manifest diffing).

## Files still requiring real environment values

Start with `examples/values-satellite.yaml` and replace:

- AWS bucket and region
- existing External Secrets `SecretStore` / `ClusterSecretStore` name and remote keys
- actual Confluence space keys and page-tree directories
- the non-Satellite `redhat[]` version/documentationUrl entries (CONFIRM against docs.redhat.com)

For production OpenShift AI Pipelines metadata, use an external MySQL/MariaDB rather than the embedded demo database.
