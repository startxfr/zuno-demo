# ADR-0109: Implement source freshness and trust scoring

- **Status:** Superseded in part by [ADR-0568](0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md) (2026-11-02, WP-186) - the freshness ranking, the stale flag, the provenance weight, the live-read trigger in agent-runtime and the freshness-lag alert went with rag-service and agent-runtime (WP-156, WP-168). The per-domain freshness policy in `knowledge/<domain>/domain.yaml` and the live read of current state ([ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md)) stay in force
- **Target:** v0.1
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`../roadmap/adr-decisions-v0.1.md`) to a full record.

Use provenance, `source_modified_at`, `indexed_at` and source/domain
freshness policy to rank knowledge, signal stale content and trigger a
live MCP/API read when an indexed answer is not fresh enough for the
requested operation.

Scoring inputs and the staleness decision are implemented in
`rag-service` ranking and the Agent Runtime retrieval step; thresholds
come from the domain descriptors (`knowledge/<domain>/domain.yaml`), not
code.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Update 2026-11-02 (WP-186): what the UnifAI RAG does about freshness

The code this record pointed to is gone: `components/rag-service` (WP-168) and `components/agent-runtime` (WP-156). UnifAI's RAG does not rank by date and has
no stale flag, provenance weight or freshness-lag metric. What it does instead is part of the sync: a changed or vanished Confluence page or web page has its points
deleted before the new content is stored (`core/pipeline/executor.py` of the fork), which is stronger than the old down-ranking. Confluence and web chunks carry
`last_modified` (often empty for web, which takes it from the HTTP header); none carries `indexed_at` or `stale_after`. So freshness is now the sync cadence
(`syncInterval`) plus deletion, and the decay and flag clauses of this record are retired. An older procedure that stays in the source next to its replacement is
not preferred by anything; the demo corpus is live-synced, so the cost is small (see WP-186).

## Related ADRs

- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md)
  — the metadata-aware retrieval foundation this scoring builds on.
- [ADR-0105](0105-automate-source-specific-knowledge-ingestion.md)
  — the per-source cadences whose objectives this ADR's freshness
  policy is graded against.
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
  — the metadata schema (`source_modified_at`, `indexed_at`,
  `stale_after`) this ADR enforces and scores.
- [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md)
  — the routing principle this ADR's scoring/trigger mechanism
  implements, together (WP-24).
