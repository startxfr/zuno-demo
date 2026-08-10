# ADR-0009: Separate Agent Runtime from AI Inference Gateway

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

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

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
