# ADR-0041: Remove nominative demo identities and static passwords from Git

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

`gitops/charts/keycloak/files/realm-zuno.json` currently contains named demo users and a shared hard-coded demo password. `evaluations/tekos/run_scenarios.py` also hard-codes the same password. The repository is public and the project explicitly requires avoiding nominative and sensitive information in Git.

## Decision

Replace named fixture identities with anonymous synthetic personas such as `consultant-user-01` and `sales-user-01`. Do not store passwords, client secrets or provider credentials in Git. Test credentials must be injected from Vault/External Secrets or CI secret stores through environment variables.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Public repository contents remain safe to share and test environments become reproducible without publishing credentials.

## Security considerations

Add secret scanning and repository policy checks. Treat any previously committed real credential as compromised and rotate it even if later removed from history.

## Operational considerations

Update Keycloak fixtures, evaluation harness and documentation, then add a CI rule that rejects known secret patterns and non-approved personal fixture data.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0024
- ADR-0025
- ADR-0051

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
