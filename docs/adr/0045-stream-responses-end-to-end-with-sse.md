# ADR-0045: Stream responses end to end with SSE

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The Agent Runtime already uses LangGraph streaming primitives, but BFF/frontend paths currently behave as synchronous JSON requests. This prevents the UI from benefiting from model token streaming and conflicts with the first-token objective below six seconds.

## Decision

Use Server-Sent Events end to end for chat streaming: model/MaaS -> Agent Runtime -> BFF -> Go frontend server -> browser. Preserve request correlation, citations, tool status events, completion/error frames and client cancellation across the chain.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Users see output as soon as it is available and long responses no longer require waiting for the complete model result. Components must handle partial failures and disconnected clients.

## Security considerations

Do not stream hidden prompts, secrets, raw policy details or sensitive tool payloads. Apply classification/redaction before emitting events.

## Operational considerations

Add a performance test that measures time-to-first-token and fails when the agreed threshold is exceeded under the MVP reference load.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0009
- ADR-0032

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
