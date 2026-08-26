# ADR-0351: Share RTX PRO 6000 GPUs via NVIDIA MIG with scale-from-zero burst capacity

- **Status:** Implemented (2026-08-26; amended same day by WP-083 - two permanent MIG nodes, see decisions 5 and 7)
- **Target:** v0.3
- **Date:** 2026-08-17
- **Decision owners:** Zuno Demo architecture team

> **Amended in place 2026-08-26 (WP-083).** This record was edited rather
> than superseded, by explicit operator decision. That departs from the
> immutability rule this repo states in [README.md](README.md) ("ADRs are
> immutable decision records ... a new ADR supersedes the previous record
> instead of rewriting history"), and the departure is recorded here rather
> than left implicit. Amended parts: the Context goal, decisions 5 and 7,
> and the cost analysis. Each carries an inline `**Amended 2026-08-26:**`
> note quoting what the original text said, so the superseded reasoning is
> still readable. Nothing else was rewritten.

## Context

The demo222 cluster reached a topology where every GPU decision made for
the earlier 3x-L4 era stopped matching reality at once:

- One GPU node remained: a `g7e.2xlarge` (8 vCPU / 64GiB, one NVIDIA RTX
  PRO 6000 Blackwell Server Edition, 96GB VRAM) in `eu-west-2a`. Three
  inference workloads each requested a whole `nvidia.com/gpu`
  (`qwen25-7b-instruct`, `embeddings`, the ADR-0201 MaaS
  `LLMInferenceService`), so two of the three sat Pending, and their
  standing CPU requests (8.5 vCPU) exceeded the node's ~7.5 allocatable
  vCPU even before MIG entered the picture.
- The chat/embeddings pair carried a *hard* hostname anti-affinity written
  for the one-full-GPU-per-node world - it forbids the single-node packing
  a partitioned GPU makes desirable.
- LoRA training (ADR-0301/0302, WP-34) had no schedulable GPU at all, and
  its KFP pipeline declared **no GPU resource anyway** - run for real it
  would have silently fallen back to CPU
  (`torch.cuda.is_available()` guard in `components/mlops`).
- An out-of-repo attempt at machine automation existed: five
  `startx-cluster-machine-*` ArgoCD Applications deployed straight from
  `startxfr/helm-repository@devel` with `cluster.id=def7f838-...` - not
  this cluster's infra id (`demo222-kpkqk`). Every AWS tag filter and the
  IAM instance profile derive from that id, so all nine machinesets'
  machines Failed with "no security group found", and no
  `ClusterAutoscaler` existed so their `MachineAutoscaler`s (min 1) were
  inert.

The operator's goals: share the 96GB GPU across **all** GPU workloads
(inference and training), keep exactly one permanent GPU node, and add a
second node only for AZ failure or punctual training bursts - cost first.

> **Amended 2026-08-26 (WP-083):** the "exactly one permanent GPU node"
> goal no longer holds. It was never actually met in practice - the IPI
> `workergpu` node ran at replicas 1 throughout (decision 7 assumed zero),
> so the cluster always had two permanent GPU nodes; the second was simply
> idle at 0% GPU utilisation rather than useful. WP-083 makes the second
> node deliberate and useful instead of accidental and wasted. The
> cost-first framing survives: see the amended cost analysis below, where
> the real delta is one instance size step, not a second node.

## Decision

1. **MIG, `mixed` strategy, `all-balanced` partition on the permanent
   node.** The RTX PRO 6000 Blackwell is split 2x `1g.24gb` + 1x
   `2g.48gb` (its `default-mig-parted-config` profile, device
   `0x2BB510DE`). Slice allocation: qwen chat predictor ->
   `nvidia.com/mig-2g.48gb` (double its original L4's memory - KV-cache
   headroom), MaaS backend and embeddings -> one `nvidia.com/mig-1g.24gb`
   each (the same 24GB envelope each targeted on an L4). The
   full-GPU-era hard anti-affinity between chat and embeddings is
   removed. The strategy must be `mixed`, not the CSV default `single`:
   only `mixed` advertises `nvidia.com/mig-*` slices and whole
   `nvidia.com/gpu` units side by side, which decision 4 requires.
2. **Permanent node resized to `g7e.4xlarge`** (16 vCPU / 128GiB, same
   single 96GB GPU), kept in `eu-west-2a` - the qwen model PVC (gp3-csi,
   RWO, single-AZ) is zone-bound there. The GPU dominates the instance
   price, so the step up is ~19% (us-east-1 on-demand indicative:
   ~$3.36/h -> ~$4.00/h) for double the CPU/RAM - the cheaper fix
   (shrinking the vLLM pods' CPU requests) would have left zero headroom
   for sidecars, daemonsets and the MaaS router-scheduler on a shared
   node.
3. **Machine management enters this repo**: `gitops/charts/machines`
   (vendored startx `cluster-machine` 21.3.277, the ADR-0312 wrapper
   pattern) + `gitops/apps/machines` + `ansible/roles/machines`, a Day 0
   component ordered before `nfd`/`nvidia_gpu` (ADR-0056). All AWS
   parameters are the live-verified ones: infra id `demo222-kpkqk`,
   security group `demo222-kpkqk-node` (no `{id}-worker-sg` exists on
   OCP 4.16+ CAPA-installer clusters - the subchart's default is wrong
   here), subnets `demo222-kpkqk-subnet-private-eu-west-2{a,c}`, the
   IPI machinesets' own RHCOS AMI. The five mis-parameterized
   `startx-cluster-machine-*` Applications are retired (see Operational
   considerations for the finalizer hazard).
4. **Burst training capacity scales from zero.** A tainted
   (`zuno.io/gpu-burst=true:NoSchedule`) `g7e.2xlarge` MachineSet
   (`zuno-gpu-burst-a`) sits at replicas 0 with a MachineAutoscaler
   (min 0 / max 1) and the cluster's first `ClusterAutoscaler`
   (scale-down enabled, `unneededTime: 10m`). **Verified constraint**:
   the ClusterAutoscaler's GPU scale-from-zero support rides on the
   `capacity.cluster-autoscaler.kubernetes.io/gpu-count`/`gpu-type`
   annotations (auto-propagated by the cluster-autoscaler-operator) and
   only understands plain `nvidia.com/gpu` - `nvidia.com/mig-*` capacity
   is invisible to it. The burst node therefore runs MIG-**disabled**
   (label `all-disabled`) and the train-lora KFP task requests a whole
   `nvidia.com/gpu: 1` (+ the taint's toleration): a submitted training
   run wakes the node, trains on the full 96GB, and the node is
   reclaimed ~10 minutes after the stage completes. The GPU-operator
   daemonsets get a matching toleration via the ClusterPolicy overlay
   (decision 6) - without it the driver never starts on the tainted node.
5. **AZ failover is a one-command runbook, not an autoscaler.** A
   `zuno-gpu-c` MachineSet (same g7e.4xlarge + `all-balanced` label)
   sits at replicas 0 in `eu-west-2c` - the only other zone offering
   g7e at all (verified `describe-instance-type-offerings`; `eu-west-2b`
   does not have the instance family, which also proves the experiment's
   `worker-gpubig-b` could never have provisioned). The same
   CAS-cannot-see-MIG constraint from decision 4 makes automatic
   failover impossible for MIG-slice pods; losing zone a is rare enough
   that `oc scale machineset zuno-gpu-c --replicas=1` plus the qwen PVC
   recreation (zone-bound storage) is the documented recovery path
   (`gitops/charts/machines/README.md`).

   > **Amended 2026-08-26 (WP-083): `zuno-gpu-c` runs at replicas 1 as the
   > second permanent inference node.** The original text above ("sits at
   > replicas 0 ... `oc scale machineset zuno-gpu-c --replicas=1` ... is the
   > documented recovery path") described a design that could not work, for
   > the reason this same decision states two sentences earlier: the
   > ClusterAutoscaler only sees plain `nvidia.com/gpu`, never
   > `nvidia.com/mig-*`. A Pending MIG-slice pod could therefore never have
   > summoned this MachineSet, and nothing else would have noticed zone a
   > was gone. A standby that only a human can trigger, during an outage,
   > is not failover capacity - a second MIG node has to be standing
   > *before* it is needed. It now is, in `eu-west-2c`, and the two
   > inference nodes are symmetric `all-balanced` g7e.4xlarge: either one
   > alone holds all three model workloads (1x `2g.48gb` + 2x `1g.24gb`
   > = 3/3 slices), which is what makes single-node loss survivable.
   >
   > Two parts of the original recovery path are also obsolete: the qwen
   > model PVC no longer exists (ADR-0521 made every served model S3-only),
   > and `oc scale` is still required to change replicas - not because it
   > is a runbook, but because `gitops/apps/machines/application-d0.yaml`
   > sets `ignoreDifferences` on MachineSet `/spec/replicas`, so a value
   > committed to `values.yaml` is deliberately never pushed to the live
   > object. Git and cluster can silently diverge on replicas by design.
6. **The ClusterPolicy MIG strategy is an ansible overlay, not a Git
   manifest.** ADR-0312/ADR-0047's discovery design stands: the spec is
   still read from the installed CSV's `alm-examples` at deploy time;
   `ansible/roles/nvidia_gpu` now `combine`s `{mig: {strategy: mixed},
   daemonsets: {tolerations: [nvidia.com/gpu, zuno.io/gpu-burst]}}` into
   it before serializing. Day-2 changes go through a role re-run -
   `zuno-nvidia-gpu-d1`'s selfHeal reverts live `oc patch`es.
7. **The IPI `demo222-kpkqk-workergpu-*` machinesets stay live at
   replicas 0**, unmanaged by this repo: installer-native artifacts,
   harmless at zero, and a manual escape hatch if the `machines` chart
   ever has to be torn down.

   > **Amended 2026-08-26 (WP-083): this decision is restored, not
   > reversed.** The live cluster had drifted from it -
   > `demo222-kpkqk-workergpu-eu-west-2a` was running at replicas 1, first
   > because ADR-0412 deliberately borrowed its idle full GPU for
   > gpt-oss-20b, then still after ADR-0414 retired that exception. The
   > result was a `g7e.2xlarge` billed 24/7 whose entire 96GB RTX PRO 6000
   > sat at 0% utilisation and 0 MiB allocated: unusable for MIG workloads
   > because, being outside `gitops/charts/machines`, no
   > `nvidia.com/mig.config` label can be pushed to it declaratively, and
   > any partition applied by hand would be lost on node replacement.
   > WP-083 scales it back to 0 and moves that capacity to `zuno-gpu-c`
   > (decision 5). The machinesets stay declared at zero, so the escape
   > hatch this decision describes - which `ansible/roles/machines/README.md`
   > depends on for the chart-teardown path - is intact and is now actually
   > true rather than aspirational.
   >
   > Note this overtakes ADR-0414's header claim to amend decision 7
   > ("the unmanaged IPI workergpu machinesets no longer stay unmanaged").
   > ADR-0414 is still `Proposed` and proposed adopting the node into
   > `machines` management; WP-083 retires it instead. See ADR-0414's own
   > amendment note.

### Cost analysis (us-east-1 on-demand, indicative)

| Item | $/h | $/month (~730h) |
|---|---|---|
| Permanent g7e.4xlarge (was g7e.2xlarge) | ~4.00 (was ~3.36) | ~2,920 (+~470) |
| Second permanent GPU node (avoided) | ~3.36+ | **~2,450+ avoided** |
| Burst g7e.2xlarge (scale-from-zero) | ~3.36 while training runs | ~0 at rest |
| Failover g7e.4xlarge (replicas 0) | 0 until scaled | 0 |

One partitioned node runs what previously needed three L4 nodes; the only
standing cost increase is the 2xlarge->4xlarge step, and training/failover
capacity bills only when actually used.

> **Amended 2026-08-26 (WP-083).** Two rows above are wrong as written.
> "Second permanent GPU node (avoided) | **~2,450+ avoided**" was never
> avoided - the IPI `workergpu` `g7e.2xlarge` was billed at that rate the
> whole time (decision 7's amendment), so the saving was booked against a
> node that was in fact running. "Failover g7e.4xlarge (replicas 0) | 0"
> now bills, because that node is `zuno-gpu-c` at replicas 1.
>
> The correct standing cost of WP-083 is a swap, not an addition:
>
> | Item | $/h | $/month (~730h) |
> |---|---|---|
> | `zuno-gpu-c` g7e.4xlarge, replicas 1 (was 0) | ~4.00 | ~2,920 |
> | IPI `workergpu` g7e.2xlarge, replicas 0 (was 1) | -3.36 | -~2,450 |
> | **Net delta** | **~+0.64** | **~+467** |
>
> ~$467/month buys: the second 96GB card moving from 0% to serving
> gpt-oss-20b, AZ redundancy (2a + 2c, where both GPU nodes previously sat
> in 2a), declarative MIG management, and a vCPU/VRAM ratio that can
> actually drive a 3-slice partition - the `g7e.2xlarge` had ~4.5 cores
> free for 3 slices, so one model pod fit and 96GB was bought to use 24GB.
> Same indicative us-east-1 on-demand basis as the table above.

### Relationship to ADR-0211

ADR-0211 records, verbatim: *"This repo has no AWS provisioning
automation at all - no Terraform, no CloudFormation, no
`amazon.aws`/`community.aws` Ansible collections"* and decided that the
repo *"shouldn't gain a new category of it for a single credential"*.
This ADR deliberately scopes - and partially supersedes - that stance:
MachineSet, MachineAutoscaler and ClusterAutoscaler are **cluster-native
Machine API CRs delivered through the existing GitOps mechanism**, exactly
like every other CR this repo manages. The AWS API calls are made by the
cluster's own machine-api and cloud-credential operators with credentials
the IPI installation already holds; no Terraform, no AWS Ansible
collection, no new IAM identity, and no cloud API access from ansible
enter the repo. ADR-0211's prohibition continues to apply to
*out-of-cluster* AWS tooling.

## Consequences

- All three inference workloads become co-resident on one node; a node
  outage (or the AZ-failover window) now takes down all local inference
  at once instead of one model. Accepted: this is a demo platform, the
  SLO path (ADR-0102) measures the BFF, and the failover runbook is one
  command plus a ~15GB model re-download.
- Every future GPU workload must choose a resource shape: a MIG slice
  (inference-class, permanent node) or a whole GPU (burst node,
  training-class). The `zuno-ai-run` quota enforces the split by pinning
  `requests.nvidia.com/gpu` to 0 there.
- The `machines` chart owns GPU capacity as code - "add a GPU node" is
  now a values edit + sync, not an undocumented console action. The
  ArgoCD Application must keep ignoring MachineSet `/spec/replicas`
  (with `RespectIgnoreDifferences=true`) or selfHeal would fight both
  the autoscaler and the failover runbook.
- Kueue still has no GPU `ResourceFlavor` (ADR-0321's noted gap) -
  queued/quota'd training beyond the single burst node remains future
  work and is unblocked, not delivered, by this ADR.

## Security considerations

No new credentials, IAM identities or cloud tooling (see the ADR-0211
scoping above). The burst taint/toleration pair is a scheduling contract,
not a security boundary - workload isolation continues to rest on
namespaces, quotas and NetworkPolicies (ADR-0329/ADR-0331). MIG's
hardware partitioning adds memory/fault isolation between the co-resident
inference workloads that plain time-sliced sharing would not provide. The
`zuno-ai-run` GPU quota refusing whole-GPU requests at admission prevents
a misconfigured inference workload from silently waking (and billing) the
burst node.

## Operational considerations

- **Rollout order matters**: flip the ClusterPolicy to `mixed` first (a
  no-op for a node with no `mig.config` label - the running node keeps
  advertising `nvidia.com/gpu: 1`), then create the new capacity; the
  permanent node boots empty, is partitioned by mig-manager before any
  workload lands, and inference migrates by resource rename. A node is
  never repartitioned while busy - MIG layout changes mean node
  replacement.
- **Retiring the startx machine apps has a destructive edge**: all five
  carry the ArgoCD resources-finalizer.
  `startx-cluster-machine-configpool` owns the live `worker`
  MachineConfigPool and `-config` owns a master KubeletConfig -
  cascade-deleting those two would delete the worker MCP (catastrophic)
  and roll master reboots. Their finalizers are stripped first (orphaning
  those objects in place); the other three (`-set`, `-autoscaler`,
  `-health`) cascade-delete safely - their broken machinesets' 3 Failed
  machines have no AWS instances behind them.
- The subchart quirks that bit the experiment are documented in
  `gitops/charts/machines/README.md`: `minReplicas` must be the string
  `"0"` (Helm-falsy integer 0 silently becomes 1), one security group
  per machineset, single-AZ subnets by tag name.
- The qwen model PVC stays the zone anchor: any permanent-node zone
  change (including failover) requires deleting/recreating the download
  Job + PVC (WaitForFirstConsumer rebinds it beside the new node).

## Acceptance criteria

- The permanent node advertises `nvidia.com/mig-1g.24gb: 2` and
  `nvidia.com/mig-2g.48gb: 1` allocatable; qwen chat, embeddings and the
  MaaS backend are Running co-resident on it and answer their smoke
  tests (chat completion, embedding call, MaaS route).
- A submitted train-lora pipeline run scales `zuno-gpu-burst-a` 0->1
  unattended, trains on the burst node's whole GPU, and the node is
  removed within ~15 minutes of the stage completing.
- `zuno-gpu-c` provisions a MIG-partitioned node when scaled to 1 by
  hand (failover rehearsal), or at minimum the machineset is confirmed
  schedulable-parameter-correct.
- The five `startx-cluster-machine-*` Applications and their broken
  machinesets/autoscalers are gone; the `worker` MachineConfigPool
  survived their removal untouched.
- `make check` passes (day-0 role/Makefile/docs consistency).

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md)
- [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md)
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md)
- [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md)
- [ADR-0211](0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md)
- [ADR-0301](0301-introduce-lora-and-peft-model-customization.md)
- [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md)
- [ADR-0312](0312-route-operator-installs-through-argocd-applications.md)
- [ADR-0321](0321-delegate-kueue-lifecycle-to-the-red-hat-build-of-kueue-operator.md)
- [ADR-0329](0329-consolidate-agent-workloads-into-the-shared-zuno-ai-run-namespace.md)
- [ADR-0343](0343-complete-the-maas-and-ray-prerequisites-on-the-datasciencecluster.md)
