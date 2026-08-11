# Platform: lws

LeaderWorkerSet Operator (ADR-0317).

`ansible/roles/lws` (chart `gitops/charts/lws`) installs the
LeaderWorkerSet operator - the Kubernetes/OpenShift API used for
multi-node, multi-GPU model-serving topologies (e.g. distributed vLLM
inference) - ahead of any consumer: this demo still serves exactly one
always-on, single-GPU model (`gitops/charts/models`, `platform/gpu`) with
no multi-node topology. Only the operator is installed; no
`LeaderWorkerSet` workload exists in this repository yet, and there is no
cluster-singleton operand CR to instantiate (unlike `connectivity-link`'s
`Kuadrant` CR) - individual multi-node workloads create their own
`LeaderWorkerSet` objects, out of scope here. See
`ansible/roles/lws/README.md` and `platform/openshift-ai/README.md` for
the full disposition.
