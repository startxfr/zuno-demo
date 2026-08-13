# ADR-0205: Prefer indexed knowledge for read and live tools for freshness and write

- **Status:** To be implemented
- **Target:** v0.2
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

Several enterprise sources serve two different purposes. Their content is valuable in a semantic RAG index for fast, cross-record reasoning, but the source system remains authoritative for current state and is the only valid destination for mutations.

This applies directly to Confluence and Salesforce and can also apply to Jira, Aramis and Workday depending on the task. Salesforce knowledge is intentionally asynchronous by a few hours; technical documentation/Confluence is expected to refresh at least weekly. Treating every read as a live API call wastes latency/cost and loses semantic retrieval, while treating every indexed value as current risks stale operational answers.

## Decision

Adopt the following routing principle:

1. **Semantic/general read:** use the authorized logical knowledge domain first.
2. **Freshness-sensitive/current-state read:** use the live logical tool/API when the user explicitly asks for current state, policy marks the field/source as freshness-sensitive, or the indexed result exceeds the allowed freshness window.
3. **Write/mutation:** always use an authorized live tool/API; RAG is never a write path.
4. **No silent source substitution:** the answer/trace must identify when a live verification replaced or confirmed an indexed result.

Every operational-source chunk must record at least `source_modified_at`, `indexed_at` and `stale_after`. Knowledge policy defines acceptable freshness by domain/source/operation instead of hard-coding one global duration.

Initial objectives are:

- `knowledge.tech`: scheduled refresh at least weekly, with source-specific/manual refresh available;
- `knowledge.sales`: asynchronous Salesforce refresh on an hours-scale cadence (target configurable, expected to be a few hours);
- `knowledge.adv`: Aramis refresh according to project-data operational needs, configurable independently;
- `knowledge.sxa-legacy`: immutable/on-demand after a validated dump unless a new legacy snapshot is imported.

Confluence content indexed into `knowledge.tech` is the normal technical read path. Direct Confluence MCP is used for live verification or read/write operations requiring the current source system.

For Salesforce, `knowledge.sales` is the preferred semantic read path, while live Salesforce MCP is used for freshness-sensitive reads and every create/update operation.

## Consequences

Agents get low-latency semantic access without pretending that asynchronous indexes are transactional systems of record. The same source may legitimately appear in both the ingestion plane and the tool plane.

Agent Runtime/knowledge routing needs a small explicit freshness decision rather than ad-hoc tool fallbacks in prompts.

## Security considerations

Live fallback does not bypass normal MCP authorization. Indexed content and live results both contribute classification and local-only restrictions to the effective context. Writes require the user's/business role to hold an explicit write capability; read permission never implies write permission.

## Operational considerations

Expose source lag (`now - indexed_at`, and when available `indexed_at - source_modified_at`) in metrics. Alert on ingestion lag relative to the domain objective. A failed live verification must be reported as such rather than silently presenting stale data as current.

## Acceptance criteria

- A normal sales semantic question can be answered from `knowledge.sales` without a live Salesforce call.
- A question explicitly asking for the current value of a mutable Salesforce field can trigger live verification.
- Every Salesforce mutation goes through a write capability, never through RAG.
- Technical Confluence content can be answered from `knowledge.tech`; an authorized live Confluence action can still read/update the source page.
- Traces show whether a response used indexed knowledge, live verification, or both.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0017](0017-access-sales-data-through-controlled-mcp-tools.md)
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md)
- [ADR-0105](0100-v0.1-roadmap.md#adr-0105-automate-source-specific-knowledge-ingestion)
- [ADR-0109](0100-v0.1-roadmap.md#adr-0109-implement-source-freshness-and-trust-scoring)
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
