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
| MachineSet `zuno-gpu-c` (replicas 0) | AZ-failover twin in eu-west-2c, same MIG label, scaled by hand (runbook below) |
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

## AZ-failover runbook (zone a lost)

1. `oc scale machineset zuno-gpu-c -n openshift-machine-api --replicas=1`
   (~8 min: boot + NVIDIA driver build + MIG partition; the node comes up
   with the same `all-balanced` slices).
2. The embeddings and MaaS pods reschedule on their own. The qwen chat
   predictor's model PVC is zone-bound to eu-west-2a (gp3-csi is single-AZ):
   delete the `qwen25-7b-instruct-model-download` Job and the
   `qwen25-7b-instruct-model` PVC, then sync `zuno-models-d1` - the Job
   reruns on the new node and the PVC rebinds in eu-west-2c (~15GB
   re-download).
3. Fail back by reversing: scale `zuno-gpu-a` back to 1 once zone a
   returns, drain-wait, scale `zuno-gpu-c` to 0, recreate the PVC in a.

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
