# nfd

Installs the Node Feature Discovery Operator (OLM `Subscription`,
redhat-operators catalog, `stable` channel) and applies a minimal
`NodeFeatureDiscovery` instance (ADR-0047). PREP_COMPONENT only - no
CONFIG_SCOPE, nothing to configure beyond that instance
(`tasks/configure.yml` is a documented no-op, same convention as
`ansible/roles/nvidia_gpu`).

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

`ansible/playbooks/{precheck,prepare}.yml` list `nfd` before `nvidia_gpu`
in `prerequisite_components`, and `Makefile`'s `PREP_COMPONENTS` includes
it - `make prepare nfd` (or the default `make prepare` "all" run, which
now prepares it in the correct order) must complete before
`make prepare nvidia-gpu`.
