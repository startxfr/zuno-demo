# WP-086: Spread the GPU predictors across both MIG nodes, plus two platform-hygiene fixes

- **State:** Done (live-verified 2026-08-26). Machine replaced, predictors spread, all checks
  green except #9, which needs a deliberate node cordon.
- **ADRs:** none new. Relates to ADR-0351 decision 1 (which removed the *hard* anti-affinity
  this WP re-adds in soft form) and ADR-0521 (models are S3-only, so pod placement is not
  pinned by a zone-bound PVC).
- **Depends on:** WP-083 (right-sizing, the second permanent MIG node, the `volumeSize: 250`
  fix whose benefit this WP finally applies to `zuno-gpu-c`)
- **Related:** ADR-0343 (the istio carve-out for the localmodel workloads this WP retires),
  ADR-0518 (current model set)

> Execute this brief as a standalone task from the repository root.

## Goal

Three separate things, bundled because all three were found while closing out WP-083 and none
of them is large enough to carry a WP alone.

1. **Blast radius.** All three GPU predictors run on one node. Losing it takes down every
   model at once, and the survivor would have to cold-start all three.
2. **`zuno-postgresql-repo-host-0` had no requests or limits at all** — its only QoS came from
   the injected istio sidecar.
3. **`kserve.modelCache` was enabled and never used**, at the cost of a permanent reconcile
   loop against one PersistentVolume.

## What changed

### 1. Soft anti-affinity between the GPU predictors

`gitops/charts/models/values.yaml` gains `spreadAcrossGpuNodes: true`, gating a
`podAntiAffinity` term in all three predictor templates:

| Template | Where | Selector |
|---|---|---|
| `llminferenceservice-qwen.yaml` | `spec.template.affinity` | `kserve.io/component: workload` |
| `llminferenceservice-gptoss.yaml` | `spec.template.affinity` | `kserve.io/component: workload` |
| `inferenceservice-embedding.yaml` | `spec.predictor.affinity` | `app.kubernetes.io/name: <inferenceServiceName>` |

Expected layout: `qwen` alone on one node, `gpt-oss` + `embeddings` on the other. The imbalance
is deliberate — the aim is to isolate the chat model MaaS and the agents depend on, not to
even out bytes.

**Every term is `preferredDuringSchedulingIgnoredDuringExecution`.** This is the whole design.
A `required` term would leave a pod `Pending` when only one node survives, instead of packing
it onto the survivor — the exact opposite of the resilience this WP is buying. ADR-0351
decision 1 removed the full-GPU-era *hard* anti-affinity because it forbade single-node
packing; the soft form honours that reasoning rather than contradicting it.

Three constraints the CRDs imposed on the design, all verified live before writing:

- **`LLMInferenceService.spec.template` is a bare PodSpec with no `metadata`.** No custom label
  can be attached to the qwen/gpt-oss pods, and the CR's own labels (`zuno.io/managed-by`) are
  not propagated to the generated Deployment's pod template.
- Consequently **no label is common to all three predictor pods** except istio's
  (`security.istio.io/tlsMode`) and topology labels. A `topologySpreadConstraints` keyed on a
  shared selector — the more idiomatic tool — is simply unavailable, hence anti-affinity on
  the labels that do exist.
- **`kserve.io/component: workload` matches exactly the two LLM model pods cluster-wide.** The
  `router-scheduler` pods carry `app.kubernetes.io/component` instead and are not counted.

The embeddings term names qwen specifically rather than reusing `kserve.io/component: workload`:
once the two chat models spread, both nodes host one of them, so the broad selector would score
every node identically and steer nothing.

It also selects on `.Values.inferenceServiceName` (`qwen36-27b-instruct`), **not**
`.Values.servedModelName` (`qwen3.6-27b-instruct`). The first draft used the latter, which
matches no pod and would have degraded silently to no constraint at all — caught by rendering
the chart and diffing against the live pod labels, not by any schema check.

