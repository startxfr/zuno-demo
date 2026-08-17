# machines

Applies the `gitops/apps/machines` ArgoCD Application (ADR-0351), whose
chart (`gitops/charts/machines`, a vendored startx `cluster-machine`
wrapper) creates the cluster's GPU capacity: the permanent MIG-partitioned
inference MachineSet (`zuno-gpu-a`, g7e.4xlarge, replicas 1), the manual
AZ-failover MachineSet (`zuno-gpu-c`, replicas 0), the scale-from-zero
burst-training MachineSet (`zuno-gpu-burst-a`, tainted, MachineAutoscaler
min 0/max 1) and the `ClusterAutoscaler` singleton. A Day 0 component
(ADR-0056) - `install.yml` applies both Application halves then waits for
`zuno-gpu-a` to have its machine available (first boot of a g7e node is
~8 min; the NVIDIA driver build on top of it is `nvidia_gpu`'s wait, not
this role's).

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
