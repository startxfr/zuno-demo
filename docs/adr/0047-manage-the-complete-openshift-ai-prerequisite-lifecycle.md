# ADR-0047: Manage the complete OpenShift AI prerequisite lifecycle

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The Make/Ansible interface already manages OpenShift AI, DataScienceCluster and NVIDIA GPU prerequisites. The selected OpenShift AI 3.5 capabilities can also require supporting operators/services such as NFD, cert-manager, Service Mesh, Connectivity Link, LeaderWorkerSet, OGX and MaaS-related dependencies depending on the enabled feature set.

## Decision

Extend `make precheck` and `make prepare` component dispatch so every OpenShift AI capability has explicit prerequisite checks and idempotent installation roles. Only install feature-specific dependencies when the corresponding capability is enabled. The DataScienceCluster configuration must be checked after operator installation.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Platform preparation becomes reproducible and failures identify the missing dependency rather than surfacing later during model/RAG deployment.

## Security considerations

Operators must be installed from approved catalogs/channels and their cluster-scoped permissions documented before installation.

## Operational considerations

Add component checks for NFD, GPU Operator, cert-manager, Service Mesh, OGX, Connectivity Link, LeaderWorkerSet and MaaS as applicable to the chosen v0 feature flags.

## Implementation state

**Implemented (2026-08-05)**, scoped to what this repository's actual v0
feature set uses - not every capability the Context/Operational
considerations name generically, several of which turned out not to
apply once checked against the real configuration (see below, and
`platform/openshift-ai/README.md` for the full per-capability reasoning).

**New prerequisite role**: `ansible/roles/nfd` (precheck + prepare,
`PREP_COMPONENT`, positioned immediately before `nvidia_gpu` in
`ansible/playbooks/{precheck,prepare}.yml`'s `prerequisite_components`).
This closes a real, previously undeclared gap: the NVIDIA GPU Operator's
default `ClusterPolicy` (`ansible/roles/nvidia_gpu`) relies on
Node-Feature-Discovery-applied node labels to identify GPU-bearing nodes,
and nothing in this repository installed NFD before this ADR.

**A real bug found and fixed while implementing this ADR** (Consequences:
"failures identify the missing dependency rather than surfacing later
during model/RAG deployment" - found by reading, which is even earlier
than that): `ansible/roles/openshift_ai/tasks/prepare.yml`'s
`DataScienceCluster` set `kserve.serving.managementState: Managed` with
`name: knative-serving`, which implicitly requires the Red Hat OpenShift
Service Mesh Operator, the Red Hat OpenShift Serverless Operator (which
owns the `KNativeServing` CR that `name` referenced) and cert-manager -
none of which this repository ever installed. On a real cluster this
`DataScienceCluster` would never have reached `Ready`. Fixed by setting
`serving.managementState: Removed` (RawDeployment mode) instead - this
demo's one model (`gitops/charts/models`) runs
`minReplicas == maxReplicas == 1`, always on, with no use for Serverless's
scale-to-zero, so RawDeployment is the *correct* mode here, not a
workaround. `gitops/charts/models/templates/inferenceservice.yaml` now
also sets `serving.kserve.io/deploymentMode: RawDeployment` explicitly
(belt and suspenders with the cluster-wide default).

**Per-capability disposition** (Operational considerations: "Add
component checks for NFD, GPU Operator, cert-manager, Service Mesh, OGX,
Connectivity Link, LeaderWorkerSet and MaaS as applicable to the chosen v0
feature flags" - the "as applicable" qualifier is doing real work here):

| Capability | Disposition |
|---|---|
| NFD | Genuinely needed - new `ansible/roles/nfd` |
| GPU Operator | Already had a role (`nvidia_gpu`); now correctly ordered after `nfd` |
| cert-manager, Service Mesh, Serverless | Not installed - the RawDeployment fix above removes the need for all three |
| Connectivity Link | Not applicable - this project's own MCP Gateway/AI Inference Gateway (ADR-0010/ADR-0009) are its policy enforcement points, not a Connectivity-Link-fronted API |
| LeaderWorkerSet | Not applicable - one always-on, single-GPU model, no multi-node/multi-GPU serving topology exists |
| MaaS | Not applicable to v0 - ADR-0049 ("Zuno as MaaS policy router") is explicitly deferred to v1 |
| OGX | Not a separate operator - ADR-0018 defines it as this project's name for capabilities (`kserve`, RAG) already covered by the rows above |

"The DataScienceCluster configuration must be checked after operator
installation" (Decision) was already true structurally before this ADR -
`openshift_ai/tasks/prepare.yml` applies the Subscription, waits for the
CRD, *then* applies the DataScienceCluster and waits for it to report
Ready - not something this ADR needed to build, just to preserve.

Security considerations ("Operators must be installed from approved
catalogs/channels"): every Subscription in this repository (existing and
new) sources from `redhat-operators` or `certified-operators` in
`openshift-marketplace` - never a community/unverified catalog; the new
`nfd` role follows the same convention. See ADR-0048's implementation note
for the channel-selection half of this (this ADR set up the roles;
ADR-0048 made the channel selection itself verified-not-hardcoded).

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0002
- ADR-0003
- ADR-0018
- ADR-0019
- ADR-0030

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