Stale comments corrected in the same pass: both `llminferenceservice-*.yaml` claimed the
`nodeSelector` was backed by "only Card A's managed MIG node advertises it". Both permanent
nodes advertise the slices since WP-083.

### 2. `c6cbda4` — sizing the pgBackRest repo host

`gitops/charts/postgresql/` gains `backups.repoHost.resources`, wired into
`postgrescluster.yaml` at `spec.backups.pgbackrest.repoHost.resources` (path confirmed with
`oc explain` first).

Measured at **30-second resolution**, which was the decisive choice: a full backup runs ~60s,
so a 5-minute `rate` smooths it away and reports 29m of CPU where the real peak is **181m**.

| | CPU | RAM |
|---|---|---|
| Idle (>99% of the time) | 2.5m | 39Mi |
| Diff backup, 203MB database | 181m | — |
| Diff backup, 769MB database | 27m | 140Mi |
| 48h RAM peak | — | 180Mi |

Chosen: requests `cpu 50m` / `memory 256Mi`, limits `cpu 1` / `memory 512Mi`.

Memory is requested **above** the peak rather than near the 39Mi average on purpose: memory is
incompressible and the kubelet ranks eviction candidates by usage-over-request, so an
average-sized request would make the backup itself the thing that evicts the pod. CPU is safe
to under-request because it throttles instead of killing. The CPU limit sits ~5x the measured
peak because pgBackRest is compression-bound and the peak tracks database size, which grew
from 203MB to 769MB in one day.

### 3. `ef21189` — disabling the unused `kserve.modelCache`

`DataScienceCluster.spec.components.kserve.modelCache` was `Managed` (140Gi, GPU-node selector)
with nothing using it: zero `LocalModelCache` / `LocalModelNode` CRs, `/var/lib/kserve` at 0
bytes on both GPU nodes, no InferenceService referencing it, and every served model pulling
from S3 into an `emptyDir`. `Removed` is the CRD's own default.

The cost was a self-sustaining two-writer fight over `kserve-localmodelnode-pv`, confirmed in
the kube-apiserver audit log (`oc adm node-logs <master> --path=kube-apiserver/audit.log`,
checked on **all three** masters — writes are spread across API servers):

```
redhat-ods-operator-controller-manager   re-applies the PV without spec.claimRef
kube-system:persistent-volume-binder     re-binds it to the PVC
```

~35 updates/min on one object, roughly a third returning **409**, driving the operator's
`kserve` controller to 36 reconciles/min (2/min after the fix; `gatewayconfig`, for scale, does
2). The operator's own write retriggers its own watch. Thanos
(`kube_persistentvolume_status_phase`) dated the flapping to nine minutes after the PV was
created, 38h before the fix — it predated all of WP-083's node work.

**A single `oc get` cannot diagnose this.** The PV reads `phase: Available` with an empty
`claimRef` while its PVC reads `Bound`, which looks like stale metadata. Polling it for 60s
shows it flapping.

Teardown took under 30s: DaemonSet `kserve-localmodelnode-agent`, Deployment
`kserve-localmodel-controller-manager`, the PVC and the PV all went, models untouched.

`cacheSize`/`nodeSelector` are kept commented out. Re-enabling needs them back *and* real
`LocalModelCache` CRs — and would reinstate the loop, which is upstream behaviour rather than
anything this repo controls.

## Live finding: the DataScienceCluster `/spec` is ArgoCD-ignored

The `modelCache` commit synced green and changed nothing. `zuno-openshift-ai-d1` declares:

```yaml
ignoreDifferences:
  - group: datasciencecluster.opendatahub.io
    kind: DataScienceCluster
    jsonPointers: ["/spec"]
```

No drift is detected, so auto-sync never fires, and the Application reports `Synced` at the new
revision. **The whole `dataScienceCluster.spec` block in
`gitops/charts/openshift-ai/values.yaml` is documentation, not enforcement** — every DSC change
needs `oc patch datasciencecluster zuno-dsc --type=merge`.

