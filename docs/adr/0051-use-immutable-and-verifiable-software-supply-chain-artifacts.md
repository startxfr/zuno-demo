# ADR-0051: Use immutable and verifiable software supply chain artifacts

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

Several GitOps applications track `targetRevision: main` and component Helm values use `tag: latest`. This makes a deployed environment non-reproducible and weakens rollback/auditability in a public-source project.

## Decision

Build every component in CI, publish images to Quay with immutable version/SHA tags and preferably digest pinning, generate an SBOM, scan dependencies/images, sign release images, and update GitOps manifests with immutable references. Production-like Argo CD applications must deploy a reviewed Git revision/tag rather than a moving `main` reference.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Every deployment can be traced to source, build and image digest. Releases and rollbacks become deterministic at the cost of adding CI/release automation.

## Security considerations

CI secrets stay outside Git. Signature verification and vulnerability policy become deployment gates for sensitive components.

## Operational considerations

Add CI checks rejecting `latest` for deployable component images and establish image signing/verification before industrialized use.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0004
- ADR-0022
- ADR-0024
- ADR-0041
- ADR-0048

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
