# rag-ingestion Helm chart

Helm chart for an incremental RAG ingestion chain on Red Hat OpenShift AI 3.5:

`Red Hat docs + Confluence Cloud -> AWS S3 -> change detection -> normalization -> chunking -> embeddings -> PostgreSQL/pgvector -> validation`

## Project defaults

- OpenShift namespace: `zuno-ai-build` (both the build and the pipeline run here - see ADR below)
- Confluence Cloud site: `https://startxfr.atlassian.net`
- Object storage: AWS S3
- Runtime image: built by the day1-build Ansible role, published to the integrated registry

The runtime image is consumed as:

```text
image-registry.openshift-image-registry.svc:5000/zuno-ai-build/rag-ingestion:latest
```

## Build lifecycle

Unlike an earlier revision of this chart, the image is **not** built by an
ArgoCD-managed `BuildConfig` template here - every other component's image
in this repository (`rag-service`, `mcp-gateway`, `agent-runtime`,
`ai-gateway`) is built imperatively by Ansible via the shared
`ansible/tasks/apply_openshift_build.yml` task, and rag-ingestion now
follows the same convention for consistency:

```text
make d1 build rag-ingestion
```

See `ansible/roles/rag_ingestion_build`. Image source lives at
`components/rag-ingestion/` (Containerfile + CLI), not under this chart -
`gitops/charts/<name>` holds only chart manifests, `components/<name>`
holds application/image source, matching every other component.

## AWS S3

`s3.type` defaults to `aws`, `pathStyle` is false, and an empty `s3.endpoint` is expanded to:

```text
https://s3.<region>.amazonaws.com
```

Set the real bucket and region in `values.yaml` or an environment-specific values file.

## Red Hat product documentation (`redhat[]`)

