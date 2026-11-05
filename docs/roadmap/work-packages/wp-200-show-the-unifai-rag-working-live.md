# WP-200: Show the UnifAI RAG working live

- **State:** Done (2026-11-05: live upload and on-demand Confluence resync both checked in the browser)
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
2. **Confluence resync on demand.** The trigger exists, so no fork change is needed: any new value of
   `UnifaiRAGSource.spec.resyncToken` queues a sync at once (it only changes the spec hash). A live `oc patch` would be
   reverted by ArgoCD selfHeal, which changes the hash again and queues a second sync. So the chart's `ragSources`
   entries get an optional `resyncToken`, set per cluster. Write the demo steps: change the token, then follow the
   source status and the pipeline.
3. **Docs.** Record what the Overview page counts. The rh-* sources stay suspended (R-530).

## Acceptance

- The uploaded test document reaches embedded. A question about it returns a cited answer.
- A triggered Confluence resync changes the source's status, and a page changed recently can then be found.

## Repo work (2026-11-04)

- Chart: the `ragSources` entries take an optional `resyncToken`.
- The upload test set and the demo steps are in [docs/demo/unifai-live-rag.md](../../demo/unifai-live-rag.md).
- The RAG workflow is `<team>-rag` (WP-198 team examples). It searches the caller's uploads (DOCUMENT) and their groups'
  Confluence sources.
- Live check pending, after the WP-198 examples are enabled.

## Live findings (2026-11-05)

- **The upload pipeline works.** consultant-01 uploaded the test set in the Personal workspace. The three files reached
  Done, and Qdrant holds their chunks with `owner_id: consultant-01`, `visibility: private`.
- **`consultant-rag` did not see them.** A team workflow runs as the team: the rag-server searches with
  `owner_id = <team id>`. The forwarded token only adds the caller's groups, which is why Confluence passages came back
  (5 results) and the documents did not (0 results). This is upstream design, not a defect, and the Team view has no
  Documents page to upload in the team's name.
- **Fix:** the RAG demo moves to the personal workflow `<user>-my-documents` (WP-199 step 3). The demo guide says so.
- **Upload demo passed** (2026-11-05, in the browser): consultant-01 asked `consultant-01-my-documents` and got the cited
  answers; the team's `consultant-rag` still does not see the personal upload, as designed.
- **Confluence resync on demand passed** (2026-11-05). The user edited a page in SXSI. `resyncToken: demo-2026-11-05-1` on
  `tekos-satellite` and `tekos-openshift` (commit 782b5163, then `make d2 install unifai`) queued both syncs at once.
  `tekos-openshift` reported "411 pages (1 changed, 0 deleted at the last sync)" within a minute. consultant-01 then
  asked `consultant-01-my-documents` about the page, and the answer cited "O3 : Openshift - Kubevirt" with its link.
