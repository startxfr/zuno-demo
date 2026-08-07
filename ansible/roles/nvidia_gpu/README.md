# nvidia_gpu

Applies the `gitops/apps/nvidia-gpu` ArgoCD Application (ADR-0312), whose
chart (`gitops/charts/nvidia-gpu`) installs the NVIDIA GPU Operator (OLM
`Subscription`, certified-operators catalog, sync-wave `"10"`) and its
default `ClusterPolicy` (sync-wave `"20"`), enabling GPU scheduling on the
two L4 worker nodes. A Day 0 component (ADR-0056) - `install.yml` applies
the whole chart, in two `apply_gitops_app.yml` calls (see below).
Previously applied raw manifests directly via `ansible/tasks/
apply_kustomize.yml` (ADR-0310); converted to this role-applies-one-
Application pattern by ADR-0312.

The `ClusterPolicy` spec is read from the installed CSV's own
`alm-examples` annotation at runtime rather than hand-maintained: a
hand-written minimal spec (`operator`/`driver`/`toolkit`/`devicePlugin`
only) was rejected outright on a real cluster (api.demo222.startx.fr, GPU
Operator v26.3.3) with "spec.daemonsets: Required value, spec.dcgm:
Required value, spec.dcgmExporter: Required value, spec.gfd: Required
value, spec.nodeStatusExporter: Required value" - this CRD version
requires substantially more top-level sections than the field list this
role used to hardcode. Every OLM-published operator ships its own
recommended default CR alongside the CSV, so `tasks/install.yml` reads
that instead of guessing the current required shape by hand - see
`gitops/charts/nvidia-gpu/README.md` for how this discovery interacts
with the chart now being applied as an ArgoCD Application (two
`apply_gitops_app.yml` calls, not a direct `kubernetes.core.k8s` apply of
the `ClusterPolicy`).

**Depends on `ansible/roles/nfd` having run first** (ADR-0047): the
default `ClusterPolicy` this role applies relies on Node Feature
Discovery's node labels (e.g.
`feature.node.kubernetes.io/pci-10de.present`) to identify GPU-bearing
nodes. This dependency previously existed but was undeclared - nothing in
this repository installed NFD before ADR-0047 added that role.
`ansible/playbooks/day0_{check,install}.yml` list `nfd` immediately before
`nvidia_gpu` in `day0_components` accordingly.
