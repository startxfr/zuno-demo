# WP-187: Carry the source classification through UnifAI RAG results, and keep Confluence content off external models

- **State:** Operator pending (steps 1 and 2 done 2026-11-02; step 3 set aside 2026-11-03; step 4 pushed to the fork, not released; the rest waits on operator 0.1.50)
- **ADRs:** [ADR-0565](../../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0034](../../adr/0034-compute-effective-classification-from-the-complete-context.md)
- **Depends on:** none (step 3 needs a UnifAI operator release)
- **Related:** [WP-168](wp-168-migrate-the-red-hat-product-documentation-to-unifai-rag.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md), [ADR-0206](../../adr/0206-separate-current-salesforce-knowledge-from-legacy-sxa.md)
- **Target:** v0.11
- **Estimated files touched:** ~4 in the fork (source field, payload, tests); ~6 in `zuno-demo` (`rag_query.py` and its test, the corp routing policy, the UnifAI chart and the demo333 source list, ADR notes) and an evidence file; the tekos task OKF in `zuno-demo-agents` if the `forbidden` mechanism is chosen.

> Found on 2026-11-02 while comparing an archive of leftover files with `origin/devel` (it held nothing unpublished).
> This is the one loss of the old RAG stack that touches security: retrieved chunks lost their classification.

## Goal

A retrieved chunk carries the classification of its source, the data level of the turn rises accordingly on every path that reaches the RAG, and no task that
reads Confluence can send that content to an external model.

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
- **Measured on 2026-11-02** ([evidence](../evidence/wp-187-exposure-measurement.md)): the label is not the control. The ai-gateway routes on the classification
  the caller declares, and both external providers accept C1 and C2, so C1 versus C2 changes no routing; the UnifAI agents never call the mcp-gateway search
  tool, so the constant is never read on their path; Lightspeed's model is the local MaaS one. What decides is `local_only_for` per task and the order of the
  preferred providers. Tekos's `answer-technical-question` made 51 calls at C2 to `ovhcloud-gpt-oss-120b` on 2026-10-31 (before tekos 0.4.3 put the local model
  first), and `find-relevant-docs` and `check-my-drive-docs` declare C1 by default, allow `knowledge.tech`, and list SaaS providers in their `fallback`.
- `local_only_for` is set in the corp model-routing policy (`platform/ai-gateway/model-routing-policy.yaml`); an agent cannot touch it
  (`platform/okf/generate_stack_config.py`, docstring of `model_routing()`). An agent or task can instead forbid roles (`forbidden`), which become `exclude`.

## Decisions

- **2026-11-02 (user):** the fix is in the fork and the operator, with no interim mapping in the mcp-gateway. The accepted consequence is that
  results keep the C1 label until the operator release; step 1 measures what that exposes.
- **2026-11-02 (user):** a chunk with no classification in its metadata is returned as **C2** (fail closed), not C1.
- **2026-11-02 (user, after the measurement):** widen this work package. It also closes the external-model path for the Confluence-reading tekos tasks and asks
  whether UnifAI can raise the session level from the source (ADR-0565 clause 3).
- **2026-11-03 (status from the UnifAI operator sessions, checked against the fork):**
  - Step 3 is set aside. Raising the run's level from a retrieved chunk is larger than a field read: a per-run classification floor that
    survives the Temporal activity boundaries, and the LLM, MCP and A2A header builders emitting the higher of the static level and that
    floor. The static route of step 2 (`local_only_for`) stays the control; no separate work package is opened.
  - Step 4 is coded and pushed to `devel` of the UnifAI fork, not released: `e10ab3be6` (the RAG writes the source's `classification` on
    every chunk; a change re-embeds the pages), `24ef98c56` (`UnifaiRAGSource.spec.classification`, optional enum C1 to C4, registered with
    the RAG service), `556707001` (end-to-end check of the field in search results and of the re-embedding), roadmap row R-521 of the fork.
    The search already returns the whole chunk metadata, so the field reaches the matches without a further change.
  - Step 5: `9630ecfd1` sets the operator VERSION to 0.1.50, with the rag image `devel-ca45ea9f5`; the release also carries the Tekos
    delegation fix (R-523). It waits on the user's canary and release approval; no date. Owner: the UnifAI operator session holding these
    commits.
  - After the release, in this repository: the catalog pin, the rag image roll, the demo333 Confluence sources set to C2 (the next sync
    re-embeds their pages), then step 6.

## Steps

1. **Measure the exposure** (done, [evidence](../evidence/wp-187-exposure-measurement.md)).
2. **Close the external-model path for Confluence-reading tasks (done and proved live on 2026-11-02, [evidence](../evidence/wp-187-exposure-measurement.md); agents release v0.8.1).** For tekos `answer-technical-question`, `find-relevant-docs` and `check-my-drive-docs` (and any
   arkos task that allows `knowledge.tech`), no external provider is reachable once Confluence content may be in the context. Two mechanisms; the brief records the
   choice with the user: (a) `local_only_for: [C2, C3]` for these tasks in the corp `preferences:` of the ai-gateway routing policy, which an agent cannot loosen
   (what arkos's `draft-architecture-testimonial` has); (b) `forbidden` roles in the task's OKF. Prove it live with a stresstest of tekos plus a forced local failure:
   the call fails or stays local, it never reaches OVHcloud. Check the generated routing file after the change.
3. **UnifAI session level.** Ask the UnifAI operator session whether the runtime can raise the session level from the classification of the RAG source it retrieved
   from (ADR-0565 clause 3, "a RAG source whose..."), and what it needs. Record the answer; the work is a separate operator item if it is larger than a field read.
4. **Source classification field**, with the UnifAI operator session: a `classification` field (C1 to C4, optional) on `UnifaiRAGSource`, written into each chunk's
   metadata at ingestion by the Confluence and web handlers and returned in the matches (the query response already returns the chunk metadata). The demo333 Confluence
   sources are set to C2 in `ansible/clusters/demo333.yml` and `gitops/charts/unifai`; the Red Hat web sources keep the `technical-docs` level.
5. **Fork and operator release** (owned by the UnifAI operator session): operator 0.1.50 plus a rag image; `zuno-demo` pins the release
   (`pin_operator_catalog.py`, then `make d2 install unifai`) and re-syncs the sources so existing chunks get the field.
6. **mcp-gateway.** `_from_unifai` reads the chunk's classification instead of the constant, and returns C2 when it is missing. Update
   `components/mcp-gateway/tests/test_rag_query.py`: field present is honoured, field missing gives C2. Agree the edit with the session that owns the mcp-gateway first.
7. **Prove it live.** A Confluence question through the mcp-gateway search tool shows C2; if step 3 allows it, a Confluence-backed tekos turn is raised to C2 in the
   ai-gateway span; a Red Hat docs question stays at its source's level. Save the evidence next to the measurement.
8. **Records.** Dated notes in ADR-0565 (clause 3, with the operator version) and ADR-0568. No new ADR.

## Acceptance

- No task that reads Confluence can reach an external model: the live proof of step 2 is in the evidence.
- The live proofs of step 7 are in the evidence file.
- The constant `C1` no longer appears in `rag_query.py`, and the mcp-gateway suite is green.
- ADR-0565 clause 3 and ADR-0568 state what is implemented and with which operator release; the answer of step 3 is recorded.
