# ADR-0047: Manage the complete OpenShift AI prerequisite lifecycle

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The Make/Ansible interface already manages OpenShift AI, DataScienceCluster and NVIDIA GPU prerequisites. The selected OpenShift AI 3.5 capabilities can also require supporting operators/services such as NFD, cert-manager, Service Mesh, Connectivity Link, LeaderWorkerSet, OGX and MaaS-related dependencies depending on the enabled feature set.

## Decision

Extend `make precheck` and `make prepare` component dispatch so every OpenShift AI capability has explicit prerequisite checks and idempotent installation roles. Only install feature-specific dependencies when the corresponding capability is enabled. The DataScienceCluster configuration must be checked after operator installation.

## Consequences

Platform preparation becomes reproducible and failures identify the missing dependency rather than surfacing later during model/RAG deployment.

## Security considerations

Operators must be installed from approved catalogs/channels and their cluster-scoped permissions documented before installation.

## Operational considerations

Add component checks for NFD, GPU Operator, cert-manager, Service Mesh, OGX, Connectivity Link, LeaderWorkerSet and MaaS as applicable to the chosen v0 feature flags.

## Implementation state

**Implemented (2026-08-05)**, scoped to what this repository's actual v0 feature set uses - several capabilities named generically above turned out not to apply once checked against the real configuration (see `platform/openshift-ai/README.md` for the full per-capability reasoning).

- New prerequisite role `ansible/roles/nfd` (precheck + prepare, positioned immediately before `nvidia_gpu` in `prerequisite_components`) closes a real, previously undeclared gap: the NVIDIA GPU Operator's default `ClusterPolicy` relies on Node-Feature-Discovery-applied node labels, and nothing in this repository installed NFD before this ADR.
- Real bug found and fixed: `ansible/roles/openshift_ai/tasks/prepare.yml`'s `DataScienceCluster` set `kserve.serving.managementState: Managed` with `name: knative-serving`, implicitly requiring OpenShift Service Mesh, OpenShift Serverless and cert-manager - none of which this repository ever installed; on a real cluster it would never have reached `Ready`. Fixed by setting `serving.managementState: Removed` (RawDeployment mode) - this demo's one model runs `minReplicas == maxReplicas == 1`, always on, with no use for Serverless's scale-to-zero, so RawDeployment is the correct mode, not a workaround. `gitops/charts/models/templates/inferenceservice.yaml` now also sets `serving.kserve.io/deploymentMode: RawDeployment` explicitly.
- Per-capability disposition: NFD - genuinely needed (new role). GPU Operator - already had a role, now correctly ordered after `nfd`. cert-manager/Service Mesh/Serverless - not installed, the RawDeployment fix removes the need for all three. Connectivity Link - not applicable, this project's own MCP Gateway/AI Inference Gateway (ADR-0010/ADR-0009) are its policy enforcement points. LeaderWorkerSet - not applicable, one always-on single-GPU model, no multi-node/multi-GPU topology. MaaS - not applicable to v0, deferred to v1 (ADR-0049). OGX - not a separate operator, ADR-0018 defines it as this project's name for capabilities (`kserve`, RAG) already covered above.
- "DataScienceCluster checked after operator installation" was already true structurally before this ADR (`openshift_ai/tasks/prepare.yml` applies the Subscription, waits for the CRD, then applies the DataScienceCluster) - preserved, not newly built.
- Security: every Subscription in this repository (existing and new, including `nfd`) sources from `redhat-operators` or `certified-operators` in `openshift-marketplace`, never a community/unverified catalog. See ADR-0048's implementation note for the channel-selection half of this.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- ADR-0002
- ADR-0003
- ADR-0018
- ADR-0019
- ADR-0030
