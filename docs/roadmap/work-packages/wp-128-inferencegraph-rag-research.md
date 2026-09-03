# WP-128: InferenceGraph applicability research for the RAG pipeline

- **State:** Not started
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

## Acceptance checks

- The written recommendation states plainly: reranker yes/no, and if yes, which composition
  mechanism - each grounded in the GPU-quota numbers already established (ADR-0542), not asserted
  without evidence.
- If the recommendation is "yes, deploy a reranker," it names the follow-up WP that would design
  it (not created here).

## Operator / human follow-up (not executable by the model)

Review and decide on the recommendation; if a reranker is wanted, a new WP/ADR is required before
any deployment.

## Status updates (then re-run check_docs.py)

On completion: this WP's `- **State:**` line and tracker row move together. No ADR status changes
as a result of this WP alone - a follow-up ADR is needed only if the recommendation is adopted.

## Out of scope / deferred

Any InferenceGraph use for agent-runtime's own draft/reflect/guardrails chaining (ADR-0545
decision 3 explicitly keeps that in agent-runtime). Actual reranker deployment, if recommended.
