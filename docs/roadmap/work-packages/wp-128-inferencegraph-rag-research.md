# WP-128: InferenceGraph applicability research for the RAG pipeline

- **State:** Done (2026-09-03)
- **ADRs:** ADR-0545 (decision 3, started here)
- **Depends on:** none
- **Related:** [ADR-0322](../../adr/0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md)
  (the RAG provider configuration this WP starts from),
  [ADR-0330](../../adr/0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md)

> **Research WP - no live change, no CR produced.** Deliverable is a written recommendation.

## Goal

Determine whether KServe's `InferenceGraph` should be used to compose the RAG retrieval pipeline
declaratively, starting from a fact this ADR's research surfaced: `default_reranker_model` is
unset in `components/rag-service`'s OGX configuration
(`_validate_reranker_model` only runs `if default_reranker_model is not None`) - **no reranker is
served today**, only the `embeddings` `InferenceService`. The real first question is not "how to
compose embed→rerank" but "do we want a reranker at all."

Arkos's own multi-model chaining (`draft_node`→`reflect_node`, history compaction, guardrails
pre/post) is explicitly **out of scope** - that is business/agent logic living correctly in
`agent-runtime` (conditional branching, prompt-budget clamping per ADR-0544, classification-aware
routing), not a fixed graph of served models. InferenceGraph composes `InferenceService`s; moving
agent reasoning into it would duplicate control agent-runtime already owns.

## Repo changes (step by step - all research, no code/CR changes)

1. Read `components/rag-service` (the OGX provider) end to end to confirm there is truly no
   reranking step happening in-process today (e.g. a cross-encoder call that isn't a served
   `InferenceService`) - if one exists, InferenceGraph is not the relevant mechanism regardless of
   the CR-level finding.
2. If no reranker exists anywhere (confirmed), produce a short options note answering two
   questions in order:
   - **Do we want a reranker at all?** Weigh retrieval-quality benefit against cost: it would be
     another GPU-quota-consuming `InferenceService` on a cluster already saturated
     (`mig-1g.24gb` 3/3, `mig-2g.48gb` 2/2, ADR-0542) - a real, not hypothetical, constraint.
   - **If yes, how should embed→rerank compose?** Compare (a) a declarative KServe
     `InferenceGraph` chaining `embeddings`→reranker, (b) `rag-service`/OGX calling a second
     `InferenceService` directly (today's pattern, extended), and (c) doing nothing until GPU
     headroom exists.
3. Recommend one option, grounded in the quota constraint and in KServe's own documented maturity
   for `InferenceGraph` at the installed RHOAI 3.5 version - note explicitly if the mechanism is
   still evolving upstream and that weighs into the recommendation.

## What NOT to touch

No `InferenceGraph`, `ServingRuntime`, or reranker deployment is created by this WP. No change to
`rag-service`/OGX configuration.

## Findings

1. **No reranking happens anywhere in `rag-service` today**, confirmed by reading both providers
   end to end:
   - **pgvector provider** (`app/search.py`): `hybrid_search()` fuses a pgvector similarity query
     and a PostgreSQL full-text query via Reciprocal Rank Fusion, then `_apply_soft_adjustments()`
     applies deterministic, non-ML metadata adjustments (language boost, provenance weight,
     freshness decay). No second model call anywhere in this path.
   - **OGX provider** (`app/ogx_provider.py`): `ogx_search()` queries OGX's `/v1/vector-io/query`
     and only applies client-side ACL/metadata filtering afterward - the module's own comment
     states it explicitly: *"surfaces the flag without re-ranking OGX's own ordering."*
   - `default_embedding_model`/`default_reranker_model` do not appear anywhere in `rag-service`'s
     Python code at all - they are OGX server-side config keys (ADR-0322), and only one model
     (`bge-small-en-v1.5`) is registered there; no reranker.
2. **No quality signal motivates adding one.** `components/trustyai-eval/ragas_eval.py` is
   observe-only by design (ADR-0534 Non-goals defer any pass/fail threshold). The only live RAGAS
   numbers in the repo (WP-109: `faithfulness=1.0`, `context_precision≈1.0`) are excellent, not
   poor - but measured on 3 questions, too small to be evidence either way. No ADR, WP, or roadmap
   entry records a relevance complaint or a documented retrieval-quality gap.
3. **A real, measured cost exists on the other side of the ledger.** `zuno-ai-run-gpu-cap` is
   saturated (`mig-1g.24gb` 3/3, `mig-2g.48gb` 2/2, ADR-0542) - a reranker would be a new
   GPU-quota-consuming `InferenceService` with no free capacity to place it in today.
4. **The insertion point would not affect agent-runtime either way.**
   `components/agent-runtime/app/clients/rag_client.py`'s contract (`POST /v1/search →
   SearchResponse`) does not change whether reranking happens inside `rag-service` via a
   declarative `InferenceGraph` or via a direct second `httpx` call - agent-runtime sees no
   difference. So the InferenceGraph-vs-direct-call question is deferred entirely: it only matters
   once a reranker is actually wanted.
5. **`InferenceGraph` the CRD is present and usable** (kserve `Managed` on the DSC) but has zero
   live instances anywhere in the cluster - confirmed during ADR-0545's own inventory.

## Recommendation

**No reranker for now.** The evidence available says the opposite of what would justify one: the
one quality signal that exists is already excellent (even though the sample is too small to trust
fully), no complaint or documented gap calls for better relevance, and the GPU quota that would
have to absorb a new served model is already at capacity. Revisit if either changes materially:
RAGAS scores degrade on a larger, more representative sample, or a documented client-facing
relevance complaint appears. Because no reranker is wanted, the InferenceGraph-vs-direct-call
composition question is moot for now - it becomes relevant only alongside a future decision to
deploy one, which would need its own WP/ADR.

## Acceptance checks

- The written recommendation states plainly: reranker yes/no, and if yes, which composition
  mechanism - each grounded in the GPU-quota numbers already established (ADR-0542), not asserted
  without evidence. **Met** - see Recommendation above.
- If the recommendation is "yes, deploy a reranker," it names the follow-up WP that would design
  it (not created here). **N/A** - recommendation is "no."

## Operator / human follow-up (not executable by the model)

Review the recommendation; no action needed unless it is rejected. Revisit only on the stated
triggers (degraded RAGAS at scale, or a documented relevance complaint).

## Status updates (then re-run check_docs.py)

`State: Done` reflected in this brief and its `docs/roadmap/implementation-roadmap.md` tracker row
together. No ADR status change - ADR-0545 stays `Accepted` (decisions 1/2 are tracked separately)
(*correction 2026-09-06*: with WP-126/127/128 all `Done` and decision 2's design-only scope ruled
complete by the demo owner, ADR-0545 is now `Implemented` - see WP-127's Status updates note);
a follow-up ADR is needed only if a reranker is adopted later.

## Out of scope / deferred

Any InferenceGraph use for agent-runtime's own draft/reflect/guardrails chaining (ADR-0545
decision 3 explicitly keeps that in agent-runtime). Actual reranker deployment, if recommended.
