# ADR-0044: Use PatternFly React for the agent frontend

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

`components/agent-frontend/static/style.css` explicitly states that it is hand-written CSS approximating PatternFly 5. The project requirement is to use the PatternFly framework, not only its visual vocabulary.

## Decision

Build the shared frontend with PatternFly React components and a reproducible frontend toolchain (for example Vite). Produce static assets at build time and continue serving them with the lightweight Go server. Keep runtime API endpoint injection from environment into JavaScript context.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

The UI conforms to the requested framework and gains accessible, maintained components while preserving a small production runtime image.

## Security considerations

Use dependency pinning, vulnerability scanning, CSP-compatible assets and no runtime CDN dependency.

## Operational considerations

Replace hand-rolled PatternFly-like classes and add frontend build/lint/accessibility checks.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0008
- ADR-0051

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
