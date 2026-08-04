# ADR-0048: Discover supported operator channels and serving runtimes at deployment time

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The repository contains hard-coded assumptions such as `quay.io/modh/vllm:rhoai-2.16-cuda`, `latest` channels and comments indicating that some tags were not verified. OpenShift AI 3.5 should use serving runtimes and operator channels that are actually available in the installed cluster/catalog.

## Decision

Precheck the PackageManifest/CatalogSource and OpenShift AI resources before configuration. Select approved operator channels and `ClusterServingRuntime`/serving images exposed by the installed OpenShift AI version instead of embedding unverified runtime image tags. Fail with a clear diagnostic when the expected capability is unavailable.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

The demo follows the installed product rather than stale hard-coded image assumptions, reducing upgrade and compatibility risk.

## Security considerations

Only approved registries and signed images may be selected. Runtime discovery must not silently switch to an untrusted image.

## Operational considerations

Add precheck output showing selected channels, operator versions, serving runtimes and GPU compatibility before model deployment.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0002
- ADR-0019
- ADR-0047
- ADR-0051

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
