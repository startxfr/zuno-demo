# ADR-0546: Introduce a cross-cluster source bucket and per-cluster S3 bucket convention

- **Status:** Proposed
- **Target:** v0.8
- **Date:** 2026-09-03
- **Decision owners:** Zuno Demo architecture team

## Context

`zuno-demo` (single cluster `demo222` today) uses seven S3 buckets, all provisioned
manually — there is no AWS IaC in this repository (ADR-0211) — and referenced from
`ansible/confidential.yml` (credentials) plus `gitops/charts/*/values.yaml` (bucket
name/endpoint/prefix). ADR-0517 is preparing a second cluster, `demo333`, deployed
from scratch in parallel with `demo222` (no migration), but it does not settle any
storage-architecture question: WP-118 closed exactly one S3 gap (undocumented
MariaDB backup variables) and explicitly left bucket sharing-vs-duplication across
clusters undecided.

A cross-repository audit (ansible/, gitops/, docs/adr/) found the current bucket set
already mixes two different kinds of data inside the same buckets:

- **Cross-cluster inputs** — data that is identical no matter which cluster consumes
  it, and that a brand-new cluster needs in order to exist at all (model weights, the
  raw SXA legacy dump, reusable training corpora).
- **Per-cluster outputs** — data a specific cluster's own workloads produce or need
  for themselves (ingested/normalized RAG corpus, MLflow experiment tracking, KFP
  pipeline run objects, DB backups, monitoring traces, Automation Hub content).

| # | Bucket (real name) | Region | Vault path | Contents |
|---|---|---|---|---|
| 1 | `zuno-demo-rag-corpus` | eu-west-2 | `rag/s3` | model weights (`models/<name>/`), ingested RAG corpus (raw/normalized/manifest/failed), lmeval tokenizer cache, mlops model read/write |
| 2 | `zuno-corpus` | us-east-1 ⚠️ undocumented | `rag/s3` (same credential, different bucket) | MLflow artifacts, mlops KFP pipeline objects (dataset/model/eval/registry prefixes), training-corpus tarball (`qwen-wesh-training-corpus.tgz`) |
| 3 | `zuno-demo-sxa-corpus` | eu-west-2 | `sxa-corpus/s3` | raw SXA legacy mysqldump export (ADR-0216/0217/0219) |
| 4 | `zuno-data-pgbackups` (chart calls it `zuno-mariadb-backups`) | eu-west-2 | `postgresql/backup-s3` **and** `mariadb/s3` | pgBackRest (PostgreSQL) + PhysicalBackup (MariaDB) — already one physical bucket shared via two credentials |
| 5 | `zuno-aap-hub` | (Vault-sourced) | `aap/hub-s3` | Automation Hub content storage (WP-075) |
| 6 | `zuno-demo-rhoai-traces` | (Vault-sourced) | `rhoai/traces-s3` | RHOAI monitoring stack traces (`data-science-tempostack`) |
| 7 | `sx-helm-repository-prod` (S3 static website, public, eu-west-3) | — | none | third-party/org-wide Helm chart repo — not application data |

`zuno-monitoring`'s own TempoMonolithic (distinct from RHOAI's) uses PV storage, not
S3 — out of scope. No S3-backed container registry exists today (Quay.io is used).

Anomalies found along the way, independent of the cross-cluster question:

- `zuno-corpus` is undocumented in `confidential.example.yml`, lives in a different
  AWS region than everything else (forcing mlops to build two separate boto3
  clients), and does not follow the `zuno-demo-*` naming used elsewhere.
- The backup bucket is already shared between two DB engines via two distinct
  credentials — a pattern worth keeping rather than fighting.
- WP-079 already hit a live IAM-scoping bug from credential reuse: the
  `zuno-sxa-corpus-s3` IAM user was reused for AAP Hub and RHOAI traces without the
  right `s3:ListBucket` grant.

## Decision

1. Introduce **one cross-cluster source bucket**, `zuno-demo-sources`, holding only
   data that is identical across clusters and that a brand-new instance needs to
   bootstrap:
   - `models/<servedModelName>/` — every served model's weights, both pretrained
     base models and locally fine-tuned/merged variants (e.g. `qwen3.5-9b-wesh`).
     Fine-tuned checkpoints are promoted here directly by the training pipeline,
     exactly as `zuno-demo-rag-corpus/models/` works today.
   - `sxa-dump/` — the raw SXA legacy mysqldump export.
   - `training-corpus/` — reusable fine-tuning/style-adaptation corpora (e.g.
     `qwen-wesh-training-corpus.tgz`).
   - Any future raw external-system export meant to seed a new instance follows this
     same convention.

   A new, already-ingested/normalized RAG corpus is explicitly **not** treated as a
   cross-cluster source: each cluster re-runs its own ingestion pipeline against the
   raw sources (this bucket, plus its own live pulls from Confluence/Salesforce/etc).
   Re-ingestion is the existing, already-optimized path (ADR-0519/ADR-0520).

