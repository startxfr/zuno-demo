# WP-200: Show the UnifAI RAG working live

- **State:** Not started
- **ADRs:** [ADR-0598](../../adr/0598-give-every-persona-default-unifai-team-workspaces-and-a-shared-catalog.md)
- **Depends on:** WP-198
- **Related:** [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [WP-149](wp-149-unifai-rag-qdrant-hybrid-sources-backup.md)
- **Target:** v0.13
- **Estimated files touched:** ~5 (a test document set, the chart, demo docs; maybe a small operator change)

> Why: the RAG has never been seen working in real time. Its Overview page counts only the Slack and Document source types,
> so it shows 0 while Confluence and web content is indexed. User decision of 2026-11-04: show a document upload and a
> visible Confluence sync. The Overview counting patch and Slack are out of scope.

## Goal

Two demos:
- a document is uploaded on the Documents page and is answered from in a chat a minute later;
- a Confluence resync is triggered and its progress followed.

## Steps

1. **Upload.**
   - A small public test document set (English) under the chart's `files/`.
   - Check end to end: upload, then docling, embedding, Qdrant, then a chat through a RAG workflow or template.
   - Find which retriever covers the `document_data` collection.
   - Fix whatever breaks (NetworkPolicy, mesh, docling timeout).
2. **Confluence resync on demand.** Find the existing trigger (annotation, operator field, rag endpoint). If there is
   none, propose a `unifai.startx.fr/resync-at` annotation to the fork. Write the demo steps.
3. **Docs.** Record what the Overview page counts. The rh-* sources stay suspended (R-530).

## Acceptance

- The uploaded test document reaches embedded. A question about it returns a cited answer.
- A triggered Confluence resync changes the source's status, and a page changed recently can then be found.
