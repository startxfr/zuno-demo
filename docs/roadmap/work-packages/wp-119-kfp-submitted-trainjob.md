# WP-119: LoRA training compute as a KFP-submitted TrainJob

- **State:** Repo work merged (2026-09-02) — shipped disabled
  (`training.trainJob.enabled: false`); the live scale-from-zero probe has not been run
- **ADRs:** [ADR-0539](../../adr/0539-delegate-lora-training-compute-to-a-kfp-submitted-trainjob.md)
- **Depends on:** none
- **Related:** [ADR-0538](../../adr/0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md)
  (decision 4, whose deferral this lifts),
  [ADR-0302](../../adr/0302-build-dataset-to-model-mlops-pipelines.md) (decision 1, re-affirmed)

## Goal

Move the LoRA step's GPU placement out of a compiled DAG and into the chart, by having the KFP
step submit a `TrainJob` instead of doing the training itself.

Before: six Kubeflow SDK calls inside `files/pipeline.py.tpl` — `set_accelerator_type/limit`,
`set_cpu_*`, `set_memory_*`, `add_node_selector`, `add_toleration` — set the whole-GPU request,
the `gpu-burst` node selector and the burst-node toleration. Platform configuration as Python
inside an immutable `PipelineVersion`. After: a namespaced `TrainingRuntime` in Git, and a step
that submits and waits.

Nothing about the training itself changes, and the Kubeflow Trainer controller finally has a
consumer — 15 `ClusterTrainingRuntime`s have been usable since install with nothing submitting to
any of them.

## What landed

- `components/mlops/src/trainjob.py` — submit, adopt-if-already-complete, poll, and a terminal
  contract that raises `SystemExit` so the KFP task fails and `.after()` stops `merge-export`.
- `components/mlops/src/mlops.py` — `stage_train_lora` becomes a dispatcher;
  `stage_train_lora_local` is the unchanged implementation, exposed as the CLI stage
  `train-lora-local` (which the trainer pod runs, so the dispatcher cannot recurse). It also
  verifies `train_manifest.json` reached S3 rather than trusting a Complete condition.
- `gitops/charts/mlops/templates/trainingruntime.yaml` — the `mlops-lora` runtime, reading the
  unchanged `training.gpu`/`training.resources` values.
- `gitops/charts/mlops/templates/rbac.yaml` — the Role was `rules: []`; it now grants `trainjobs`
  create/get/list/watch/delete and read-only on runtimes, jobsets, pods, pods/log and events. The
  RoleBinding gained `pipeline-runner-mlops-dspa` as a second subject — the SA the KFP task pods
  actually run as, without which submission would 403 at runtime while the chart looked correct.
- `gitops/charts/mlops/files/pipeline.py.tpl` — the GPU wiring is now Helm-conditional, and the
  submitter branch gets modest CPU/memory instead. `MLOPS_TRAINJOB_*` added to `BASE_CONFIG_KEYS`.
- `components/mlops/Containerfile` — an explicit `COPY` for `trainjob.py`.
- `gitops/charts/mlops/values.yaml` — the `training.trainJob` block; `pipeline.version` v0-2-0 →
  **v0-2-1**.
- 12 tests in `components/mlops/tests/test_trainjob.py`; 67 across the component, 0 failures.

## Three decisions worth re-reading before changing this

**The in-process path is kept, not deleted.** `training.trainJob.enabled` is `false` by default
and is the documented one-value rollback, so the GPU wiring stays behind a Helm conditional.
Deleting it would make the rollback silently GPU-less — a fallback that no longer works is worse
than no fallback.

**Credential hygiene is a test, not a convention.** `spec.trainer.env` has no `envFrom`, so
config travels as literals and credentials as `valueFrom.secretKeyRef`. A plaintext credential in
a `TrainJob` spec sits in etcd readable by anyone with `get trainjobs` in the namespace.
`SecretHygiene.test_no_credential_value_appears_anywhere_in_the_body` asserts on the rendered
body, so this fails the build rather than a review.

**An unrecognised controller condition means "still running", never "done".** The CRD does not
pin the condition vocabulary. Guessing success from an unknown type would let `merge-export`
start against a model that was never written.

## Remaining

1. **The scale-from-zero probe, before any real run.** Whether the ClusterAutoscaler carries
   MachineSet template labels into its simulated node for a *JobSet-owned* pod is unknown. If it
   does not, the TrainJob pends until the 4h timeout. Probe with a short CPU-only TrainJob;
   ADR-0351's documented fallback is to drop the node selector and keep the toleration plus the
   whole-GPU request.
2. Confirm `spec.trainer` overrides the container named `node`, and that the name is required —
   both are mirrored from the operator's own runtimes, not from documentation.
3. Confirm a JobSet-owned pod terminates under istio injection in `zuno-mlops`. Precedent is good
   (the garak Jobs in `zuno-ai-run` reach `0/2 Completed`), and `zuno-mlops` has a chart-authored
   NetworkPolicy rather than an operator-authored one — but read that file before blaming the
   mesh, per WP-116's finding that an operator NetworkPolicy allowing only DNS and the database
   strands the sidecar.
4. Then `training.trainJob.enabled: true`, a full pipeline run, and the negative test that
   matters: a deliberately broken `MLOPS_LORA_TARGET_MODULES` must fail the TrainJob, exit the
   KFP step non-zero, and never start `merge-export`.
5. One line left for WP-116 phase 4: `MLFLOW_TRACKING_URI` is already forwarded by prefix, but the
   trainer pod authenticates as its own ServiceAccount — if that SA lacks workspace access,
   tracking silently no-ops and looks like "no runs appeared".

## Verification

```bash
cd components/mlops && ./.venv/bin/python tests/test_trainjob.py   # 12 passing
helm template m gitops/charts/mlops | grep -c set_accelerator_type              # 1 (fallback)
helm template m gitops/charts/mlops --set training.trainJob.enabled=true \
  | grep -c set_accelerator_type                                               # 0 (submitter)
oc get trainingruntime,trainjob -n zuno-mlops
make d2 check mlops
```
