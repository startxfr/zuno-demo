# ADR-0538: Adopt RHOAI 3.5 workload surfaces - MLflow tracking, queued workloads, training-jobs UI

- **Status:** Accepted
- **Target:** v0.7
- **Date:** 2026-09-02
- **Decision owners:** Zuno Demo architecture team

## Context

The 2026-09-02 human review of the RHOAI dashboard (the same session that closed ADR-0534's
visibility gap via WP-113/WP-115) surfaced four dashboard pages this platform leaves empty or
unconfigured:

- **Experiments** - "MLflow not configured": the `mlflowoperator` DSC component has been
  `Managed` since ADR-0331, but no `MLflow` CR was ever created; the operator has sat idle since
  install. Meanwhile the only experiment tracking the MLOps pipeline (ADR-0302/ADR-0526) has is
  S3 JSON manifests, and the Model Registry stores just two custom properties - the run-to-run
  variance ADR-0526 documents (4-run table in `components/mlops/src/mlops.py`'s docstring) has
  no comparison surface at all.
- **Workload metrics** - "Configure the project queue": Kueue is installed and reconciled
  (ADR-0321, standalone operator, DSC `kueue: Unmanaged`) but has **never admitted a single
  workload**: no zuno namespace carries the `kueue.openshift.io/managed` label, the only
  LocalQueue sits in `zuno-ai-build` where nothing is labeled for queueing, the ClusterQueue
  covers cpu/memory only, and the GPU ResourceFlavor precondition ADR-0321's own text set
  ("must account for GPU ResourceFlavor and quotas before ... queued model workloads") was
  never discharged.
- **Jobs** - "No TrainJobs or RayJobs": the Kubeflow Trainer 2.1 / training-operator / KubeRay
  controllers all run, 15 `ClusterTrainingRuntime`s are usable, and nothing in this repo submits
  any of them - by design so far (openshift-ai values comments defer to "the actual future
  consumer").
- **Evaluations** - handled separately by WP-115 (ADR-0534's surface: dashboard feature flags +
  the `zuno-evalhub` instance).

GPU reality these decisions must fit (ADR-0351/ADR-0537): the two standing GPU nodes are
MIG-partitioned (`all-balanced`: per node 2x `nvidia.com/mig-1g.24gb` + 1x
`nvidia.com/mig-2g.48gb`, and `nvidia.com/gpu` allocatable is **zero**), while LoRA training
deliberately uses a whole-GPU scale-from-zero burst node (ADR-0526 Operational considerations).

## Decision

1. **MLflow experiment tracking goes live, PostgreSQL-backed.** One cluster-scoped `MLflow` CR
   (new Day 2 component `mlflow`, mirroring the `trustyai-config` shape) with
   `backendStoreUriFrom` pointing at a pre-composed URI Secret for a **new dedicated `mlflow`
   database on the existing Crunchy PGO cluster** (the platform's ~19-dedicated-DBs pattern;
   connection via the primary Service, not PgBouncer - Alembic migrations and SQLAlchemy
   session state do not survive transaction pooling, same documented choice as the MaaS DB).
   `workspaceLabelSelector` exposes every `opendatahub.io/dashboard=true` namespace as a
   workspace; `zuno-ai-run` and `zuno-mlops` each get an `MLflowConfig`
   (group `mlflow.kubeflow.org` - NOT `opendatahub.io`) plus the conventional
   `mlflow-artifact-connection` Secret targeting the existing `zuno-corpus` S3 bucket
   (Vault `rag/s3` credentials via ExternalSecrets).
2. **The MLOps pipeline logs to MLflow - non-fatally.** `train-lora` logs hyperparameters and
   training metrics, `evaluate` logs the ADR-0107 gate outcome, keyed by `run_id`. Every MLflow
   call is best-effort: **a tracking outage must never fail a training or evaluation run** -
   the S3 manifests (ADR-0302 decision 3) remain the pipeline's system of record; MLflow is a
   comparison/visualization surface over them, not a dependency. The existing
   `wesh-20260829-145123` run (ADR-0526's one green run) is backfilled from its manifests so
   the Experiments page shows real history without re-spending ~2h of GPU.
3. **Kueue's GPU precondition is discharged and the queue gets its first real consumers.** A
   `gpu-mig` ResourceFlavor (real nodeLabels for the MIG nodes) and a ClusterQueue covering
   `nvidia.com/mig-1g.24gb`/`nvidia.com/mig-2g.48gb` alongside cpu/memory (two resourceGroups -
   a resource may belong to only one). LocalQueue `default` lands in `zuno-ai-run`, and the
   namespace gets the `kueue.openshift.io/managed` label - safe because the operand runs
   `manageJobsWithoutQueueName: false`, so **only Jobs that opt in via
   `kueue.x-k8s.io/queue-name` are ever touched**. First consumers: the `trustyai-config`
   evaluation Jobs (garak/ragas), giving the Workload metrics page genuinely admitted
   workloads. KFP-launched training pods stay un-queued (the operand integrates the `BatchJob`
   framework only); `zuno-mlops` gets no LocalQueue.
4. **TrainJobs/RayJobs: UI enabled, adoption deferred and framed.** The dashboard's
   training-jobs surface is turned on (`trainingJobs: true`), but no workload moves off KFP:
   ADR-0302 decision 1 (still in force) keeps KFP as the pipeline orchestrator. The conforming
   future shape - already anticipated by the openshift-ai values comments - is **a KFP step
   submitting a TrainJob/RayJob** (KFP stays the orchestrator; the step delegates the compute),
   and doing that is explicitly a later ADR once a distributed-training need exists.
5. **Dashboard feature flags are live-patched, not GitOps-managed.** `OdhDashboardConfig/
   odh-dashboard-config` is operator-created and outside this repo (same posture ADR-0534's
   Operational considerations already document for `disableLMEval`/`guardrails`); this ADR adds
   `trainingJobs: true` the same way and records all such flags here as the authoritative list:
   `disableLMEval: false`, `guardrails: true`, `trainingJobs: true`.

## Non-goals

Moving LoRA training off KFP (decision 4 defers it); queueing KFP pods (the operand's only
integration framework is BatchJob); MLflow model-registry duty (the RHOAI Model Registry,
ADR-0302 decision 6, keeps that role - MLflow tracks experiments, it does not register serving
candidates); bias-monitoring `TrustyAIService` (out of scope per ADR-0534).

## Operational considerations

- The MLflow server lives in `redhat-ods-applications` (the operator hardcodes its namespace -
  ADR-0331's constraint family), which currently admits **no** cross-namespace ingress
  (`allowedFromNamespaces: []`); the namespaces chart must open it to `zuno-mlops` and
  `zuno-ai-run` or every pipeline-side tracking call times out - silently, because decision 2
  makes those calls non-fatal. Verify connectivity explicitly, never via pipeline logs alone.
- The in-cluster tracking URI and the operand's workspace-selection contract are not derivable
  from the CRD; they are discovered live before any `mlops.py` code depends on them (WP-116
  gates on it).
- PGO never recreates a manually dropped database, and the pguser ExternalSecrets use
  `creationPolicy: Merge` (which cannot create a missing Secret) - the vault-seed +
  postgresql-role precreate ordering (ADR-0529) is mandatory for the new `mlflow` role.
- Kueue suspends an opted-in Job until admission; the Job controller resets `startTime` on
  unsuspend, so `activeDeadlineSeconds` budgets are unaffected. A suspended Job reports
  Progressing to ArgoCD - a mis-sized ClusterQueue would show up as a stuck sync, which is the
  correct failure mode (visible, not silent).
- A KFP `PipelineVersion` spec is immutable: the pipeline env change (MLFLOW_TRACKING_URI)
  requires a `pipeline.version` bump, or the old spec silently stays in force.

## Migration / evolution

Executed by [WP-116](../roadmap/work-packages/wp-116-mlflow-experiment-tracking.md) (decisions
1-2) and [WP-117](../roadmap/work-packages/wp-117-kueue-gpu-quota-and-queued-workloads.md)
(decision 3, plus the decision-5 flag patch). [WP-115](../roadmap/work-packages/wp-115-trustyai-dashboard-ui-flags-and-evalhub.md)
(ADR-0534) delivered the Evaluations surface this ADR builds beside. Future: a dedicated ADR for
KFP-submitted TrainJobs when distributed training becomes real; MLflow-side alerting/retention
tuning as usage accumulates.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Consequences,
Security considerations, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0534](0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md) - the sibling
  dashboard-visibility effort (Evaluations/guardrails surfaces, WP-113/WP-115).
- [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md) - KFP stays the orchestrator
  (decision 1 in force); its S3 manifests remain the system of record MLflow mirrors.
- [ADR-0526](0526-fine-tune-and-serve-a-french-urban-register-model-variant.md) - the LoRA
  flow being instrumented; its one green run is the backfill source.
- [ADR-0321](0321-delegate-kueue-lifecycle-to-the-red-hat-build-of-kueue-operator.md) - the Kueue installation whose GPU
  precondition decision 3 discharges.
- [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md),
  [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md),
  [ADR-0537](0537-integrate-rhoai-hardware-profiles-and-maas-external-models.md) - namespace and
  GPU-topology constraints these decisions fit inside.
