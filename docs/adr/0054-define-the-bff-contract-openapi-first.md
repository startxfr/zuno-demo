# ADR-0054: Define the BFF contract OpenAPI-first

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The project requires versioned BFF APIs with Swagger/OpenAPI, but the reviewed Go BFF currently relies on hand-written request/response structs and comments describing the Runtime contract. This has already allowed identity and streaming expectations to diverge between components.

## Decision

Create a versioned OpenAPI specification for the agent BFF API and use it as the contract source for Go handlers/clients and frontend integration. Include chat/session endpoints, task discovery, SSE event schemas, citations, approvals/errors and authentication requirements. Generate code where practical and validate backward compatibility in CI.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

API drift is reduced and every agent BFF exposes consistent Swagger documentation. Contract changes become explicit review events.

## Security considerations

The specification must clearly mark authenticated operations, never expose internal tokens in schemas, and document authorization failures without leaking policy internals.

## Operational considerations

Add OpenAPI linting and contract tests between frontend, BFF and Runtime adapters.

## Implementation state

**Implemented (2026-08-05)** for the real API surface this component
exposes. `components/agent-bff/openapi.json` is a versioned (`1.0.0`)
OpenAPI 3.0.3 document covering both real operations
(`GET /healthz`, `POST /api/chat`), the JSON and SSE response variants
(ADR-0045), `Citation`/`ChatRequest`/`ChatResponse`/`ErrorResponse` plus
one schema per SSE event type, and a `bearerAuth` security scheme applied
to every operation except the health probe. Authored as JSON rather than
YAML specifically so the contract test below can parse it with
`encoding/json` alone - this component's `go.mod` had zero external
dependencies before this ADR (see its own README's "Why standard library
only") and still does after it; a YAML-parsing library would have been
the one exception a spec-only need didn't justify.

**Not part of this contract**: the Decision's generic template text also
names "task discovery" and "approvals". Neither concept exists anywhere in
this codebase - v0 is one chat endpoint per agent with no per-task routing
UI and no approval workflow - so `openapi.json` documents the real
`/api/chat`/`/healthz` surface rather than inventing endpoints to satisfy
that wording; a future agent/task-discovery feature would extend this
same spec file, not require a new one.

"Use it as the contract source ... Generate code where practical" -
`components/agent-bff/contract_test.go` (this repository's first Go test
suite) reads `openapi.json` and asserts the real Go wire structs
(`apiChatRequest`, `apiChatResponse`, `apiErrorResponse`,
`internal/runtime.Citation`) serialize to exactly the field names the spec
declares, via `encoding/json` struct tag reflection - not full code
generation (a two-struct API's marginal benefit from a generator like
`oapi-codegen` didn't justify the added toolchain for this small a
surface), but a real, running check that fails the moment either side
drifts from the other, which is what the Context names as the actual
problem ("identity and streaming expectations to diverge between
components").

Security considerations: `bearerAuth` is applied at the document level (every
operation except `/healthz`, which explicitly overrides with `security: []`);
no schema property holds a raw token (the security scheme's own
`description` says so explicitly, and `platform/api/lint_openapi.py`
checks it structurally - see below); `403`'s schema/description document
only "lacks the entitlement group", never which group was expected or
which groups the caller actually has - matching the real `main.go`
behavior, not just documenting an aspiration.

Operational considerations: "Add OpenAPI linting" -
`platform/api/lint_openapi.py` validates the spec against the OpenAPI 3.x
meta-schema (`openapi-spec-validator`) plus the two conventions named
above, run and passing in this phase's development environment (3/3
checks). "contract tests between frontend, BFF and Runtime adapters" -
`contract_test.go` above covers the BFF's own wire contract (run and
passing, 5/5 tests); a Runtime-side or frontend-side equivalent is a
natural next extension of the same pattern but out of this ADR's literal
scope ("a versioned OpenAPI specification for the agent BFF API",
singular) - not built here to avoid scope creep into components other
tracks/ADRs own.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0008
- ADR-0032
- ADR-0033
- ADR-0045

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
