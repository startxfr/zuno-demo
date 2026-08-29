# nfd

Applies the `gitops/apps/nfd` ArgoCD Application (ADR-0312), whose chart
(`gitops/charts/nfd`) installs the Node Feature Discovery Operator (OLM
`Subscription`, redhat-operators catalog, `stable` channel, sync-wave
`"10"`) and a minimal `NodeFeatureDiscovery` instance (sync-wave `"20"`,
ADR-0047) - gated on the Subscription's custom health check
(`ansible/roles/argocd/tasks/apply_resource_health_checks.yml`, ADR-0312)
so ArgoCD doesn't attempt the instance before OLM has installed the
operator. A Day 1 component (ADR-0056; moved here from Day 0 by
ADR-0421) - `install.yml` applies the whole chart in one call, same
convention as `ansible/roles/nvidia_gpu`.
Previously applied raw manifests directly via
`ansible/tasks/apply_kustomize.yml` (ADR-0310); converted to this
role-applies-one-Application pattern by ADR-0312.

## Why this role exists

`ansible/roles/nvidia_gpu`'s `ClusterPolicy` previously assumed GPU nodes
were already discoverable without ever installing what actually discovers
them: the NVIDIA GPU Operator's default node selection relies on
NFD-applied labels (e.g. `feature.node.kubernetes.io/pci-10de.present`) to
identify which nodes have an NVIDIA PCI device present. Nothing in this
repository installed the Node Feature Discovery Operator before this ADR -
a real, previously undeclared prerequisite gap (ADR-0047: "failures
identify the missing dependency rather than surfacing later during
model/RAG deployment").

`ansible/playbooks/day1_{check,install}.yml` list `nfd` before
`nvidia_gpu` in `day1_components` (both moved from Day 0 to Day 1 by
ADR-0421), and `Makefile`'s `DAY1_RUN_COMPONENTS` includes it -
`make d1 install nfd` (or the default `make d1 install` "all" run, which
now installs it in the correct order) must complete before
`make d1 install nvidia-gpu`. `machines` (Day 0) still runs before either,
unaffected by ADR-0421.
