# nvidia_gpu

Installs the NVIDIA GPU Operator (OLM `Subscription`, certified-operators
catalog) and applies the default `ClusterPolicy`, enabling GPU scheduling on
the two L4 worker nodes. A Day 0 component (ADR-0056) with a documented
no-op `configure.yml` - nothing to configure beyond the `ClusterPolicy`
itself.

**Depends on `ansible/roles/nfd` having run first** (ADR-0047): the
default `ClusterPolicy` this role applies relies on Node Feature
Discovery's node labels (e.g.
`feature.node.kubernetes.io/pci-10de.present`) to identify GPU-bearing
nodes. This dependency previously existed but was undeclared - nothing in
this repository installed NFD before ADR-0047 added that role.
`ansible/playbooks/day0_{check,install}.yml` list `nfd` immediately before
`nvidia_gpu` in `day0_components` accordingly.
