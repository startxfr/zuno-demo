# ADR-0009: Separate Agent Runtime from AI Inference Gateway

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Context

Zuno Demo requires an explicit, reviewable architecture decision so implementation, security and roadmap work remain aligned across the MVP and future releases.

## Decision

Keep orchestration/state/tooling separate from inference routing, budgets, quotas, model policy and provider fallback.

**Implementation status (2026-08-04):** not implemented as decided.
`components/agent-runtime` (orchestration/state/tooling) was built, but
inference routing/fallback (`ModelRouter`, `app/clients/model_router.py`)
was implemented inside it rather than as the separate `components/ai-gateway`
this ADR calls for — that directory remains an unimplemented README stub.
Every other v0 ADR's decision is realized in code as decided; this is the
one exception, tracked here rather than marked `Implemented`.

## Alternatives considered

Alternatives remain valid when documented in implementation discussions, but this ADR records the selected direction for the stated target release.

## Consequences

Implementation and documentation must follow this decision. Any material change requires a superseding ADR and an explicit migration/evolution note.

## Security considerations

Security implications must be evaluated during implementation. This decision must not weaken identity propagation, data classification, least privilege, secret management or auditability.

## Operational considerations

Operational checks, observability and rollback/diagnostic procedures must be added as the corresponding capability becomes executable.

## Migration / evolution

Future changes must be documented by a new ADR using `Supersedes ADR-0009` when applicable.

## Related ADRs

See [ADR index](README.md).
