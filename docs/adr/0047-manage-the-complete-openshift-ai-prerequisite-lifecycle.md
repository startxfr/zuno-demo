# ADR-0047: Manage the complete OpenShift AI prerequisite lifecycle

- **Status:** To be implemented
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

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

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
