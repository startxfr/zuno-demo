# ADR-0036: Enforce the complete MCP authorization intersection in the gateway

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

`policies/tools/tool-policy.yaml` documents the intended authorization formula: agent declaration ∩ task rights ∩ user group rights ∩ classification ∩ platform policy. The policy file states that the MCP Gateway must enforce all five factors, but the implementation and agent definition stubs do not yet provide a reliable end-to-end enforcement path.

## Decision

Make the central MCP Gateway the mandatory policy enforcement point for tool invocation. It must validate the calling agent, active task, validated user groups, effective data classification and GitOps platform policy before forwarding a standard MCP call. Missing or invalid policy inputs cause denial.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Tool authorization becomes centralized, explainable and testable. Agent Runtime remains responsible for selecting a tool, but cannot bypass platform authorization.

## Security considerations

The gateway must fail closed, emit an auditable denial reason without leaking sensitive data, and never allow a task to widen its parent agent tool declaration.

## Operational considerations

Add policy decision traces and negative tests for each independent factor of the intersection.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0010
- ADR-0011
- ADR-0022
- ADR-0043

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
