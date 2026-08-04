# ADR-0009: Separate Agent Runtime from AI Inference Gateway

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Context

Zuno Demo requires an explicit, reviewable architecture decision so implementation, security and roadmap work remain aligned across the MVP and future releases.

## Decision

Keep orchestration/state/tooling separate from inference routing, budgets, quotas, model policy and provider fallback.

**Implementation status (2026-08-04):** implemented.
`components/agent-runtime` owns orchestration/state/tooling.
`components/ai-gateway` (`gitops/apps/ai-gateway` -> `gitops/charts/ai-gateway`,
applied by `ansible/roles/llm`) owns inference routing, provider fallback
and classification-eligibility (ADR-0020, ADR-0021) behind an
OpenAI-compatible `POST /v1/chat/completions`; `agent-runtime`'s
`ModelRouter` (`app/clients/model_router.py`) is now a thin client holding
no provider API key and no routing config. Budgets/quotas - also named in
this ADR's decision text - remain unimplemented (measured via
`ai-gateway`'s OTel cost metric, not enforced) and are documented as
explicit future work in `components/ai-gateway/README.md` rather than
built now; that scope decision was confirmed with the user before this
implementation, not silently deferred.

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
