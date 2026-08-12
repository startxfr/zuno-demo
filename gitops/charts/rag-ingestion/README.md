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
ever stamped on chunks from these sources. Ships with 8 entries (2 latest
versions x 4 techs: Red Hat Satellite, OpenShift Container Platform,
OpenShift AI, Red Hat build of Keycloak) - only the Satellite 6.17/6.16
version strings are confirmed; the rest are this chart's current best
guess and are marked `CONFIRM` in `values.yaml` pending verification
against docs.redhat.com.

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
cadence, but are not yet wired into a chart-rendered resource: this
RHOAI/DataSciencePipelinesApplication version does not expose a
Kubernetes-native `RecurringRun` CRD, only the KFP v2beta1 HTTP API.
Creating the recurring run is a follow-up activation step (manual via the
OpenShift AI dashboard / KFP UI, or a future `uri`-based Ansible task
against the DSPA's API route) - deliberately left undone rather than
shipping an unverified custom-resource manifest.

## Runtime image status

The build context and CLI contract are included under
`components/rag-ingestion/`. The container is buildable now, but the
eight ingestion stage implementations are intentionally guarded until the
remaining environment-specific values are fixed (AWS bucket/region,
Confluence spaces/directories, pgvector endpoint/schema and embedding
endpoint/model). This prevents a successful-looking but incomplete data
ingestion.

The stable command contract is:

```text
rag-ingestion fetch-redhat
rag-ingestion fetch-confluence
rag-ingestion detect-changes
rag-ingestion normalize
rag-ingestion chunk
rag-ingestion embed
rag-ingestion index-pgvector
rag-ingestion validate
```

## Files still requiring real environment values

Start with `examples/values-satellite.yaml` and replace:

- AWS bucket and region
- existing External Secrets `SecretStore` / `ClusterSecretStore` name and remote keys
- actual Confluence space keys and page-tree directories
- the non-Satellite `redhat[]` version/documentationUrl entries (CONFIRM against docs.redhat.com)

For production OpenShift AI Pipelines metadata, use an external MySQL/MariaDB rather than the embedded demo database.
