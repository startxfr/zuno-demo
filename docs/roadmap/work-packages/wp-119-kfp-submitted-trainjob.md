# WP-119: LoRA training compute as a KFP-submitted TrainJob

- **State:** Done (2026-09-04, closed by
  [WP-126](wp-126-finalize-lora-trainjob.md)) — the mechanism this WP built is now
  live-proven: flag flipped to `true`, a real `TrainJob` reached `Complete`
  end to end (scale-from-zero, training, S3 manifest, MLflow visibility,
  scale-back-to-zero), with 4 live-only defects found and fixed along the way.
  See ADR-0539's `Status: Implemented` line and WP-126's file for the full
  evidence.
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

Closed by [WP-126](wp-126-finalize-lora-trainjob.md) (live-verified 2026-09-04):

1. ~~The scale-from-zero probe.~~ Proven live twice: `zuno-gpu-burst-a` scaled
   0→1 on two separate real `TrainJob` runs, with GPU device plugin
   registration and training running to completion each time.
2. ~~Confirm `spec.trainer` overrides the container named `node`.~~ WP-126
   finding 4 found and fixed a structural bug (`trainjob-ancestor-step` label
   one level too deep) that had been silently preventing any override;
   confirmed live afterward: `command`/`args`/`env_count=48` all correctly
   applied.
3. Confirm a JobSet-owned pod terminates under istio injection in
   `zuno-mlops`. Not explicitly called out in WP-126's write-up, but
   implicitly confirmed: the run reached `AllJobsCompleted` with no mesh
   issue reported. Treat as resolved; revisit only if a future run shows
   sidecar-related hangs.
5. `MLFLOW_TRACKING_URI`/trainer-pod SA access. Implicitly resolved: the
   `wp126-20260904-075724` run is visible in MLflow (experiment 34), so the
   trainer pod's ServiceAccount does have workspace access.
4. ~~The negative test.~~ **Live-verified 2026-09-04** (run `wp126-20260904-095517`,
   `TrainJob lora-comage-xwv7z`): the `comage` agent's ConfigMap
   `MLOPS_LORA_TARGET_MODULES` was live-patched to `nonexistent_module_xyz`
   (ArgoCD `automated` sync paused first, restored after). `peft.get_peft_model`
   raised `ValueError: Target modules nonexistent_module_xyz not found in the
   base model` after the base model loaded, the Job failed (`backoffLimit: 0`),
   the TrainJob reached `Failed:FailedJobs`, the KFP `train-lora` step exited
   `status 1`, and no `merge-export` pod was ever created for the run
   (confirmed by listing every pod for the run). ConfigMap reverted, ArgoCD
   `Synced`/`Healthy` confirmed afterward, `zuno-gpu-burst-a` scaled back to 0
   ~7.7 minutes after the pod failed.

All five items are now closed. WP-119 has no remaining open engineering work.

## Verification

```bash
cd components/mlops && ./.venv/bin/python tests/test_trainjob.py   # 12 passing
helm template m gitops/charts/mlops | grep -c set_accelerator_type              # 1 (fallback)
helm template m gitops/charts/mlops --set training.trainJob.enabled=true \
  | grep -c set_accelerator_type                                               # 0 (submitter)
oc get trainingruntime,trainjob -n zuno-mlops
make d2 check mlops
```
