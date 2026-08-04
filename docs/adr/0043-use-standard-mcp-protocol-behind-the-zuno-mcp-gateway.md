# ADR-0043: Use standard MCP protocol behind the Zuno MCP Gateway

- **Status:** To be implemented
- **Target:** v1
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The project currently exposes a Zuno-specific `POST /v1/tools/{tool}/invoke` interface and JSON-RPC-like payloads. The long-term goal is to make MCP integrations reusable and standards-based while retaining central Zuno authorization and governance.

## Decision

Keep the Zuno MCP Gateway as the policy enforcement layer, but use a standards-compliant MCP SDK/protocol between the gateway and MCP servers. Where practical, the Agent Runtime should also consume a standard MCP client abstraction while the gateway injects policy enforcement transparently.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

MCP servers become reusable by other compatible clients, protocol maintenance is reduced, and custom policy remains centralized.

## Security considerations

Protocol compliance must not allow clients to bypass the Zuno policy gateway. Network/workload controls from ADR-0037 remain mandatory.

## Operational considerations

Introduce compatibility tests against the selected MCP SDK and migrate servers incrementally.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0010
- ADR-0036
- ADR-0037

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
