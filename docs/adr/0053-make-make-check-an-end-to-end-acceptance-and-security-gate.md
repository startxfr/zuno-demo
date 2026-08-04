# ADR-0053: Make make check an end-to-end acceptance and security gate

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The current check path is primarily service-health oriented. The project requires proof that the agent chain, classification, authentication, RAG, MCP and model routing behave correctly, not merely that pods answer `/healthz`.

## Decision

`make check` must run layered checks: infrastructure readiness, Keycloak login/claims, BFF and Runtime auth, RAG retrieval, MCP allow/deny, local model inference, permitted SaaS fallback, classification enforcement, SSE first token, citations, and the 20 Tekos evaluation scenarios. Security-negative cases are first-class acceptance tests.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

The demo gains one operator command that proves business behavior and critical security assumptions. Checks may take longer but failures become actionable.

## Security considerations

Mandatory negative tests include unauthorized agent access, wrong group, forged user identity, direct MCP bypass, C2 Confluence to SaaS denial and missing/expired tokens.

## Operational considerations

Return machine-readable results and non-zero exit status when mandatory gates fail. Preserve the 75% quality threshold while making security checks 100% mandatory.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0027
- ADR-0028
- ADR-0030
- ADR-0032
- ADR-0035
- ADR-0036
- ADR-0045

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
