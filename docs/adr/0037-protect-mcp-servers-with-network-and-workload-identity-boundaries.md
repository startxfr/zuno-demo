# ADR-0037: Protect MCP servers with network and workload identity boundaries

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

Downstream MCP servers such as `sales-db` trust calls that are expected to originate from the central MCP Gateway. Without explicit network isolation and workload authentication, another pod in the cluster could attempt to call a server directly and bypass gateway policy.

## Decision

MCP servers must accept traffic only from the MCP Gateway and explicitly approved operational probes. Enforce this with OpenShift NetworkPolicy and service/workload identity. Direct agent-runtime-to-MCP-server paths are forbidden. Sensitive MCP servers must validate the gateway workload identity in addition to relying on network location.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

The gateway becomes a real security boundary instead of a convention. Operational debugging requires controlled access paths.

## Security considerations

Use least-privilege service accounts, disable unnecessary service account token automounting, and prevent namespace-wide implicit trust.

## Operational considerations

Add an acceptance test showing that a direct call to `sales-db-mcp` from an unauthorized namespace/workload is denied.

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
- ADR-0023
- ADR-0052

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
