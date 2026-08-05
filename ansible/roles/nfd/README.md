# nfd

Installs the Node Feature Discovery Operator (OLM `Subscription`,
redhat-operators catalog, `stable` channel) and applies a minimal
`NodeFeatureDiscovery` instance (ADR-0047). A Day 0 component (ADR-0056)
with a documented no-op `configure.yml` - nothing to configure beyond
that instance, same convention as `ansible/roles/nvidia_gpu`.

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

`ansible/playbooks/day0_{check,install}.yml` list `nfd` before
`nvidia_gpu` in `day0_components`, and `Makefile`'s `DAY0_COMPONENTS`
includes it - `make d0 install nfd` (or the default `make d0 install`
"all" run, which now installs it in the correct order) must complete
before `make d0 install nvidia-gpu`.
