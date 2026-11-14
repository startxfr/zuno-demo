# machines

Applies the `gitops/apps/machines` ArgoCD Application (ADR-0351), whose
chart (`gitops/charts/machines`, a vendored startx `cluster-machine`
wrapper) creates the cluster's GPU capacity: the permanent MIG-partitioned
inference MachineSets (`zuno-gpu-a` in eu-west-2a and, since WP-083,
`zuno-gpu-c` in eu-west-2c - both g7e.4xlarge at replicas 1, both
`all-balanced`, symmetric so either survives the loss of the other), the
scale-from-zero burst-training MachineSet (`zuno-gpu-burst-a`, tainted,
MachineAutoscaler min 0/max 1) and the `ClusterAutoscaler` singleton. Note
the Application sets `ignoreDifferences` on MachineSet `/spec/replicas`, so
replica counts in `values.yaml` are never pushed to live objects - changing
one takes an `oc scale`. A Day 0 component
(ADR-0056) - `install.yml` applies both Application halves then waits for
the GPU machinesets to have their machines available (first boot of a g7e node is
~8 min; the NVIDIA driver build on top of it is `nvidia_gpu`'s wait, not
this role's).

## General-purpose workers (2026-11-13)

`zuno-worker-a/b/c` (m5a.4xlarge, one per zone, group `general`, no taint) give the
platform non-GPU capacity so the three control-plane nodes can be unschedulable
(`schedulers.config.openshift.io/cluster` `mastersSchedulable: false`). On demo333 a
master ran 179 pods at 97% CPU, etcd applies took 200 ms+ and every operator lost its
leader election. The role sets `mastersSchedulable: false` once these sets have their
nodes (`zuno_masters_schedulable`, default false; only after the general sets have their nodes).

## Node pools (ADR-0614, 2026-11-13)

| Pool | MachineSets | Placement |
|---|---|---|
| infra | `zuno-infra-a/b/c` (m5a.2xlarge, 150 GB) | label + taint `node-role.kubernetes.io/infra`, `infra` MachineConfigPool; Red Hat infra-eligible components only |
| general | `zuno-worker-a/b/c` (m5a.4xlarge, 200 GB) | no taint |
| Spot overflow | `zuno-worker-spot-a/b/c` (m5a.2xlarge Spot, 0..1 each) | rendered by `gitops/charts/machines/templates/machineset-spot.yaml` with their MachineAutoscalers |
| GPU | `zuno-gpu-a` (and the sets at 0) | soft taint; **never scaled down without the owner's double approval** |

The role waits for the general and infra sets and the infra pool before it
makes the masters unschedulable. Moving infra components onto the infra
nodes is NOT done here: each component has its own switch (see ADR-0614).

## Ordering

`ansible/playbooks/day0_{check,install}.yml` list `machines` before
`nfd`/`nvidia_gpu`: the permanent GPU node should exist (or be
provisioning) by the time `nvidia_gpu` waits for its `ClusterPolicy` to go
ready - the GPU operator's operands only fully deploy once a GPU node is
present. `day0_uninstall.yml` lists it after them (reverse order): tearing
the GPU nodes away mid-uninstall would strand the GPU operator's
node-scoped operands.

## Uninstall hazard

`uninstall.yml` deletes the `-d0` Application, which cascade-deletes the
MachineSets and TERMINATES every GPU node this chart manages. The qwen
model PVC survives (namespaced storage), but all GPU workloads go Pending
until capacity is reinstalled. The IPI `demo222-kpkqk-workergpu-*`
machinesets (kept at replicas 0, unmanaged by this chart - see
`gitops/charts/machines/README.md`) remain available as a manual escape
hatch.