`syncOptions` does not include `RespectIgnoreDifferences=true`, so the ignore suppresses diff
*detection* only; a forced sync would still apply the full manifest, but it would also drag in
whatever else moved on `main`. A targeted `oc patch` is the safer mechanism.

This is the third instance of the same trap, after `zuno-machines-d0`'s `/spec/replicas` on
MachineSets and `zuno-kiali-d1`'s three `Kiali` subtrees. The failure mode is a false green:
`Synced` at your own SHA reads as proof the change landed.

## Operator actions remaining

1. **Replace `zuno-gpu-c-wnkhl`.** The machine was created before WP-083's `volumeSize: 250`
   reached the MachineSet template, so it came back on the old 149GB disk, and it has been
   cordoned since 14:17. `oc delete machine -n openshift-machine-api zuno-gpu-c-wnkhl`;
   `replicas=1` recreates it at 250GB, uncordoned, with the taint inherited from the template.
   Do **not** run `oc adm drain` — the machine-controller drains on its own and the node is
   already empty.
2. **Then** let the models chart sync. The pod-template change triggers a rolling update, which
   needs a surge slice; with one node at 3/3 slices there is none. Quota has room
   (`mig-2g.48gb` 1/2, `mig-1g.24gb` 2/3).

Why the disk replacement still matters once the models are spread: in steady state the split
leaves ~60GB on the smaller node, comfortable. The risk is the **failover cold start** — losing
one node puts all three models on the survivor, and the storage-initializer transiently doubles
occupancy while downloading. On a 149GB node that projects to `44.8 + 2 x 45.9 ~= 136GB`
against a `nodefs.available < 10%` eviction threshold of ~144.5GB used: ~6% margin, and
precisely the peak that already evicted a pod on this node. On 250GB it is ~46% of capacity.

## Live finding: a soft anti-affinity is only as good as the scheduling order

The predictors ended up **gpt-oss on node A, qwen + embeddings on node C** — not the
predicted "qwen alone on one node".

`preferredDuringSchedulingIgnoredDuringExecution` is evaluated once, at scheduling time,
against the pods already placed. During the rolling update the order was:

1. embeddings' new pod scheduled while the **old** qwen pod was still on node A, so it
   correctly avoided A and went to C;
2. qwen's new pod scheduled next, avoided the node holding the other LLM workload (A), and
   also went to C — landing on top of embeddings;
3. gpt-oss rolled last, avoided C (now holding qwen), and stayed on A.

Every term did exactly what it says. The embeddings term's *intent* — sit away from qwen —
still lost, because nothing re-evaluates it once qwen moves. `IgnoredDuringExecution` is not
a footnote; it is the whole contract.

The outcome is still a 2/1 split and still delivers the blast-radius reduction this WP is
for, so no change was made. Worth knowing before assuming a specific layout: **if a
particular pairing ever matters, it has to be enforced at eviction time (a descheduler
policy), not at scheduling time.**

## Live results (2026-08-26)

Replacement node `ip-10-18-67-65` (`zuno-gpu-c-cnhhz`, eu-west-2c) came up in 7 minutes:
Ready at 3m40s, `mig.config.state=success` at 7m, slices advertised 30s later.

| | node A `ip-10-18-15-25` | node C `ip-10-18-67-65` |
|---|---|---|
| Disk | 249GB | 249GB |
| Slices | 2x `1g` + 1x `2g` | 2x `1g` + 1x `2g` |
| Ephemeral used | 66.4GB (**25%**) | 77.6GB (**29%**) |
| Predictors | gpt-oss-20b | qwen + embeddings |

Both nodes now sit at roughly a quarter of capacity, against the 91% the three models
projected onto a 149GB node.

Warm completions, 200 tokens, from inside the mesh:

```
qwen3.6-27b-instruct   11.0s / 10.9s / 10.9s   18.2-18.4 tok/s
gpt-oss-20b             2.9s /  2.3s /  2.3s   61.1-85.9 tok/s
```

