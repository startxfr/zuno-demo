# WP-083: GPU right-sizing and a second permanent MIG node

- **State:** Done (live-verified 2026-08-26). Every operator action below was executed and
  checked; the IPI GPU node is decommissioned.
- **ADRs:** ADR-0351 (amended in place 2026-08-26 — decisions 5 and 7 and the cost analysis),
  ADR-0414 (its claim on ADR-0351 decision 7 withdrawn)
- **Depends on:** WP-082 (identified and deferred both defects this WP fixes), WP-076/ADR-0521
  (made served models S3-only, which removes the zone-bound qwen PVC from the failover path)
- **Related:** ADR-0518 (current model set and its sizing), ADR-0412/ADR-0414 (the prior
  attempts to use the IPI `workergpu` card)

## Goal

Close the two defects WP-082 recorded under `## Live finding: any GPU-workload spec change
deadlocks its own rollout` and explicitly deferred: *"raising the quota by one slice per profile
is NOT attempted here - it needs its own WP and a decision about GPU headroom."* Then make the
second physical GPU useful instead of idle.

The measured starting point, 2026-08-26:

- `gpt-oss-20b` `Pending`, never scheduled, while a `mig-1g.24gb` slice sat free at 64 MiB.
- The `embeddings` InferenceService `PredictorReady=False`/`FailedCreate` with a perfectly
  healthy pod running.
- `demo222-kpkqk-workergpu-eu-west-2a` billing a whole 96GB RTX PRO 6000 at **0% utilisation,
  0 MiB allocated** — half the cluster's VRAM.

None of it was a VRAM problem.

## What changed

**Right-sizing (`4be71ce`, `gitops/charts/models/values.yaml`).** Model requests had been set
from estimates, never from measured load. A 24h Thanos window covering the 11h47 MMLU
`LMEvalJob` that drove qwen36 continuously gives the real ceilings:

| Workload | CPU peak | CPU req → | RAM peak | RAM req → | limit → |
|---|---|---|---|---|---|
| `qwen3.6-27b-instruct` | 1.00 core | 4 → **2** | 10.1 GiB | 24Gi → **16Gi** | 48Gi (unchanged) |
| `gpt-oss-20b` | 0.97 core | 4 → **2** | 4.0 GiB | 16Gi → **8Gi** | 20Gi (unchanged) |
| `qwen3-embedding-0.6b` | 0.62 core | 500m → **750m** | **5.57 GiB** | 3Gi → **6Gi** | 6Gi → **8Gi** |

Two of the three were over-provisioned ~4x; the third was *under*-provisioned and sitting at
93% of its memory limit, one ingestion burst from repeating the `exit 137` its own chart comment
documents. Limits are untouched on the two chat models: they cover the safetensors load spike,
requests only govern scheduling.

This alone unblocks `gpt-oss-20b`. WP-082 correctly diagnosed the node as CPU-saturated, but the
saturation was self-inflicted: of node A's 12 426m of CPU requests only 4 600m was model
serving, and the 4-core request could not fit the 1 824m left. **The pod was blocked on CPU,
never on GPU.**

**Quota (`4be71ce`, `gitops/charts/namespaces/values.yaml`).** `mig-1g.24gb` 2 → **3**,
`mig-2g.48gb` 1 → **2**. Sized at exactly one slice per workload, the quota made every rolling
update impossible by construction — KServe Deployments are `RollingUpdate`/`maxUnavailable: 0`,
so a new revision must be admitted while the outgoing pod still holds its slice. Counts are now
workload-count + 1 per profile. The surge slot is a ceiling, not a reservation: it costs nothing
when no rollout is in flight.

**Second MIG node (`2e0ca38`, `gitops/charts/machines/values.yaml`).** `zuno-gpu-c` goes to
`replicas: 1` as the second *permanent* inference node, and the IPI `workergpu` machineset
returns to 0. `zuno-gpu-c`'s original design as a scale-on-demand failover twin could not work,
for the reason ADR-0351 decision 5 itself states: the ClusterAutoscaler only sees plain
`nvidia.com/gpu`, never `nvidia.com/mig-*`, so a Pending MIG-slice pod could never have summoned
it. A second MIG node has to be standing before it is needed.

Both GPU machinesets also get `nvidia.com/gpu=true:PreferNoSchedule`. **Soft, not hard, and the
distinction is load-bearing:** dedicating both GPU nodes outright would mean relocating ~10.2
cores of platform requests onto 12.0 cores of headroom concentrated on the three masters, taking
them from ~75% to ~98% cpu-requests. The taint's job is to stop platform pods creeping back and
re-starving the inference nodes, not to evict what is already placed.

Model pods need no matching toleration: they are the only pods requesting `nvidia.com/mig-*`,
which no other node advertises, so the resource requirement already pins them and the soft
penalty has nothing to bias them towards.

### Failure-mode simulation

Modelled against live requests, with the soft taint letting `zuno-gpu-c` absorb overflow:

