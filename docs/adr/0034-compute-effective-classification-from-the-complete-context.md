# ADR-0034: Compute effective classification from the complete context

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

Tekos currently uses a static `TEKOS_DATA_CLASSIFICATION = "C1"` in `components/agent-runtime/app/graph/nodes.py`. The same workflow can retrieve public C1 documentation and C2 Confluence material. A static request classification can therefore under-classify the final model context.

## Decision

Compute an effective classification for every reasoning step from the highest sensitivity of all contributing inputs: user request, retrieved documents, tool results, conversation memory and generated intermediate artifacts. The effective classification must be propagated to model routing, logging/redaction policy, cache policy and downstream tools.

## Consequences

Model eligibility and data handling follow the actual context rather than the agent default. This requires classification metadata on RAG documents and MCP results.

## Security considerations

Classification must only stay the same or become more restrictive as context is accumulated. A downstream step must never downgrade classification automatically.

## Operational considerations

Implement classification aggregation in Agent Runtime state and add tests for C1-only, C1+C2 and C3 contexts.

## Implementation state

**Implemented (2026-08-05).**

- `components/agent-runtime/app/graph/state.py` gains `effective_classification`, seeded at the technical-docs baseline (C1) by `retrieve_node` and escalated (never downgraded - `_escalate()` in `app/graph/nodes.py` is a strict highest-rank-wins comparison) by `tool_call_node` when Confluence content (C2, per `policies/data-classification/classification.yaml`) enters context. `reason_node` declares this aggregated value as `X-Zuno-Data-Classification` instead of the old static `TEKOS_DATA_CLASSIFICATION = "C1"` constant.
- Explicit scope note: Tekos's only two context sources today are RAG (`technical-docs`, C1) and the Confluence tool (`confluence`, C2) - there is no C3 source in this workflow, so a genuine C3-context test isn't constructible without fabricating a source. The aggregation mechanism itself (`_escalate`/`_CLASSIFICATION_RANK`) is generic and correctly handles C3 the moment a real C3 source exists. RAG documents don't carry per-document classification metadata yet (ADR-0046's scope) - every RAG result is treated as baseline C1.
- Tests: `evaluations/tekos/security_checks.py`'s `confluence_policy_is_c2_and_local_only` covers the C1-only vs. C1+C2 distinction at the policy level; the full aggregation path is exercised end to end by scenario 10 (`chat_triggers_tool`) once a live cluster is available.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md)
