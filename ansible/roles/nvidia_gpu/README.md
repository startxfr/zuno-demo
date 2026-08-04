# nvidia_gpu

Installs the NVIDIA GPU Operator (OLM `Subscription`, certified-operators
catalog) and applies the default `ClusterPolicy`, enabling GPU scheduling on
the two L4 worker nodes. PREP_COMPONENT only - no CONFIG_SCOPE, nothing to
configure beyond the `ClusterPolicy` itself (`tasks/configure.yml` is a
documented no-op).
