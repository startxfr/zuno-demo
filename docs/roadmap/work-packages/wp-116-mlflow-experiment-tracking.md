# WP-116: MLflow experiment tracking for the MLOps pipeline

- **State:** Not started (2026-09-02)
- **ADRs:** [ADR-0538](../../adr/0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md)
  (decisions 1-2), [ADR-0302](../../adr/0302-build-dataset-to-model-mlops-pipelines.md)
  (KFP stays the orchestrator; S3 manifests stay the system of record),
  [ADR-0526](../../adr/0526-fine-tune-and-serve-a-french-urban-register-model-variant.md)
  (the LoRA run being instrumented and backfilled)
- **Depends on:** ADR-0331 (namespace constraint), the PGO cluster (ADR-0529 pguser mechanics)
- **Related:** WP-115, WP-117 (the other two dashboard surfaces)

## Goal

The RHOAI dashboard's Experiments page reports "MLflow not configured": the `mlflowoperator`
component has been `Managed` for weeks with no `MLflow` CR ever created. Meanwhile the LoRA
pipeline's only record of a training run is S3 JSON, and the Model Registry keeps just
`classification` + `base_model` - no hyperparameters, no metrics, no way to compare the runs
whose variance ADR-0526 itself documents.

This WP stands up the tracking server (PostgreSQL-backed), wires the pipeline to log to it
non-fatally, and backfills the one existing green run so the page shows real history
immediately.

## Steps

### Step 1 - the `mlflow` PGO database
Vault seed `mlflow/postgresql-app` (password restricted to letters+digits: the URI interpolates
it un-encoded), `postgresql_pguser_bootstrap_secrets` entry (ADR-0529: the pguser ExternalSecret
uses `creationPolicy: Merge`, which cannot create a missing Secret - the role's precreate step
is mandatory), `mlflowDatabase` values block + `externalsecret-mlflow.yaml` + the user/database
entry on the PostgresCluster. Live: `make d0 vault install` then `make d0 postgresql install`.

### Step 2 - the `mlflow` Day 2 component
New `gitops/charts/mlflow/` (mirroring `trustyai-config`'s gated shape) with: the backend-store
ExternalSecret composing `postgresql://user:pass@zuno-postgresql-primary.zuno-data.svc:5432/
mlflow` (**primary, not PgBouncer** - Alembic/SQLAlchemy vs transaction pooling, the documented
MaaS-DB choice), the cluster-scoped `MLflow` CR (`backendStoreUriFrom`,
`workspaceLabelSelector: opendatahub.io/dashboard=true`), and per workspace
(`zuno-ai-run`, `zuno-mlops`) an `mlflow-artifact-connection` ExternalSecret (Vault `rag/s3`,
bucket `zuno-corpus`) plus an `MLflowConfig` (**group `mlflow.kubeflow.org`**, not
`opendatahub.io`). Plus `-d0`/`-d1` Applications, the Ansible role, and Makefile/playbook
wiring. Separate commit: open `redhat-ods-applications`'s `allowedFromNamespaces` (today `[]`)
to `zuno-mlops`/`zuno-ai-run`.

### Step 3 - discover the tracking contract (gate)
The in-cluster tracking URI and the operand's workspace-selection mechanism are not derivable
from the CRD. Discover them live (Service + a curl from a `zuno-mlops` pod) BEFORE any pipeline
code depends on their shape. Nothing in Step 4 is written until this returns a concrete answer.

### Step 4 - pipeline logging (non-fatal)
`mlflow-skinny` in the mlops image; `_mlflow_log_training()` after the train manifest write
(experiment `mlops-<agent>`, run name = `run_id`, LoRA hyperparameters as params, `train_loss`/
`steps` as metrics) and `_mlflow_log_gate()` after `gate_result.json` (gate outcome + scores,
run found by `run_id` tag). Both no-op without `MLFLOW_TRACKING_URI` and swallow every
exception: **a tracking outage must never fail a training or evaluation run** (ADR-0538
decision 2). Wire `MLFLOW_TRACKING_URI` through the chart ConfigMap AND `BASE_CONFIG_KEYS` in
`pipeline.py.tpl` (a key absent from that map never reaches the step pod), and bump
`pipeline.version` (PipelineVersion specs are immutable). Extend the standalone test script.

### Step 5 - backfill `wesh-20260829-145123`
A one-off idempotent script reading that run's S3 manifests and creating the experiment/run
retroactively (start time from the manifest), run in-cluster with the mlops image. This is what
makes the Experiments page meaningful without re-spending ~2h of burst-node GPU.

## What NOT to touch

- KFP's orchestrator role (ADR-0302 decision 1) - this WP adds tracking, it moves no stage.
- The S3 manifests / Model Registry - they stay the system of record; MLflow mirrors them.
- The DSC (`mlflowoperator` is already `Managed`) - and remember DSC edits need `oc patch`
  anyway (ArgoCD `ignoreDifferences` on `/spec`).

## Verification checklist (operator step - ask before running)

1. `oc get secret zuno-postgresql-pguser-mlflow -n zuno-data` carries both ESO keys and PGO's
   `uri`/`host`; `\l` in a postgres pod lists the `mlflow` database.
2. `oc get mlflow` shows the server Ready; its Deployment/Service run in
   `redhat-ods-applications`; the operator's migration Job succeeded (Alembic tables exist).
3. `oc get mlflowconfig -A` returns both workspaces; the dashboard Experiments page lists them.
4. A curl from a `zuno-mlops` pod reaches the tracking API (proves the NetworkPolicy opening -
   never infer this from pipeline logs, decision 2 makes them silent).
5. The backfilled `wesh-20260829-145123` run is visible with its LoRA params, `train_loss` and
   gate outcome.

## Risks and known unknowns

1. The tracking-URI/workspace contract is the one genuinely undiscoverable-from-git unknown -
   isolated as a gate (Step 3) precisely so no code is written against a guess.
2. PgBouncer would break Alembic migrations - the primary Service is used deliberately; do not
   "optimize" it onto the pooler later.
3. PGO never recreates a dropped database ([[pgo-does-not-recreate-dropped-database]]): if the
   `mlflow` DB is ever dropped by hand, the whole cluster reconcile error-loops.
4. The backfill fabricates a historical run from manifests - it must be marked as such (a tag)
   so it is never mistaken for a natively-tracked run.

## Status updates (once live-verified)

- `State` moves to `Done` once the checklist passes, including the visible backfilled run.
