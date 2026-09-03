# WP-126: finalize the LoRA TrainJob (lift WP-119's "shipped disabled")

- **State:** Operator pending (2026-09-03)
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

3. **A third, still-unresolved defect: `trainjob.py`'s own K8s API call to `kubernetes.default.svc`
   fails TLS verification, deterministically, only inside the real KFP-launcher-wrapped execution.**
   After the image rebuild (finding 2, fixed), a fresh run's `train-lora` step correctly reached
   `_find_existing`'s `session.get(...)` call and failed with the same
   `SSLCertVerificationError: ... self-signed certificate in certificate chain` on **two separate
   run attempts** (ruling out a transient/race explanation). Manual reproduction in a throwaway
   pod - same image, same `pipeline-runner-mlops-dspa` ServiceAccount, same explicit
   `session.verify = /var/run/secrets/kubernetes.io/serviceaccount/ca.crt` call - **succeeds
   cleanly** (`Verify return code: 0`), twice, including with `SSL_CERT_FILE` explicitly set to
   the same 227958-byte merged `/kfp/certs/ca.crt` bundle the real pod also mounts (ruling out
   that env var as the cause too - `requests`'s explicit `session.verify=` path does not consult
   `SSL_CERT_FILE`). Confirmed `kube-root-ca.crt` (the modern projected-volume source for the
   standard SA `ca.crt` mount) correctly contains all 7 expected signers, including
   `kube-apiserver-service-network-signer` (the one that actually signs `kubernetes.default.svc`'s
   served cert, confirmed via direct `openssl s_client`). Two concrete hypotheses tested and
   disproved; root cause not yet identified. Something specific to the Argo `emissary` executor's
   process-wrapping of the launched Python process is the remaining suspect, untested.

### Original live-action plan (now resuming against a rebuilt image)

1. Trigger the `mlops` KFP pipeline's LoRA training stage for a real run (the same wesh-style
   dataset WP-119/ADR-0526 already used, unless a different real case is preferred).
2. Watch the JobSet-owned pod actually materialize on `zuno-gpu-burst-a` from a scaled-from-zero
   node - this is the one step WP-119 explicitly left unverified ("the scale-from-zero probe for a
   JobSet-owned pod").
3. Confirm the `TrainJob` reaches a terminal `Complete` condition and `mlops.py`'s
   `train_manifest.json` verification against S3 passes (per WP-119, it does not trust the
   `Complete` condition alone).

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
