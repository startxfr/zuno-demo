# ADR-0052: Harden all workloads for OpenShift restricted security and SecNumCloud objectives

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

A repository-wide search currently finds no consistent pod/container `securityContext` or `automountServiceAccountToken` hardening in the reviewed Helm content. The project targets OpenShift and has a future SecNumCloud-oriented security objective.

## Decision

Adopt a default restricted workload baseline: run as non-root/arbitrary UID compatible with OpenShift, `allowPrivilegeEscalation: false`, drop all Linux capabilities, `seccompProfile: RuntimeDefault`, read-only root filesystem where compatible, explicit writable emptyDir mounts, and `automountServiceAccountToken: false` unless Kubernetes API access is required. Add NetworkPolicies and least-privilege service accounts by default.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Workloads align with OpenShift restricted expectations and reduce lateral movement/privilege risk. Some third-party images may require remediation or explicit documented exceptions.

## Security considerations

Exceptions require an ADR or security waiver with compensating controls. No component may request privileged SCC merely for convenience.

## Operational considerations

Add policy-as-code or CI checks that fail charts missing the baseline and verify deployed pods against the expected SCC/PSA behavior.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0023
- ADR-0024
- ADR-0111
- ADR-0037

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
