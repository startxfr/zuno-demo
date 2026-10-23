# WP-168: Migrate the Red Hat product documentation to UnifAI's RAG

- **State:** Not started
- **ADRs:** [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0575](../../adr/0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)
- **Depends on:** [WP-156](wp-156-retire-the-old-agent-stack-and-rag-stack-from-zuno-demo.md)
- **Related:** [WP-149](wp-149-unifai-rag-qdrant-hybrid-search.md), [ADR-0330](../../adr/0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md)
- **Target:** v0.11
- **Estimated files touched:** ~8 in the fork (`fork/unifai-operator` source type and controller, a RAG source adapter for web pages, tests) and ~4 in `zuno-demo` (`gitops/charts/unifai` sources, `rag-ingestion` removal, evidence).

> Decision of 2026-10-23 (user, while retiring the old stack in WP-156):
> `rag-service` and `rag-ingestion` stay in place for the Red Hat product
> documentation only, and this work package moves that documentation to UnifAI so
> that the old RAG can finally go. Until then the mcp-gateway handler keeps a
> second path to `rag-service` for what UnifAI does not hold.

## Goal

The Red Hat product documentation that `rag-ingestion` loads into `rag-service`
(about 874 `docs.redhat.com` pages: Satellite 6.16 and 6.17, OpenShift 4.21 and
4.22 books and release notes, and the other books listed in
`gitops/charts/rag-ingestion/values.yaml`) is a UnifAI RAG source tagged
`knowledge.tech`, ingested and re-synced by the unifai-operator. A search
through `/api/sources/query.bearer?tags=knowledge.tech` returns it next to the
Confluence pages, with the caller's group rules, and `rag-service`,
`rag-ingestion` and the mcp-gateway fallback are removed.

## Context

- UnifAI's RAG knows `DOCUMENT` (uploaded files), `CONFLUENCE` and `SLACK`
  sources. `UnifaiRAGSource` only has `type: confluence` today. Nothing fetches a
  list of public web pages.
- The stack already deploys `docling-serve`, which converts HTML and PDF to
  structured text; it is what the document pipeline uses for uploads.
- `rag-ingestion` today fetches, converts, chunks and embeds the pages
  (ADR-0105, ADR-0330, ADR-0519), keeps a raw copy in S3 and writes to
  `rag-service`. The page list and the per-page metadata (product, version,
  language) live in the chart values.
- Searches by Keycloak users already reach UnifAI with `tags=knowledge.tech`;
  today they only find Confluence pages.

## Steps

1. **Decide the source model (before any code).** Options: a new `UnifaiRAGSource`
   `type: web` with a URL list and per-URL metadata (recommended, same sync loop
   and status as Confluence), or one DOCUMENT upload per page driven by a Job.
   Record the choice and the metadata kept per page (product, version, URL) in
   this brief.
2. **RAG side (fork `rag/`).** A web-pages data source type: fetch each URL
   (respecting a rate limit and `If-None-Match`/`Last-Modified`), convert through
   docling, chunk with the existing pipeline, keep a per-URL manifest in
   `type_data` so a re-sync only touches changed pages, and delete the points of
   pages that left the list. Unit tests with recorded HTML, as for Confluence.
3. **Operator side.** `UnifaiRAGSource` `type: web` with `web.urls[]` (and an
   optional shared `metadata`), `visibility: shared` without ACL groups reachable
   by every signed-in user (the Red Hat pages are public), tags, and the same
   status fields. Envtest with the fake RAG API.
4. **Chart.** Generate the source list from the existing
   `gitops/charts/rag-ingestion/values.yaml` page list (one source per product
   and version, tagged `knowledge.tech`), rather than copying 874 URLs by hand.
5. **Ingest and compare.** Ingest on demo333, then compare answers to a fixed
   set of product questions between `rag-service` and UnifAI (top results and
   scores). Record the comparison in an evidence file.
6. **Switch and retire.** Drop the rag-service path from the mcp-gateway handler,
   then retire `rag`, `rag-ingestion` and their raw S3 prefix under the
   WP-156 procedure (separate window, user go).

## Acceptance

- UnifAI returns Red Hat product pages for the fixed question set with quality
  at least equal to `rag-service` (the comparison is in the evidence file).
- A re-sync with no page change writes nothing; a changed page is re-embedded
  alone; a removed page leaves no point.
- Searching as a user outside any group still finds the public pages and none
  of the shared Confluence ones.
- `rag-service` and `rag-ingestion` are uninstalled and `check_docs.py` is green.

## Open questions

- Is the raw S3 copy of the pages still needed once UnifAI holds the text
  (ADR-0546 treats S3 as the store for model weights and raw corpora)?
- Language and version handling: one tag per product version, or one source per
  version with a `product` metadata field the search can filter on?
- The embedding model and chunk size of `rag-service` differ from UnifAI's
  hybrid setup: do the comparison questions need re-tuning (threshold, top k)?
