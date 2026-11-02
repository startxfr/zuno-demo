# WP-187: Carry the source classification through UnifAI RAG results

- **State:** Not started
- **ADRs:** [ADR-0565](../../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0034](../../adr/0034-compute-effective-classification-from-the-complete-context.md)
- **Depends on:** none (step 3 needs a UnifAI operator release)
- **Related:** [WP-168](wp-168-migrate-the-red-hat-product-documentation-to-unifai-rag.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md), [ADR-0206](../../adr/0206-separate-current-salesforce-knowledge-from-legacy-sxa.md)
- **Target:** v0.11
- **Estimated files touched:** ~4 in the fork (source field, payload, query response, tests); ~4 in `zuno-demo` (`rag_query.py` and its test, the UnifAI chart and the demo333 source list, ADR notes) and an evidence file.

> Found on 2026-11-02 while comparing an archive of leftover files with `origin/devel` (it held nothing unpublished).
> This is the one loss of the old RAG stack that touches security: retrieved chunks lost their classification.

## Goal

A retrieved chunk carries the classification of its source, and the data level of the turn rises accordingly on every path that
reaches the RAG: the UnifAI agents and the OpenShift Lightspeed tool.

## Context

- `components/mcp-gateway/app/handlers/rag_query.py` gives every UnifAI result `classification: "C1"` (a module constant, the value of the
  `technical-docs` entry of `policies/data-classification/classification.yaml`). The retired rag-service reported the classification stored on each
  chunk, and the ingestion tagged Confluence chunks C2 (`rag_ingestion.py` line 962 at `877d8c83^`). Confluence pages are therefore C1 today.
- [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md) requires the classification to be returned per
  result, and [ADR-0034](../../adr/0034-compute-effective-classification-from-the-complete-context.md) raises the level of the turn from tool
  results. [ADR-0565](../../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md) clause 3 lets "a RAG source" raise a session's
  level; it is not implemented (`wp-156` states "ADR-0565 clause 3 not implemented").
- UnifAI agents are covered by static levels today (tekos carries `classificationOverrides` C2 for `answer-technical-question`). Whether the
  Lightspeed path, which calls `knowledge.tech.search` through the mcp-gateway, raises its turn from a result at all is not established.
- The UnifAI `UnifaiRAGSource` has no classification field.

## Decisions

- **2026-11-02 (user):** the fix is in the fork and the operator, with no interim mapping in the mcp-gateway. The accepted consequence is that
  results keep the C1 label until the operator release; step 1 measures what that exposes.
- **2026-11-02 (user):** a chunk with no classification in its metadata is returned as **C2** (fail closed), not C1.

## Steps

1. **Measure the exposure (no code change).** Ask a real Confluence question through the Lightspeed path and through a UnifAI agent, and read the
   level the turn gets (mcp-gateway logs and traces, `zuno.classification` on the ai-gateway `model_call` spans). Record the result and the real
   exposure in the evidence file.
2. **Design with the UnifAI operator session.** A `classification` field on `UnifaiRAGSource`, written into each chunk's payload at ingestion and
   returned in the metadata of the `query.bearer` matches. The demo333 Confluence sources are set to C2 in `ansible/clusters/demo333.yml` and
   `gitops/charts/unifai`; the Red Hat web sources keep the level of the `technical-docs` entry.
3. **Fork and operator release** (owned by the UnifAI operator session): field, payload, response, tests. `zuno-demo` pins the release
   (`pin_operator_catalog.py`, then `make d2 install unifai`) and re-syncs the sources so existing chunks get the field.
4. **mcp-gateway.** `_from_unifai` reads the chunk's classification instead of the constant, and returns C2 when it is missing. Update
   `components/mcp-gateway/tests/test_rag_query.py`: field present is honoured, field missing gives C2.
5. **Prove it live.** A Confluence question through Lightspeed and through tekos raises the turn to C2 in the ai-gateway span; a Red Hat docs question
   stays at its source's level. Save the evidence under `docs/roadmap/evidence/wp-187-*.md`.
6. **Records.** Dated notes in ADR-0565 (clause 3 implemented, with the operator version) and ADR-0568. No new ADR.

## Acceptance

- The live proofs of step 5 are in the evidence file.
- The constant `C1` no longer appears in `rag_query.py`, and the mcp-gateway suite is green.
- ADR-0565 clause 3 and ADR-0568 state what is implemented and with which operator release.
