# ADR-0109: Implement source freshness and trust scoring

- **Status:** Implemented - see `components/rag-service/app/search.py`, `components/agent-runtime/app/graph/nodes.py`.
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