qwen's throughput is unchanged from before the move (18 tok/s), so the new node's slice
performs identically.

**The first request after a pod replacement is not representative.** It timed out at 90s;
the vLLM log shows why — Triton kernel JIT compilation (`_fused_post_conv_kernel`,
`_triton_mrope_forward`, `layer_norm_fwd_kernel`, ...) fires on the first inference of a cold
pod, and vLLM itself warns "consider extending warmup to cover this shape/config". Readiness
was already `True`. Any post-rollout smoke test must warm the pod first or it will report a
false failure.

`make d2 check models`, `make d0 check machines` and `make d3 test platform` (8/8) all pass.

## Verification checklist

| # | Check | Expected |
|---|---|---|
| 1 | `oc get nodes -l nvidia.com/gpu.present=true` | 2 nodes, AZ 2a + 2c, 249GB each, none `SchedulingDisabled` |
| 2 | `oc get pods -n zuno-ai-run -o wide` | qwen on one node, gpt-oss + embeddings on the other |
| 3 | `/proxy/stats/summary` on both nodes | cold-start peak <= 50% of capacity |
| 4 | `oc get inferenceservice -n zuno-ai-run` | `embeddings` `READY=True`, no `FailedCreate` |
| 5 | `make d2 check models` | assertions pass, `/v1/models` responds |
| 6 | 200-token completion on qwen **and** gpt-oss | under 15s, HTTPS on 8000 |
| 7 | `make d0 check machines` | passes, covers both GPU MachineSets |
| 8 | `make d3 test platform` | 8/8 |
| 9 | Cordon the qwen node, delete the pod | qwen reschedules onto the other node **despite** the anti-affinity |
| 10 | `oc get pv \| grep localmodel` | nothing |
| 11 | `pgbackrest info --stanza=db` on the repo host | `status: ok`, backup chain intact |

Check **9** is the only one that proves the property that matters. An anti-affinity mistakenly
written as `required` passes 1 through 8 without complaint and only reveals itself during a
real outage.

## Out of scope

- **`disruptionsAllowed: 0` PDBs on five single-replica workloads** (`agent-runtime`,
  `ai-gateway`, `mcp-gateway`, `zuno-auth/zuno`, `rag-service`). Every future `oc adm drain`
  blocks on each of them — this is what made WP-083's decommission a manual, pod-by-pod
  operation. Fixing it means two replicas or `maxUnavailable: 1`, but each service has to
  tolerate two instances (sessions, leases, writes). Its own WP.
- `zuno-gpu-burst-a` (replicas 0): `train-lora` has never been executed; keeping or retiring
  that MachineSet should be decided on a real run.
- `demo222-kpkqk-workergpu-eu-west-2a` stays declared at 0 — ADR-0351 decision 7's installer
  escape hatch.
- AZ-2a concentration: accepted risk, operator decision.
- ADR-0343's `neverInjectSelector` entries for the two localmodel workloads are inert since
  `ef21189` but left in place; its `kuberay-operator` entry still applies.

## Status updates

- `c6cbda4` and `ef21189` are live and verified: repo host `3/3 Running` with the new requests
  and its backup chain intact; `modelCache` torn down with the `kserve` reconcile rate down
  from 36/min to 2/min and the DSC back to `Ready=True`.
- The anti-affinity change is live. `zuno-gpu-c-wnkhl` was replaced by `zuno-gpu-c-cnhhz`
  (`ip-10-18-67-65`, 249GB) and the rolling update spread the predictors 2/1 across the two
  nodes. See `## Live results` — and `## Live finding` for why the split is not the one the
  plan predicted.
- Check #9 (cordon the qwen node, delete the pod, confirm it packs onto the survivor rather
  than going Pending) is **not yet run** — it needs a deliberate node cordon.
- `python3 platform/docs/check_docs.py` passes.
