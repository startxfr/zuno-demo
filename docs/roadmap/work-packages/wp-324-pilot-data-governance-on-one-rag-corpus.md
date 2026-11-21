# WP-324: Pilot data governance on one RAG corpus

- **State:** Not started (proposed by ADR-0625 on 2026-11-21; the ADR is `Proposed`, so this work package is not approved)
- **ADRs:** [ADR-0625](../../adr/0625-evolve-zuno-toward-a-modular-sovereign-enterprise-ai-platform.md)
- **Depends on:** none
- **Related:** [ADR-0110](../../adr/0110-automate-document-acl-synchronization.md), [ADR-0203](../../adr/0203-enforce-knowledge-authorization-as-policy-intersection.md), [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md)
- **Target:** v0.19
- **Estimated files touched:** ~8: a catalog configuration, a reconciliation job, tests, this brief

## Goal

For pilot corpora: owners and classifications in a catalog, lineage, versioning, ACL reconciliation and deletion propagation.

Horizon in the ADR's indicative roadmap: Day 60-90. The horizons count from the start of an approved initiative. They are not calendar dates.

## Proposed work

1. Choose the pilot corpora (open question of the ADR).
2. Catalog their owners and classifications.
3. Establish lineage and versioning from the source to the index.
4. Reconcile ACL changes and propagate deletions to the index.

## Existing work it builds on

- The query-time ACL filter of [ADR-0110](../../adr/0110-automate-document-acl-synchronization.md) on the UnifAI RAG ([ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md)) and the knowledge domains of [ADR-0203](../../adr/0203-enforce-knowledge-authorization-as-policy-intersection.md).
- The page [data retention](../../data/data-retention.md).

## Acceptance

- A revoked access to a source document shows in retrieval and in later access to the derived data.
- A deleted source document no longer appears in the index.
