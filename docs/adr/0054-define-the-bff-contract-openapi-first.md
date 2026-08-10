# ADR-0054: Define the BFF contract OpenAPI-first

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The project requires versioned BFF APIs with Swagger/OpenAPI, but the reviewed Go BFF currently relies on hand-written request/response structs and comments describing the Runtime contract. This has already allowed identity and streaming expectations to diverge between components.

## Decision

Create a versioned OpenAPI specification for the agent BFF API and use it as the contract source for Go handlers/clients and frontend integration. Include chat/session endpoints, task discovery, SSE event schemas, citations, approvals/errors and authentication requirements. Generate code where practical and validate backward compatibility in CI.

## Consequences

API drift is reduced and every agent BFF exposes consistent Swagger documentation. Contract changes become explicit review events.

## Security considerations

The specification must clearly mark authenticated operations, never expose internal tokens in schemas, and document authorization failures without leaking policy internals.

## Operational considerations

Add OpenAPI linting and contract tests between frontend, BFF and Runtime adapters.

## Implementation state

**Implemented (2026-08-05)** for the real API surface this component exposes.

- `components/agent-bff/openapi.json` is a versioned (`1.0.0`) OpenAPI 3.0.3 document covering both real operations (`GET /healthz`, `POST /api/chat`), the JSON and SSE response variants (ADR-0045), `Citation`/`ChatRequest`/`ChatResponse`/`ErrorResponse` plus one schema per SSE event type, and a `bearerAuth` security scheme applied to every operation except the health probe. Authored as JSON rather than YAML specifically so the contract test can parse it with `encoding/json` alone - this component's `go.mod` had zero external dependencies before and after this ADR.
- **Not part of this contract**: the Decision's generic template text also names "task discovery" and "approvals". Neither concept exists in this codebase - v0 is one chat endpoint per agent with no per-task routing UI and no approval workflow - so `openapi.json` documents the real `/api/chat`/`/healthz` surface rather than inventing endpoints; a future feature would extend this same spec file.
- `components/agent-bff/contract_test.go` (this repository's first Go test suite) reads `openapi.json` and asserts the real Go wire structs (`apiChatRequest`, `apiChatResponse`, `apiErrorResponse`, `internal/runtime.Citation`) serialize to exactly the field names the spec declares, via `encoding/json` struct tag reflection - not full code generation (a two-struct API didn't justify a generator like `oapi-codegen`), but a real, running check that fails the moment either side drifts.
- Security: `bearerAuth` is applied at the document level (every operation except `/healthz`, which overrides with `security: []`); no schema property holds a raw token; `403`'s schema/description documents only "lacks the entitlement group", never which group was expected or which the caller has - matching real `main.go` behavior.
- Operational: `platform/api/lint_openapi.py` validates the spec against the OpenAPI 3.x meta-schema plus the two conventions above (3/3 checks, run and passing). `contract_test.go` covers the BFF's own wire contract (5/5 tests, run and passing); a Runtime-side or frontend-side equivalent is a natural next extension but out of this ADR's literal scope (singular "BFF API").

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- ADR-0008
- ADR-0032
- ADR-0033
- ADR-0045
