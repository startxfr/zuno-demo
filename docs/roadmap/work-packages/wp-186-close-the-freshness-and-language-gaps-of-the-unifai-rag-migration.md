# WP-186: Close the freshness and language gaps of the UnifAI RAG migration

- **State:** Done (2026-11-03: the four ADRs and WP-24 are corrected, the ten French questions are measured at hit@1 0.80, so French retrieval is accepted as it is)
- **ADRs:** [ADR-0109](../../adr/0109-implement-source-freshness-and-trust-scoring.md), [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0205](../../adr/0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md)
- **Depends on:** none
- **Related:** [WP-24](wp-24-freshness-trust-scoring.md), [WP-149](wp-149-unifai-rag-qdrant-hybrid-sources-backup.md), [WP-168](wp-168-migrate-the-red-hat-product-documentation-to-unifai-rag.md), [ADR-0110](../../adr/0110-automate-document-acl-synchronization.md), [ADR-0203](../../adr/0203-enforce-knowledge-authorization-as-policy-intersection.md)
- **Target:** v0.11
- **Estimated files touched:** ~6: the status lines of ADR-0109, ADR-0110, ADR-0203, ADR-0205 and the header of WP-24; `evaluations/redhat-docs/ranking.yaml`, its README and one new report in `results/`.

> Found on 2026-11-02 while comparing an archive of leftover files with `origin/devel` (it held nothing unpublished).
> The old rag-service ranked by freshness and boosted the query language; UnifAI does neither, and four ADR status lines still point
> to code that no longer exists. This brief makes the documentation true and measures French retrieval, which nobody has done.

## Goal

The records say what the UnifAI RAG does about freshness and language, and French-language retrieval has a measured baseline.

## Context

- **Freshness.** UnifAI's query path ranks by no date and filters on none. Confluence and Web chunks carry `last_modified` (often empty for Web, which
  takes it from the HTTP header) but no `indexed_at`, `stale_after` or `language`; DOCUMENT chunks carry none of them
  (`rag/core/data_sources/types/*/pipeline_handler.py` in the fork). What the sync does better than the old service: it deletes the points of
  changed and vanished pages (`core/pipeline/executor.py` line 170), where the old code only down-ranked them. The old rank-last-and-flag
  treatment (`_freshness_decay_factor`, `_is_freshness_untrusted`, `_provenance_weight` in `search.py` at `877d8c83^`) has no replacement. A concrete
  case: a superseded procedure that is not deleted sits next to its newer version and nothing prefers the newer. The impact on the demo corpus is small
  (21 Red Hat web sources and Confluence, all live-synced).
- **Language.** The sparse side is a hashing BM25 encoder with accent folding and English and French stop words, no stemming, no language
  field, no boost (the old boost was +0.01). The dense model is multilingual. The four French-content questions of `ranking.yaml`
  (ids 18 to 21), asked in English, rank 1, 2, 1, 1. No question is asked in French, which is where stemming and a boost would matter.
- **Stale records.** ADR-0109 ("Implemented - see `components/rag-service/app/search.py`"), ADR-0110 (`rag_ingestion.py`), ADR-0203 and
  ADR-0205 (`rag-service` search) point to deleted files. WP-24 is `Done` for the same code. `platform/docs/check_docs.py` does not check that
  a status line cites an existing file, and this WP does not add that check (decision below).
- The write-path invariant test of ADR-0205 (the retrieval path never writes) went with `rag-service`. The invariant holds by construction in
  `components/mcp-gateway/app/handlers/rag_query.py` (one GET), but nothing asserts it.

## Steps

1. **Records (user decision: the four ADRs and WP-24).**
   - ADR-0109 and WP-24: superseded by ADR-0568. Freshness is now the sync cadence plus the deletion of vanished and changed pages; the decay,
     `stale` flag and provenance weight are gone.
   - ADR-0110: say what remains (access by source-level `aclGroups`, applied fail-closed at query time) and that per-page ACL reconciliation is gone.
   - ADR-0203: say that the intersection is now UnifAI's group ACL plus the `knowledge.*` tag filters.
   - ADR-0205: keep the decision (indexed read, live tools for freshness and writes); record that its write-path invariant test was removed with
     `rag-service` and that the invariant is enforced by the shape of `rag_query.py`.
   - Keep the ADR index and the roadmap tables consistent, then run `check_docs.py`.
