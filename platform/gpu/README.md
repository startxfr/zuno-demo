# Platform: gpu

NVIDIA GPU Operator and GPU-node readiness (ADR-0047).

Two prerequisites, applied in order by `ansible/roles/{nfd,nvidia_gpu}`
(both `PREP_COMPONENTS`, `ansible/playbooks/{precheck,prepare}.yml`):

1. **Node Feature Discovery** (`ansible/roles/nfd`) - must be ready first.
   The GPU Operator's default `ClusterPolicy` relies on NFD-applied node
   labels (e.g. `feature.node.kubernetes.io/pci-10de.present`) to identify
   which nodes actually have an NVIDIA GPU present. This was a real,
   previously undeclared dependency gap: nothing in this repository
   installed NFD before ADR-0047.
2. **NVIDIA GPU Operator** (`ansible/roles/nvidia_gpu`) - the certified
   `gpu-operator-certified` operator plus a default `ClusterPolicy`,
   enabling GPU scheduling on this demo's L4 worker node(s) for the one
   local model `gitops/charts/models` serves.

`ansible/roles/datascience`'s GPU-capped `ResourceQuota` (1 GPU in
`zuno-ai`) is the demand side of this budget - see that role.