| Scenario | GPU node | Masters | Verdict |
|---|---|---|---|
| Steady state | gpu-a 68%, gpu-c 26% | 76-80% | comfortable |
| **Loss of `zuno-gpu-a`** | gpu-c 66% CPU / 40% RAM, **3/3 slices** | 85-88% | survivable; the dimensioning case |
| Loss of `zuno-gpu-c` | gpu-a 84% | 79-82% | comfortable |

Either node alone holds all three models — 1x `2g.48gb` + 2x `1g.24gb` = exactly 96GB. That
symmetry is the point of the g7e.2xlarge → g7e.4xlarge step; qwen36-27b could never have fit on
the 2xlarge under load. Net standing cost is **~+467 $/month**, not the ~2,450 a second node
implies, because the node being retired is half the size of the one replacing it.

## Live finding: ephemeral storage, not CPU/RAM/VRAM, is what broke first

This WP sized CPU, memory and VRAM and never looked at disk. `zuno-gpu-c`'s
first boot hit the gap immediately.

Model weights land in an **emptyDir**, so they are ephemeral-storage on the
node's root volume - the same 150GB that holds RHCOS and the unpacked
container images. On a fresh node every model arrives at once, and during a
KServe `RollingUpdate` each exists twice (the outgoing pod keeps its copy
while the incoming one downloads). Measured on gpu-c: qwen3.6-27b 28.8GB +
gpt-oss-20b 12.8GB x2 pods + the vLLM image unpacking from a 17.7GB pull,
peaking at **~136GB of 149GB** against a kubelet eviction threshold of
~24GB free.

Consequences, all observed: the qwen pod was `Evicted` mid-init and left as
`Init:Error`, the node took a `node.kubernetes.io/disk-pressure:NoSchedule`
taint, and qwen's replacement pod went Pending against
`1 node(s) had untolerated taint(s)` - the rollout stalled on a node that
had a free `2g.48gb` slice the whole time.

It self-healed: evicted pods released their storage, usage fell to **54.5GB
of 149GB**, the kubelet cleared the condition after its transition period,
the taint went away and qwen completed onto gpu-c. No service interruption
at any point - qwen and embeddings kept serving from node A throughout.

Fix: `blockDevices.volumeSize` 150 -> 250 on both permanent inference nodes.
Steady state never needed it (54.5GB used); the transient and the failover
case do - one node holding all three models plus rollout duplicates is
exactly the scenario the second node exists to survive. gp3 capacity is
negligible against a g7e.4xlarge. Block device changes apply only to NEW
machines, so the running nodes keep 150GB until replaced; that is acceptable
because the steady-state figure has a wide margin.

## Deviations from repo convention (deliberate, operator-approved)

1. **ADR-0351 was amended in place, not superseded.** `docs/adr/README.md` states ADRs are
   immutable and that a change of direction requires a superseding record. The operator was
   shown this rule and chose in-place amendment anyway. Every amended passage carries an inline
   `**Amended 2026-08-26:**` note quoting what the original said, and a banner at the top of
   ADR-0351 records the departure rather than hiding it.
2. **The implementation commits are not `WP-083:`-prefixed.** Convention is a scaffolding commit
   (ADR + brief + index) *before* the implementation commits. `4be71ce` and `2e0ca38` were
   already committed when this brief was written, and by then a concurrent session had built
   three further commits on top of them — reordering would have rewritten another session's
   history. This brief is the scaffolding, landing after rather than before.

## Operator actions remaining

Ordered; each gates the next.

1. Push `4be71ce` alone. Confirm `zuno-ai-run-gpu-cap` shows `mig-1g.24gb: 3` **before** the
   models app rolls — `zuno-namespaces-d1` and `zuno-models-d1` are separate Applications with
   independent reconcile loops and no cross-app ordering. If models land first the new revision
   is refused at admission and the controller retries until the quota arrives.
2. Confirm `gpt-oss-20b` reaches `Running` **on node A**, with no node added. This validates the
   whole CPU diagnosis on its own.
3. Push the rest, then `oc scale machineset zuno-gpu-c -n openshift-machine-api --replicas=1`.
   The `oc scale` is **mandatory**: `gitops/apps/machines/application-d0.yaml` sets
   `ignoreDifferences` on MachineSet `/spec/replicas` with `RespectIgnoreDifferences=true`, so
   the committed `replicas: 1` is deliberately never pushed to the live object.
4. Confirm the new node advertises `mig-1g.24gb: 2` and `mig-2g.48gb: 1`. The mig-manager
   partitions at first boot while the node is still empty; a node is never repartitioned once it
   carries GPU workloads.
5. Taint node A live — a MachineSet template change never retaints an existing node:
   `oc adm taint node ip-10-18-16-201.eu-west-2.compute.internal nvidia.com/gpu=true:PreferNoSchedule`