2. **French evaluation.** Add 10 questions written in French to `evaluations/redhat-docs/ranking.yaml`: paraphrases of existing entries and new ones on
   Confluence and Red Hat pages, each with its `expect` fragments. Leave the 24 existing entries untouched. Run the whole set with the probe pod of the
   2026-10-31 runs (same persona, `top_k` 10), save `results/ranking-fr-<date>.json`, and note in the README how the French subset is read.
3. **Rule (user decision).** If the French hit@1 is at least 0.7: accept, and amend ADR-0568 to say that bilingual handling is English and French stop
   words plus accent folding, with no language boost. Below 0.7: open a follow-up for a French suffix stemmer in the fork (sparse encoder version 3, full
   re-index), with this measurement as its baseline.

## Acceptance

- ADR-0109, ADR-0110, ADR-0203, ADR-0205 and WP-24 no longer cite deleted files and state what is true today; `check_docs.py` is green.
- The French report is in `results/`, and the brief records the figure and the decision (accept, or the follow-up WP).
- The existing 24-question baseline (hit@1 0.71, hit@5 0.86, MRR 0.77) is unchanged by the edit of `ranking.yaml`.

## Decisions

- **2026-11-02 (user):** fix the four ADRs together with WP-24, not only ADR-0109; ten French questions, not six, because a 0.7 threshold on six
  is decided by one question; no new `check_docs.py` check in this work package.
- **2026-11-03 (measured):** the French run, with the embedding model back, gave hit@1 0.80 (8 of 10), hit@5 0.90, MRR 0.85 (`evaluations/redhat-docs/results/ranking-fr-2026-11-03.json`); the
  24-question baseline stayed at 0.71 / 0.86 / 0.77. Rule of step 3: at least 0.7, so the result is accepted, no stemmer follow-up is opened, and ADR-0568 records that the bilingual handling
  is English and French stop words plus accent folding, with no language boost. One question misses (26, registry exposure), watched rather than fixed: a single miss of ten does not
  justify a sparse encoder version 3 and a full re-index.
- **2026-11-03 (written):** the read-only test of ADR-0205 exists again in `components/mcp-gateway/tests/test_rag_query.py` (GET and empty body for an answer, a refusal and a server error; no write call in the handler source).
- **2026-11-03 (user, after the fork's stemmer v3 shipped off in operator 0.1.50/0.1.51):** compare the sparse encoders on the live stack before deciding about v3.
  Result ([README](../../../evaluations/redhat-docs/README.md), `results/ranking-sparse-v1-v2-v3-2026-11-03.json`): French hit@1 v1 0.80, v2 0.60, v3 0.60; all 31
  v1 0.68, v2 0.48, v3 0.52. By the rule above v3 is not needed (v1 French hit@1 is above 0.7) and it stays off; the stack reads v1 again. The `_v2` and `_v3`
  collections stay in Qdrant (dropping them is a separate decision). Corrected below: the v2 and v3 figures are on an incomplete corpus.
- **2026-11-03 (rerun, user's go, after the second GPU node and operator 0.1.51):** the 0.62 is reproduced exactly
  (`results/ranking-v1-rerun-2026-11-03.json`): all 31 0.68 / 0.81 / 0.74, English 21 0.62 / 0.76 / 0.69, French 10 0.80 / 0.90 / 0.85.
  - Four English entries moved since the 0.71 run: 7 and 10 from rank 1 to 2; 9 and 11 from ranks 4 and 3 to out of the top 10.
  - Their books are still indexed. Asked for 50 results, 9 ranks 7 and 11 ranks 4, so the fused order depends on `top_k_results`.
  - Both runs used `top_k` 10, so `top_k` does not explain the move; what changed between the two runs is not known. The French rule still holds.
- **2026-11-03 (correction, from a Qdrant facet on `metadata.source_id`):** the v2 and v3 collections were incomplete. The `[2,3]` resync left 11 of the 23
  sources without any chunk in v2/v3 and five partial, so the v2 and v3 columns above are not reliable and the 1,198-chunk gap is not a stale tail in v1 (v1 is
  complete, 4 stale chunks of a deleted source). A fresh v1 resync is not needed. Per the fork the first sync at a new version re-ingests every page, so the run did not complete for them (not investigated); a forced full ingest
  is a classification change or a recreated source. v3 stays off by the rule applied to v1.