2. Introduce **N per-cluster buckets**, named `zuno-<cluster_name>-<purpose>`. For
   `demo222` today:

   | Bucket | Contents | Replaces |
   |---|---|---|
   | `zuno-demo222-data` | RAG ingestion outputs (raw/normalized/manifest/failed, all domains), lmeval tokenizer cache | ingestion part of `zuno-demo-rag-corpus` |
   | `zuno-demo222-mlops` | MLflow experiment-tracking artifacts, mlops KFP pipeline run objects (dataset/eval/registry prefixes) | mlops/MLflow part of `zuno-corpus` |
   | `zuno-demo222-backups` | pgBackRest under `postgresql/`, PhysicalBackup under `mariadb/` — one bucket, two prefixes, as today | `zuno-data-pgbackups` |
   | `zuno-demo222-traces` | RHOAI/Tempo monitoring traces | `zuno-demo-rhoai-traces` |
   | `zuno-demo222-aap-hub` | Automation Hub content storage | `zuno-aap-hub` |

   A future S3-backed container registry, if one is introduced, follows the same
   convention as `zuno-<cluster_name>-registry`.

3. **Credentials**: one dedicated IAM user and Vault path per bucket (e.g.
   `sources/s3`, `demo222/data-s3`, `demo222/mlops-s3`, `demo222/backups-s3`,
   `demo222/traces-s3`, `demo222/aap-hub-s3`), closing the reuse gap WP-079 hit.
   The shared `demo222-backups` bucket may still use two scoped IAM users (one per
   DB engine, each restricted to its own prefix) to keep least-privilege without
   reopening the one-bucket decision.

4. **Region**: standardize all new buckets (source and per-cluster) on `eu-west-2`,
   matching the majority of the current estate. `zuno-corpus`'s `us-east-1` is
   treated as unintentional drift absent a documented compliance/latency reason;
   this clause is open to revision if such a reason surfaces during review.

5. This ADR is a **decision record only**. It does not create any bucket, move any
   data, or change `ansible/`/`gitops/`. Execution — provisioning, data migration,
   rewiring `ansible/confidential.yml`/`confidential.example.yml`, the Vault role,
   and every affected chart's `values.yaml`/`ExternalSecret` (`models`,
   `rag-ingestion`, `mlflow`, `mlops`, `mariadb`, `postgresql`, `aap`,
   `openshift-ai`), plus old-bucket decommissioning — is scoped into a follow-up
   work package once this ADR is Accepted, most likely tied to ADR-0517/WP-118's
   `demo333` effort.

## Acceptance criteria

- This ADR is reviewed and its Status moves to `Accepted`.
- A follow-up work package exists, scoping the actual bucket provisioning, data
  migration and `ansible`/`gitops` rewiring described in Decision clause 5.
- No `demo222` bucket, credential or chart is touched by this ADR itself.

## Mapping (old → new)

| Content | Current location | Target location |
|---|---|---|
| Model weights (all) | `zuno-demo-rag-corpus/models/` | `zuno-demo-sources/models/` |
| RAG ingestion outputs | `zuno-demo-rag-corpus/<domain>/...` | `zuno-demo222-data/<domain>/...` |
| lmeval tokenizer cache | `zuno-demo-rag-corpus` (lmeval prefix) | `zuno-demo222-data` |
| Raw SXA dump | `zuno-demo-sxa-corpus` | `zuno-demo-sources/sxa-dump/` |
| Training-corpus tarball | `zuno-corpus/qwen-wesh-training-corpus.tgz` | `zuno-demo-sources/training-corpus/` |
| MLflow artifacts | `zuno-corpus/mlflow-artifacts` | `zuno-demo222-mlops/mlflow-artifacts` |
| mlops KFP pipeline objects | `zuno-corpus` | `zuno-demo222-mlops` |
| PostgreSQL backups | `zuno-data-pgbackups` | `zuno-demo222-backups/postgresql/` |
| MariaDB backups | `zuno-data-pgbackups` | `zuno-demo222-backups/mariadb/` |
| AAP Hub content | `zuno-aap-hub` | `zuno-demo222-aap-hub` |
| RHOAI traces | `zuno-demo-rhoai-traces` | `zuno-demo222-traces` |

See [Standard clauses](README.md#standard-clauses) for Alternatives, Consequences,
Security/Operational considerations, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0211](0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md)
- [ADR-0216](0216-import-real-sxa-content-via-s3-into-mariadb-served-through-mcp-and-rag.md)
- [ADR-0217](0217-ingest-a-weekly-sxa-corpus-as-a-new-rag-domain.md)
- [ADR-0219](0219-serve-sxa-only-as-a-historical-rag-corpus.md)
- [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md)
- [ADR-0519](0519-parallelize-and-shortcut-the-rag-ingestion-fetch-stages.md)
- [ADR-0520](0520-parallelize-the-detect-changes-read-stage.md)
- [ADR-0526](0526-fine-tune-and-serve-a-french-urban-register-model-variant.md)
- [ADR-0538](0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md)
- [ADR-0539](0539-delegate-lora-training-compute-to-a-kfp-submitted-trainjob.md)
- [ADR-0517](0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md)
