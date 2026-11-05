# WP-210: Page-level Confluence ACL in the fork connector

- **State:** Not started
- **ADRs:** [ADR-0110](../../adr/0110-automate-document-acl-synchronization.md), [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md)
- **Depends on:** none (a change to the UnifAI fork, handed to the fork session as a patch)
- **Related:** [WP-168](wp-168-migrate-the-red-hat-product-documentation-to-unifai-rag.md), [WP-186](wp-186-close-the-freshness-and-language-gaps-of-the-unifai-rag-migration.md)
- **Target:** v0.1
- **Estimated files touched:** ~6 in the fork's Confluence connector and its tests, plus one evidence file in zuno-demo

> Why: ADR-0110 wanted the indexes kept in step with each page's own restrictions. The per-page reconciliation (`stage_reconcile_acls` in `components/rag-ingestion`) was retired with rag-ingestion (WP-168). UnifAI's RAG applies one `aclGroups` list per source, so a page restricted inside a space, or restricted after ingestion, is not reflected. [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md) records this as a cut. This WP restores it only if page-level access is wanted.

## Goal

A page that is restricted in Confluence, or whose restriction changes, stops being returned to callers outside its groups after the next sync, and a page that disappears is deleted, failing closed.

## Steps

1. **Decide that it is wanted.** The current access model is source-level and fail-closed. Confirm with the user that page-level restrictions are worth the connector change before building anything.
2. **Recover the old logic.** The code and tests are in git history: `git show 877d8c83^:components/rag-ingestion/src/rag_ingestion.py` (the reconcile stage) and `tests/test_reconcile_acls.py`.
3. **Re-implement it in the fork's Confluence connector** on a feature branch (ADR-0575): read each page's live group restrictions during the sync, write them into the chunk's `acl_groups` in addition to the source's, and delete chunks of pages that are gone or out of scope. Send the result to the fork session as a patch (a zuno-demo session cannot push to `startxfr/UnifAI`).
4. **Release and pin** through the fork's release lifecycle, with the user's go.

## Acceptance

- A page restricted to a group is returned only to that group's members after a resync; removing the restriction returns it to the source's groups.
- The restore drill of [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md) still compares equal, and the source classification (WP-187) is unchanged.
