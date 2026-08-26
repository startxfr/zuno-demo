# machines

GPU capacity for the demo cluster (ADR-0351), as a thin wrapper around the
startx `cluster-machine` chart (vendored Helm dependency, same pattern as
`gitops/charts/nvidia-gpu` -> `cluster-gpu`). One ArgoCD Application uses it:
`zuno-machines-d0` (`gitops/apps/machines/application-d0.yaml`) flips the
`machineSet` / `machineAutoscaler` / `cluster.autoscaler` toggles that stay
false in `values.yaml`; `-d1` is a `noop` placeholder.

## What it renders

| Object | Purpose |
|---|---|
| MachineSet `zuno-gpu-a` (replicas 1) | Permanent inference node: g7e.4xlarge, eu-west-2a, MIG `all-balanced` (2x 24GB + 1x 48GB slices) |
| MachineSet `zuno-gpu-c` (replicas 1) | Second permanent inference node: g7e.4xlarge, eu-west-2c, MIG `all-balanced` - symmetric with `zuno-gpu-a` (WP-083; replicas set by hand, see below) |
| MachineSet `zuno-gpu-burst-a` (replicas 0) | Burst training node: g7e.2xlarge, MIG disabled (whole 96GB `nvidia.com/gpu`), tainted `zuno.io/gpu-burst=true:NoSchedule` |
| MachineAutoscaler `zuno-gpu-burst-a` (min 0 / max 1) | Scale-from-zero for the burst set |
| ClusterAutoscaler `default` | Cluster singleton; scale-down enabled (`unneededTime: 10m`) so the burst node disappears after training |

`nvidia.com/mig.config` node labels are acted on by the GPU Operator's
mig-manager at first boot, while the node is still empty - a node is never
repartitioned while it has GPU workloads. The `mixed` MIG strategy (and the
burst-taint toleration for the NVIDIA daemonsets) comes from
`ansible/roles/nvidia_gpu`'s ClusterPolicy spec overlay, not from this chart.

## Design constraints (all verified live 2026-08-17)

- **ClusterAutoscaler cannot scale from zero for `nvidia.com/mig-*`.** Its
  GPU scale-from-zero support rides on the
  `capacity.cluster-autoscaler.kubernetes.io/gpu-count`/`gpu-type`
  annotations (auto-propagated by the cluster-autoscaler-operator once a
  MachineAutoscaler targets a set), and those only speak plain
  `nvidia.com/gpu`. Hence the split: the burst set advertises a whole GPU
  (automatic 0->1 for training), the failover set (MIG slices) is manual.
- **`minReplicas` must be the string `"0"`** in `values.yaml`: the subchart
  renders `{{ .minReplicas | default 1 }}` and an integer 0 is falsy in
  Helm - it silently becomes a permanently-on node. The string survives
  `default` and renders as integer 0 (test-rendered).
- **The subchart renders exactly one security group per machineset.** This
  cluster's workers normally carry two (`demo222-kpkqk-node` +
  `demo222-kpkqk-lb`); the `-lb` SG only carries API-LB ingress
  (6443/22623), so worker nodes ride on `-node` alone. There is no
  `{id}-worker-sg` (the subchart's default) on OCP 4.16+ CAPA-installer
  clusters - every group sets `securityGroupName`/`subnet_name` explicitly.
- **No eu-west-2b group anywhere**: AWS does not offer g7e in that zone
  (`aws ec2 describe-instance-type-offerings`, 2026-08-17).
- **ArgoCD must not own `spec.replicas`**: `application-d0.yaml` carries
  `ignoreDifferences` on MachineSet `/spec/replicas` plus
  `RespectIgnoreDifferences=true`, otherwise selfHeal would revert both the
  autoscaler's burst scale-up and the failover runbook's manual scale.

## Losing a GPU node (WP-083: no runbook needed)

Both inference nodes are permanent and symmetric, so node loss needs no
manual step. Either `all-balanced` card alone holds the full model set -
1x `2g.48gb` + 2x `1g.24gb`, exactly 96GB - so the survivor absorbs the
three predictors on its own and the pods reschedule unaided.

This replaces the AZ-failover runbook that lived here. That runbook could
never have worked as written: it assumed a Pending MIG-slice pod would
signal the outage, but the ClusterAutoscaler only sees plain
`nvidia.com/gpu` (see Design constraints above), so nothing would have
raised the alarm - a human had to notice first. Its step 2 is separately
obsolete: ADR-0521 made every served model S3-only, so there is no
zone-bound qwen PVC to recreate.

What is worth knowing in a degraded state: with all three models on one
node, all three slices are taken, so no rolling update can schedule until
the second node returns. A config push during an outage will sit Pending.

### Changing replicas

`gitops/apps/machines/application-d0.yaml` sets `ignoreDifferences` on
MachineSet `/spec/replicas` with `RespectIgnoreDifferences=true`, so a
replica count committed in `values.yaml` is **deliberately never pushed**
to the live object - Git and cluster diverge on that field by design, which
is what lets the ClusterAutoscaler own the burst set. Changing a count for
real always takes a live command:

```
oc scale machineset <name> -n openshift-machine-api --replicas=<n>
```

A new node takes ~8-10 min (EC2 boot + ignition + NVIDIA driver build)
before it advertises its MIG slices.

### Decommissioning a node

`oc adm drain` on its own can hang forever - any single-replica Deployment
with `minAvailable: 1` reports `disruptionsAllowed: 0` and the eviction API
will wait on it indefinitely. Check first:

```
oc get pdb -A -o custom-columns=\
NS:.metadata.namespace,NAME:.metadata.name,ALLOWED:.status.disruptionsAllowed
```

Cordon, then delete the blocking pods and any StatefulSet singletons one at
a time (a cordoned node makes them reschedule elsewhere), then drain. Watch
for `gp3-csi` volumes: they are single-AZ, so their pods can only land on
another node in the same zone.

## Retired predecessors

Five hand-deployed `startx-cluster-machine-*` Applications (2026-08-17,
straight from `startxfr/helm-repository@devel`) previously rendered 9
machinesets whose machines all Failed with "no security group found": their
`cluster.id` parameter (`def7f838-...`) was not the real infra id
(`demo222-kpkqk`), and every AWS tag filter derives from it. They were
deleted as part of the ADR-0351 rollout (the two apps owning
MachineConfig(Pool)s had their finalizers stripped first - cascade-deleting
those would have deleted the live `worker` MachineConfigPool). The IPI
`demo222-kpkqk-workergpu-*` machinesets stay live at replicas 0 as an
installer-native escape hatch, deliberately unmanaged by this chart.

WP-083 note (2026-08-26): that was aspirational for a while.
`demo222-kpkqk-workergpu-eu-west-2a` had been running at replicas 1 since
ADR-0412 borrowed its idle full GPU, and stayed up after ADR-0414 retired
that exception - a g7e.2xlarge billed 24/7 whose whole 96GB card sat at 0%
utilisation. It is back at 0, and the escape hatch is real again.
