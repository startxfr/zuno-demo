# ADR-0034: Compute effective classification from the complete context

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

Tekos currently uses a static `TEKOS_DATA_CLASSIFICATION = "C1"` in `components/agent-runtime/app/graph/nodes.py`. The same workflow can retrieve public C1 documentation and C2 Confluence material. A static request classification can therefore under-classify the final model context.

## Decision

Compute an effective classification for every reasoning step from the highest sensitivity of all contributing inputs: user request, retrieved documents, tool results, conversation memory and generated intermediate artifacts. The effective classification must be propagated to model routing, logging/redaction policy, cache policy and downstream tools.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Model eligibility and data handling follow the actual context rather than the agent default. This requires classification metadata on RAG documents and MCP results.

## Security considerations

Classification must only stay the same or become more restrictive as context is accumulated. A downstream step must never downgrade classification automatically.

## Operational considerations

Implement classification aggregation in Agent Runtime state and add tests for C1-only, C1+C2 and C3 contexts.

## Implementation state

**Implemented (2026-08-05).** `components/agent-runtime/app/graph/state.py`
gains `effective_classification`, seeded at the technical-docs baseline
(C1) by `retrieve_node` and escalated (never downgraded - `_escalate()` in
`app/graph/nodes.py` is a strict highest-rank-wins comparison) by
`tool_call_node` when Confluence content (C2, per
`policies/data-classification/classification.yaml`) enters context.
`reason_node` now declares this aggregated value as
`X-Zuno-Data-Classification` instead of the old static
`TEKOS_DATA_CLASSIFICATION = "C1"` constant.

Scope note, made explicitly: Tekos's only two context sources today are
RAG (`technical-docs`, C1) and the Confluence tool (`confluence`, C2) -
there is no C3 source in this workflow (financial-data/hr-data aren't part
of Tekos's task set), so a genuine C3-context test isn't constructible
without fabricating a source this agent doesn't have. The aggregation
mechanism itself (`_escalate`/`_CLASSIFICATION_RANK`) is generic and
correctly handles C3 the moment a real C3 source exists. RAG documents
don't carry per-document classification metadata yet - that pipeline is
ADR-0046's scope; every RAG result is treated as the baseline C1 domain
since that's the only domain rag-service serves today.

Tests: `evaluations/tekos/security_checks.py`'s
`confluence_policy_is_c2_and_local_only` (config-consistency, no live
cluster needed) covers the C1-only vs. C1+C2 distinction at the policy
level; the full aggregation path is exercised end to end by the existing
`chat_triggers_tool` scenario (id 10) once a live cluster is available.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0021
- ADR-0035
- ADR-0046

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