An array, one entry per product+version pair - not a single product with a
`versions:` list, so each version can carry its own `documentationUrl`/
`include`/`exclude` independently. Public to everyone: no `acl_groups` is
ever stamped on chunks from these sources. Ships with 34 entries (2 latest
versions x 17 techs: Satellite, OpenShift Container Platform, OpenShift
AI, Red Hat build of Keycloak, RHEL, Ansible Automation Platform, ACM,
ACS, Quay, OpenShift Data Foundation, Connectivity Link, Migration
Toolkit for Applications/Virtualization/Containers, OpenStack, OpenShift
Virtualization, and Identity Management) - only the Satellite 6.17/6.16
version strings are confirmed; every other entry is WebSearch-sourced
best effort (`docs.redhat.com` returns HTTP 403 to this environment's
fetch tooling, so individual URL verification wasn't possible) and stays
marked `CONFIRM` in `values.yaml` pending verification against
docs.redhat.com before the first real run. Three products have no
independent version numbering of their own and are modeled as sub-entries
of their parent product instead of invented version numbers: Identity
Management (a RHEL doc chapter), Migration Toolkit for Containers (an
OpenShift Container Platform doc chapter), and OpenShift Virtualization
(also an OpenShift Container Platform doc chapter, standing in for the
now-EOL Red Hat Virtualization, which only ever had one release).

## Confluence Cloud (`confluence[]`)

An array, one entry per (tech x skill-tier) source, filterable by Space
(`spaces: []`) and by page-tree path (`directories: []`, new). Each entry
carries `requiredGroups`: the `acl_groups` values stamped onto every
chunk ingested from it. `components/rag-service`'s existing query-time
filtering (`app/search.py`'s `?|` intersection against `caller_groups`,
ADR-0046) enforces access - no serving-side changes were needed.

Ships with 12 entries, matching the 12
`confluence-{archi,build,run}-<tech>` Keycloak groups 1:1
(`gitops/charts/keycloak/files/realm-zuno.json`'s `/board` and
`/consultant` subGroups): architects (`archi`) get one tier across all 4
techs, consultants get `build` and `run` tiers separately per tech.

The default site is `https://startxfr.atlassian.net`. Authentication
stays outside the chart and is materialized by External Secrets Operator
into `Secret/rag-confluence` - every entry shares the same credential via
a YAML anchor in `values.yaml` (one Atlassian site, one token for this
demo); split it per-entry if a real environment ever needs different
credentials per source.

## PostgreSQL / pgvector

A dedicated `rag-tech` database (owner role `ragtech`) on the shared
`zuno-postgresql` PGO cluster in `zuno-data`
(`gitops/charts/postgresql`'s `ragTechDatabase` block), holding a `rag`
schema - not the platform's shared `zunoapp`/`zuno` database. Same
"bring your own password" mechanism as Keycloak's dedicated database
(ADR-0315): Vault is seeded out-of-band
(`ansible/roles/vault/tasks/install.yml`, key `rag/postgresql-app`), and
this chart's own `ExternalSecret` re-materializes that same Vault
credential in `zuno-ai-build` (PGO's own generated Secret lives in
`zuno-data`; `secretKeyRef` can't cross namespaces).

## Embedding model

`embedding.endpoint`/`embedding.model`/`embedding.dimensions` point at
`gitops/charts/models`' additive `embeddingModel` (KServe InferenceService
`embeddings`, `BAAI/bge-small-en-v1.5`, 384-dim) - the same backing
service `gitops/charts/rag-service` already expected by default
(`embeddings-predictor.zuno-ai-run.svc`), closing what was previously a
dangling placeholder on that side too.

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

OpenShift AI / Kubeflow Pipelines orchestrates the chain. The chart creates the `Pipeline` CR and a ConfigMap containing the rendered KFP source, plus a `REDHAT_SOURCES_JSON`/`CONFLUENCE_SOURCES_JSON`-carrying ConfigMap (`templates/configmap.yaml`) since KFP's `use_config_map_as_env` only maps flat key/value pairs and both sources are now arrays.

## Scheduling

`schedule.cron`/`schedule.timezone` describe the desired KFP recurring-run
cadence. RHOAI's DataSciencePipelinesApplication doesn't expose a
Kubernetes-native `RecurringRun` CRD, only the KFP v2beta1 HTTP API, so
`ansible/roles/rag_ingestion/tasks/install.yml` activates the schedule via
`ansible.builtin.uri` calls against the DSPA's own OAuth-proxied Route
(the same path the OpenShift AI dashboard itself uses) after the pipeline
is confirmed Ready. This is **best-effort and UNVERIFIED against a live
cluster** - the Route-naming assumption (`ds-pipeline-rag-dspa`), the
"newest version is index 0" assumption, and the recurring-run payload
shape all need confirming on a real cluster; a failure here is logged but
does not block the rest of `make d1 install rag-ingestion` - create the
schedule manually via the dashboard if it doesn't activate automatically.
`schedule.timezone` is not passed to the API: this KFP version has no
confirmed equivalent field, and guessing one felt worse than omitting it.

## Runtime image / CLI stages

The build context and CLI are at `components/rag-ingestion/`
(`src/rag_ingestion.py`). All eight stages are implemented - each one
round-trips its state through S3 rather than local disk, since KFP runs
every stage in its own pod:

```text
fetch-redhat      crawls each enabled redhat[] documentationUrl, discovers same-book
                  chapter links, writes raw HTML + metadata to <rawPrefix>/<doc_id>.json
                  (fetchMode: pdf is not implemented - logged and skipped, not faked)
fetch-confluence  Confluence Cloud REST API v1 (wiki/rest/api/content/search, CQL by
                  space), filters by directories (ancestor-title path match, best-effort -
                  Confluence has no literal directories) and excludeLabels, tags each
                  page's acl_groups from its confluence[] entry's requiredGroups
detect-changes    diffs raw doc sha256 against a persisted manifest; incremental=false
                  reprocesses everything; corpus.deleteOrphans drives orphan cleanup
normalize         strips nav/script/style, preserves code blocks/tables as atomic
                  fenced/tabular text per chunking.preserveCodeBlocks/preserveTables
chunk             tiktoken (cl100k_base) token-aware splitting at chunking.maxTokens/
                  overlapTokens; falls back to a whitespace approximation if tiktoken's
                  encoding can't be loaded (no network egress); code-fenced blocks are
                  never split, even when they alone exceed maxTokens
embed             calls embedding.endpoint in embedding.batchSize batches, using the
                  exact same request/response contract as rag-service's own
                  app/embeddings.py (POST {endpoint}/embeddings, {model, input: [...]})
index-pgvector    upserts into document_embeddings (source, chunk_index) - see
                  data/rag/schema/004_rag_chunking.sql - and deletes orphaned rows
validate          fails (non-zero exit) if any document this run touched has zero rows
                  or any chunk with a NULL embedding
```

Not yet exercised end to end against a live cluster/real credentials from
this environment (no network egress to Red Hat docs/Confluence/a real
Postgres+S3 from here) - verified instead via `py_compile`, `helm lint`/
`helm template`, and targeted fixture tests of the pure logic (HTML
normalization, chunk splitting incl. oversized-paragraph and
code-block-atomicity edge cases, manifest diffing across new/changed/
deleted/unchanged documents).

## Files still requiring real environment values

Start with `examples/values-satellite.yaml` and replace:

- AWS bucket and region
- existing External Secrets `SecretStore` / `ClusterSecretStore` name and remote keys
- actual Confluence space keys and page-tree directories
- the non-Satellite `redhat[]` version/documentationUrl entries (CONFIRM against docs.redhat.com)

For production OpenShift AI Pipelines metadata, use an external MySQL/MariaDB rather than the embedded demo database.