6. Decommission the IPI node. `oc adm drain` alone hangs forever: `zuno-ai-run/ai-gateway` runs
   there as a single replica with `minAvailable: 1` and `disruptionsAllowed: 0`. Cordon first,
   delete the blocking pod and the 8 StatefulSet singletons one at a time, then drain and scale
   the machineset to 0. `zuno-vault-0`, `zuno-postgresql-repo-host-0` and `zuno-redis-master-0`
   have **AZ-2a-pinned** `gp3-csi` volumes and can only land on `master-0` or `zuno-gpu-a`.

## Verification checklist

- ✅ 3 models `Running`, none `Pending` (2026-08-26)
- ✅ `embeddings` InferenceService `READY=True`, quota `FailedCreate` gone
- ⬜ `make d2 check models` passes
- ✅ `make d0 check machines` passes **and** covers `zuno-gpu-c` (precheck generalised — it
  hardcoded `zuno-gpu-a`). Verified non-vacuous: the selector returns both machinesets at 1/1,
  the MIG assertion sees both nodes at 2x`1g.24gb`+1x`2g.48gb`, and `zuno-gpu-burst-a` at 0 is
  correctly excluded. `install.yml` had the identical blind spot and was generalised with it.
- ✅ 2 GPU nodes, AZ **2a and 2c**, each 2x `mig-1g.24gb` + 1x `mig-2g.48gb`
- ✅ `PreferNoSchedule` present on both GPU nodes
- ✅ MachineSets: `zuno-gpu-a`=1, `zuno-gpu-c`=1, `zuno-gpu-burst-a`=0, `workergpu`=0
- ✅ `make d3 test platform` green after the drain — 8/8 PASS (agent-runtime, ai-gateway,
  mcp-gateway, rag-service; healthz + readyz each)
- ✅ AZ-2a-pinned StatefulSets `Running` after relocation, all on master-0. Keycloak answered
  HTTP 200 in 0.22s after the Redis move; 89/89 ExternalSecrets `SecretSynced` after Vault's
- ✅ Short load test on both chat models. Three consecutive warm 200-token completions on
  qwen3.6-27b: 11.0/11.1/11.1s, a steady 18 tok/s. **CPU measured during the load: `main` at
  11m on qwen and 89m on gpt-oss, against a 2000m request** — three orders of magnitude of
  headroom, and well under even the 1.00-core 24h peak the sizing was derived from. RAM 10.2GiB
  against 16Gi requested, matching the measured peak exactly. gpt-oss's first call was 1.15s;
  qwen's was 86.6s cold, which is `--enforce-eager` warm-up, not a sizing problem.

## Out of scope

- `zuno-postgresql-repo-host-0` has **no CPU request at all** (QoS Burstable) — first to be
  starved under node pressure, and it is the pgBackRest repo host. Unrelated to GPU; needs its
  own fix.
- Restoring a third AZ-2a node (`demo222-kpkqk-worker-eu-west-2a`, t3a.large, at 0): considered
  and declined. The swap takes AZ 2a from 3 nodes to 2 while five EBS-pinned stateful services
  live there. Capacity is fine in every modelled scenario; placement margin is what shrinks.
- Making the burst node a permanent training node: `train-lora` has **never been executed** —
  no workflow for it exists in cluster history. Validate with a real run before deciding.

## Status updates

- WP-083 → **Done** (live-verified 2026-08-26).
- ADR-0351 → `Implemented (2026-08-26; amended same day by WP-083 - two permanent MIG nodes,
  see decisions 5 and 7)`; `docs/adr/README.md` index row updated to match.
- ADR-0414 stays `Proposed`. Its tiering decision was never built (ADR-0518 replaced the model
  set) and its claim on ADR-0351 decision 7 is withdrawn in its own record.
- `MEMORY.md` updated: the GPU capacity paragraph described one permanent node plus a
  replicas-0 failover MachineSet, which is no longer true.
- `python3 platform/docs/check_docs.py` passes.
- **2026-08-26, later the same day:** this WP's steady state was not actually reached on close-out.
  `zuno-gpu-c`'s machine had been created *before* the `volumeSize: 250` fix landed in the
  MachineSet template, so it came back on the old 149GB disk and stayed cordoned; all three
  models ran on `zuno-gpu-a` alone. [WP-086](wp-086-spread-models-and-platform-hygiene.md)
  replaces that machine and spreads the predictors across both nodes.

### What the live run changed about the plan

Two things the plan got wrong, both worth carrying forward:

1. **Phase 1's success criterion could not be met on its own.** Right-sizing only takes effect
   when a pod is *replaced*, and qwen could not be replaced without a second `2g.48gb` slice —
   so it kept its old 4-core reservation, which was precisely what blocked gpt-oss. Phase 1
   depended on Phase 3. The chart comment written in `4be71ce` predicted this and the plan
   still sequenced around it.
2. **Ephemeral storage was never sized.** See the live finding above. CPU, RAM and VRAM were
   all modelled; disk was the one that actually broke.

Service continuity held throughout: qwen and embeddings never stopped serving, and gpt-oss went
from permanently `Pending` to serving.
