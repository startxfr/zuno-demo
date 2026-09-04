# WP-126: finalize the LoRA TrainJob (lift WP-119's "shipped disabled")

- **State:** Operator pending (2026-09-04) - 4/4 known defects fixed and live-verified individually;
  no run has yet completed end to end (last attempt interrupted by a planned cluster stop, not by
  a defect)
- **ADRs:** ADR-0545 (decision 1), ADR-0539, ADR-0538
- **Depends on:** WP-119 (Repo work merged, 2026-09-02)
- **Related:** [ADR-0351](../../adr/0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md)
  (the burst-node mechanism this WP's live run exercises)

> **Live cluster action - requires explicit operator go-ahead before execution.** Flipping the
> flag and running a real LoRA job triggers a genuine `MachineAutoscaler` scale-up of
> `zuno-gpu-burst-a` from zero. Do not run the live steps without confirming first.

## Goal

WP-119 built and merged the whole mechanism - a KFP step that submits a Kubeflow `TrainJob` to
the namespaced `mlops-lora` `TrainingRuntime` and waits - but shipped it disabled
(`training.trainJob.enabled: false`). This WP turns it on and proves it end to end with one real
LoRA training run, closing the gap the Kubeflow Trainer controller has had since install (15
`ClusterTrainingRuntime`s usable, zero consumers).

## Preconditions (verify before starting)

- WP-119 merged; `components/mlops/src/trainjob.py`, `gitops/charts/mlops/templates/
  trainingruntime.yaml` and the widened RBAC (`pipeline-runner-mlops-dspa`) are in place.
- `zuno-gpu-burst-a`'s `MachineAutoscaler` (min 0 / max 1) is healthy and not already scaled up for
  an unrelated reason.
- Confirm live whether the burst node's GPU allocation is isolated from the MIG `ResourceFlavor`
  quota that WP-121 found saturated (`mig-1g.24gb` 3/3, `mig-2g.48gb` 2/2) - the burst node is a
  separate, non-MIG `g7e.2xlarge` per ADR-0351, but verify this against the live `ResourceFlavor`/
  `ClusterQueue` before assuming it is unaffected.

## Repo changes (step by step) - Done, live-verified 2026-09-03

1. Flipped `training.trainJob.enabled: true` in `gitops/charts/mlops/values.yaml` (commit
   `9a0b7303`).
2. **Found and fixed a latent defect `helm template`/`helm lint` could not catch.**
   `mlPolicy.torch.numProcPerNode` rendered as a quoted `"1"` string; the `TrainingRuntime` CRD's
   CEL validation rejects that outright (`'no such overload'` - neither the string-enum branch
   ("auto"/"cpu"/"gpu") nor the int branch matches a quoted numeral). Caught only by
   `oc apply --dry-run=server` against the live cluster, never live-tested since WP-119 merged it
   disabled. Fixed to a bare YAML integer (`numProcPerNode: 1`), same commit.
3. **Preconditions verified live before flipping anything:**
   `zuno-gpu-burst-a`'s `MachineAutoscaler` (min 0/max 1) healthy at 0 replicas, not already
   scaled up. GPU isolation from the saturated MIG `ClusterQueue` quota (ADR-0542) confirmed on
   three independent axes: `zuno-mlops` carries no `kueue.openshift.io/managed` label (not
   Kueue-enrolled at all), the runtime requests `nvidia.com/gpu` (a whole GPU, never
   `nvidia.com/mig-*`), and its `nodeSelector` targets `machine.startx.io/group: gpu-burst` - a
   node group distinct from the two permanent MIG nodes' `group: gpu`.
4. Pushed (`9a0b7303`) and let ArgoCD's `automated`/`selfHeal` sync pick it up - confirmed
   `Synced`/`Healthy`, `op=Succeeded`.
5. **Live-verified the actual cluster objects**, not just the sync status:
   `trainingruntime.trainer.kubeflow.org/mlops-lora` exists in `zuno-mlops` with
   `spec.mlPolicy: {numNodes: 1, torch: {numProcPerNode: 1}}` (the fixed integer, confirmed
   server-accepted); the `zuno-mlops-d1-mlops` Role now carries the four widened rule blocks
   (`trainjobs` create/get/list/watch/delete, `trainingruntimes`/`jobsets`/`pods`/`pods/log`/
   `events` read-only) and its RoleBinding lists both `zuno-mlops-d1-mlops` and
   `pipeline-runner-mlops-dspa` as subjects - exactly WP-119's documented requirement.

## Live actions (confirm before running) - two real defects found and fixed en route, 2026-09-03

Triggering the first real run (`kfp` SDK against the `mlops-dspa` route, `oc apply
--dry-run=server`-verified beforehand) surfaced two independent, previously-invisible defects,
neither in this WP's original scope:

1. **DSP api-server could not create ANY run, for any pipeline - not specific to training.**
   `CreateRun` calls MLflow (WP-116's tracking integration) at `https://mlflow.
   redhat-ods-applications.svc:8443`; the DSP api-server pod rejected its certificate
   (`x509: certificate signed by unknown authority`), retried for ~30s, then failed the whole
   run-creation server-side (`ds-pipeline-api-server` logs: `client rate limiter Wait returned an
   error: context canceled`). Root cause: MLflow's cert is signed by
   `openshift-service-serving-signer` (confirmed via its Service's
   `service.beta.openshift.io/serving-cert-*` annotations and the `mlflow-tls` Secret), but the
   DSP api-server's trust bundle (`dsp-trusted-ca-mlops-dspa` ConfigMap, key `dsp-ca.crt`) only
   ever carried the project's own Vault-issued root (CN `zuno-demo.internal`, sourced from the
   cluster-wide `user-ca-bundle`/`Proxy.spec.trustedCA` via the RHOAI operator's own
   `odh-trusted-ca-bundle` auto-detection) - a completely different CA, never previously exercised
   against an in-cluster service-ca-signed endpoint. **Fixed live**: a new ConfigMap
   (`dsp-mlflow-trust-mlops-dspa`, `zuno-mlops`) concatenates the Vault root
   (`user-ca-bundle`/`ca-bundle.crt` in `openshift-config`) with the namespace's own
   `openshift-service-ca.crt`/`service-ca.crt`, referenced via
   `mlops-dspa.spec.apiServer.cABundle`. The operator merges this into the SAME
   `dsp-trusted-ca-mlops-dspa`/`dsp-ca.crt` file rather than switching ConfigMaps (confirmed by
   its size growing by exactly the new content's byte count) - the deployment needs an explicit
   `oc rollout restart` afterward, since the pod does not reload its trust store from the changed
   file on its own. **Not yet backported to GitOps** - live-only fix, see Follow-up below.
2. **The running `mlops:latest` image predates WP-119 by two commits and has no dispatcher at
   all.** The first real run's `train-lora` step executed `stage_train_lora`'s OLD body (`import
   tempfile` inline, no `import trainjob`) straight into the S3 base-model download - on a
   100m-CPU/512Mi-memory submitter pod sized for a lightweight TrainJob-submit call, not an
   in-process 9B-parameter load. Confirmed via `oc exec`: `/opt/app-root/src/trainjob.py` does not
   exist in the image at all, and `MLOPS_TRAINJOB_ENABLED=true` was correctly present in the pod's
   own env (so the *chart* wiring was right - the *image* was simply stale). The last build
   (`mlops-30`, `oc get builds -n zuno-ai-build`) was from commit `7141a6f` ("WP-116 phase 4"),
   which predates `07c5fb02` ("WP-119 submit LoRA training...") - nobody rebuilt the image after
   WP-119 merged. The run was terminated (`kfp.Client.terminate_run`) before it could OOM or spend
   real wall-clock time on doomed work, and `make d2 build mlops` was triggered to rebuild from
   current `main`.

3. **RESOLVED 2026-09-04. `trainjob.py`'s own K8s API call to `kubernetes.default.svc` failed TLS
   verification, deterministically, only inside the real KFP-launcher-wrapped execution.** Root
   cause found by instrumenting a throwaway diagnostic build (commit `19e95796`, reverted once the
   cause was captured) and triggering one real run: `launcher_v2` (the container's actual PID 1,
   this module's parent process) tries to build its own merged CA bundle before exec'ing the user
   command, fails to read the system CA store at the Debian path
   `/etc/ssl/certs/ca-certificates.crt` (this image is UBI/RHEL, so that read silently fails
   - `launcher_v2.go:746 Error reading CA bundle file`), and sets `REQUESTS_CA_BUNDLE`/
   `SSL_CERT_FILE` to its own incomplete temp file regardless - which never contains the
   kube-apiserver's own signer. `_session()`'s explicit `session.verify = .../ca.crt` looked like
   it should win, but `_find_existing`/`submit_and_wait` call `session.get()`/`.post()` without an
   explicit per-call `verify=`, so `requests.Session.request()`'s own `verify=None` default
   triggers `requests`' environment lookup first, and `REQUESTS_CA_BUNDLE` ends up overriding
   `session.verify` in the final merge (confirmed by reading `requests` 2.32.5's own
   `merge_environment_settings` source). **Fixed** (commit `dda503fa`): `session.trust_env = False`
   in `_session()`, so the session never consults the environment at all. The two hypotheses
   disproved in the previous investigation (incomplete `kube-root-ca.crt`; `SSL_CERT_FILE`
   interference) were both real disproofs of what they tested, just not of the actual mechanism
   (`REQUESTS_CA_BUNDLE`, not `SSL_CERT_FILE`, is what `requests` actually consults on this code
   path).

4. **RESOLVED 2026-09-04. A fourth defect, found only once finding 3's fix let a `TrainJob` submit
   for the first time: the Kubeflow Trainer controller built the JobSet/Job from the
   `TrainingRuntime`'s own container template verbatim and never applied
   `TrainJob.spec.trainer`'s `env`/`command`/`args` overrides at all** - the pod's `node` container
   started with `command: null, args: null, env: [JOB_COMPLETION_INDEX only]` and crashed
   immediately (`mlops: error: the following arguments are required: stage`), with no error
   anywhere in the controller's own logs. A first attempted fix (adding the
   `trainer.kubeflow.org/framework: torch` label, matching RHOAI's shipped runtimes) did **not**
   work - a second live run still showed zero overrides applied. Comparing byte-for-byte against
   RHOAI's own `torch-distributed` `ClusterTrainingRuntime` (`oc get clustertrainingruntime
   torch-distributed -o json`) found the real structural bug:
   `trainer.kubeflow.org/trainjob-ancestor-step: trainer` belongs on the **Job's own metadata**
   (`replicatedJobs[].template.metadata`), which is what the controller uses to find which Job in
   the JobSet is "the trainer step" to patch. `gitops/charts/mlops/templates/trainingruntime.yaml`
   had it one level too deep, on the **pod template's** metadata
   (`replicatedJobs[].template.spec.template.metadata`) - a silent, structural YAML-nesting bug
   that `helm template`/`helm lint`/`oc apply --dry-run=server` all pass, since the label is valid
   at either level; only a live run against the actual controller logic exposes it. **Fixed**
   (commit `14d86bda`): moved the label to the correct level. Confirmed live 2026-09-04: a fresh
   `TrainJob`'s pod showed `command=['/opt/app-root/src/mlops-run']`,
   `args=['train-lora-local', '--run-id', ...]`, `env_count=48` - all four defects now cleared.

### Live-action plan - status 2026-09-04

1. Done. Multiple real runs triggered via `kfp.Client.run_pipeline` against the `mlops-dspa` route
   (pipeline id `d3976051-...` / version `fb1617ae-...`, agent `comage`).
2. **Done, proven live for the first time.** `zuno-gpu-burst-a` scaled 0->1, the JobSet-owned pod
   (`lora-comage-6qcnx-node-0-0-rbwxb`) was placed on the scaled-up node, the GPU device plugin
   registered (~2 min cold start, normal), and the pod ran the real training loop (`2/2 Running`,
   loss decreasing normally, reached 111/224 steps / ~50% before the session ended).
3. **Not yet done.** The 2026-09-04 run was interrupted by a planned cluster stop (operator
   decision, not a defect - see "Resuming this WP" below) before `train-lora` finished, so
   `merge-export`/`evaluate`/`push-registry` never ran. `TrainJob` never reached a terminal
   `Complete` condition; `train_manifest.json` / MLflow visibility / burst-node scale-down are
   still unconfirmed.

### Resuming this WP (next session)

All four defects are fixed and pushed to `main` (commits `dda503fa`, `6d384044`, `14d86bda`; the
diagnostic-only `19e95796` was reverted by `dda503fa`). Nothing code-side is left to investigate -
this is now purely "run it again and watch it finish":

1. After cluster restart, work through the post-restart recovery checklist first (ArgoCD/PgBouncer/
   etc. - see that memory) before touching mlops.
2. Confirm `zuno-gpu-burst-a` is back at 0 replicas (it should have scaled down on its own once the
   interrupted pod's node was torn down by the cluster stop - verify rather than assume).
3. Trigger one more real run with `make d3 run mlops` (`AGENT=<agent>` overrides the default
   `comage`) - wraps the exact `kfp.Client.run_pipeline` sequence proven live 2026-09-03/04 as a
   repeatable command (`ansible/roles/mlops/tasks/run.yml`,
   `components/mlops/tooling/trigger_run.py`). Let it run to completion uninterrupted - training
   alone took ~13 minutes for 224 steps on the previous attempt, so budget for the full pipeline
   (dataset-prep + train + merge-export + evaluate + push-registry) rather than just the training
   loop.
4. Verify the acceptance checks below, then close out this WP's `State` line and ADR-0539's
   `Status` line together.

## What NOT to touch

`components/mlops/src/trainjob.py`'s submit/adopt/poll logic and the RBAC - correct as WP-119 left
them. The `TrainingRuntime` definition needed one field-level fix (`numProcPerNode`, above) that
WP-119 could not have caught without a live dry-run; nothing else about it changed. This WP is the
flag flip plus that fix plus the live proof, not a mechanism redesign.

## Acceptance checks

- `TrainJob` reaches `Complete`; the JobSet-owned pod's node is confirmed as the scaled-up
  `zuno-gpu-burst-a`, not silently scheduled elsewhere.
- `train_manifest.json` lands in S3; the run is visible in MLflow (WP-116's tracking).
- `zuno-gpu-burst-a` scales back to zero afterward (`unneededTime: 10m` per ADR-0351) - confirm
  the scale-down actually happens, not just that scale-up did.
- Rollback is a pure flag revert (`training.trainJob.enabled: false`) - no infrastructure is left
  behind if the run needs to be reverted.

## Operator / human follow-up (not executable by the model)

Explicit confirmation before the live actions section (real GPU node scale-up). Sign-off on the
LoRA run's output quality if it differs from a prior known-good baseline.

## Status updates (then re-run check_docs.py)

On completion: update this WP's `- **State:**` line and its tracker row together; reflect the live
run's outcome in ADR-0539's `**Status:**` line (still `Accepted` unless the live proof moves it
toward `Implemented` - judge against ADR-0539's own stated scope, not this brief).

## Out of scope / deferred

Raising `maxReplicas`/distributed multi-node training (no documented need, ADR-0545 decision 5).
A second fine-tuning use case beyond the existing `-wesh` case - none is currently planned.
