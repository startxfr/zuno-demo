# Red Hat documentation search comparison

Fixed question set and script used by WP-168 to compare the Red Hat product documentation search of
`rag-service` (legacy) and UnifAI's RAG (`web` sources tagged `knowledge.tech`, see
`gitops/charts/unifai/files/redhat-docs.yaml`). Each question lists the book URL fragments that should
answer it; a hit is an expected book among the top-k sources. Scores are not comparable between the
engines (similarity versus reciprocal-rank fusion), so the report counts hits and ranks.

```bash
oc -n zuno-data port-forward svc/rag-service 18080:8080 &
oc -n zuno-unifai port-forward svc/unifai-rag-server 13456:13456 &
export KEYCLOAK_URL=https://keycloak.apps.<cluster-domain>
export EVAL_CLIENT_SECRET=$(oc -n zuno-auth get secret zuno-evaluations-client-secret -o jsonpath='{.data.client_secret}' | base64 -d)
export DEMO_PERSONA_PASSWORD=...   # from Vault, never on the command line
python3 evaluations/redhat-docs/compare.py --persona consultant-02 --top-k 5
```

`--engines unifai` queries UnifAI alone (once `rag-service` is retired); `UNIFAI_SOURCE_TYPES`
(default `WEB`) lists the source types searched on the UnifAI side.

## Ranking set

`ranking.yaml` (34 questions: the 24 English ones below, and 10 French ones, ids 25 to 34) measures the retriever's ranking (hit@1, hit@5, MRR) before and after a
change to UnifAI's search: natural questions with the book or Confluence page that answers them,
and three questions with no answer in the corpus, to calibrate the relevance threshold. Query
`query.bearer` with each entry's `sourceType` and `tags` and `top_k_results` (not `top_k`), as a
member of `agent_tekos`. See the file header for the matching rule.

**French subset (WP-186).** Entries 25 to 34 (`lang: fr`) are French reformulations of English entries that rank 1 (`pair` names the English one), with the same `expect`.
Run them on their own, with a copy of the file that keeps only the entries whose `lang` is `fr`, so that the 24-question figures below stay comparable. The rule
agreed for WP-186: a French hit@1 of at least 0.7 means French retrieval is accepted as it is (and ADR-0568 states that the bilingual handling is English and French stop words
plus accent folding, with no language boost); below 0.7 opens a follow-up for a French suffix stemmer in the fork (sparse encoder version 3, full re-index) with this figure as its
baseline.

Run on 2026-11-03 (`results/ranking-fr-2026-11-03.json`, the 24 English and the 10 French entries in one run, top_k 10): French **hit@1 0.80** (8 of 10), hit@5 0.90, MRR 0.85,
so French retrieval is accepted as it is. The one miss is 26 (the internal registry exposed outside the cluster), which lands on the images book instead of the registry book;
28 ranks 2 (etcd backup lands on the updating book first), and 33 ranks 1 where its English twin ranks 2. The 24-question figures are unchanged by the run (0.71 / 0.86 / 0.77).

**Sparse encoder versions (WP-186, 2026-11-03).** `results/ranking-sparse-v1-v2-v3-2026-11-03.json` compares the three sparse encoders of the UnifAI RAG on the 34-entry set (31 with an
expected book; operator 0.1.50, DBSF; stack written `[2,3]`, every source re-embedded once, then read 2, read 3 and read 1 again). hit@1 / hit@5 / MRR:

| Set | v1 (live) | v2 | v3 (v2 + French suffix stemmer) |
|---|---|---|---|
| all 31 | 0.68 / 0.81 / 0.74 | 0.48 / 0.68 / 0.58 | 0.52 / 0.68 / 0.61 |
| English 21 | 0.62 / 0.76 / 0.69 | 0.43 / 0.62 / 0.53 | 0.48 / 0.62 / 0.56 |
| French 10 | 0.80 / 0.90 / 0.83 | 0.60 / 0.80 / 0.68 | 0.60 / 0.80 / 0.71 |

v3 is slightly better than v2 (it recovers French entry 26) and both are below v1 on this corpus, so v3 stays off and the stack reads v1. Two caveats: the v2 and v3
collections hold 14,489 web chunks against 15,687 in v1 (a different corpus state, v1 keeps a stale tail), and v1 itself reads 0.62 on the English 21 against 0.71 on the
same day's earlier run (entry 9 now missed). A fair v1/v2 comparison would need v1 rewritten by a fresh resync too. The `_v2` and `_v3` collections are left in Qdrant.

**v1 rerun (2026-11-03, operator 0.1.51).** `results/ranking-v1-rerun-2026-11-03.json` reproduces the v1 figures exactly: all 31 0.68 / 0.81 / 0.74,
English 21 0.62 / 0.76 / 0.69, French 10 0.80 / 0.90 / 0.85.
- Against the earlier 0.71 run, entries 7 and 10 move from rank 1 to 2. Entries 9 and 11 leave the top 10.
- Asked for 50 results, 9 ranks 7 and 11 ranks 4: the books are indexed, and the fused order depends on `top_k_results`.
  Compare runs at the same `top_k`.

Results are kept in `results/`, one JSON report per run (per-question rank, top score and top URL).
`ranking-before-2026-10-31.json` is the baseline before UnifAI operator 0.1.44: hit@1 0.52, hit@5
0.76, MRR 0.63 over the 21 answerable questions, and every no-answer question still gets a top
score of 0.5, because the score is a fused rank, not a relevance.

`ranking-dbsf-2026-10-31.json`: the same set after UnifAI operator 0.1.45 made DBSF (score-based)
fusion the default, on the same chunks: hit@1 0.71, hit@5 0.86, MRR 0.77. Still missed: 1
(namespace definition), 2 and 12. Scores now range 0-2 (sum of normalised dense and sparse scores),
but the no-answer questions (0.95-1.65) overlap the answered ones (1.02-2.30 at rank 1): no
threshold separates them yet.

`ranking-prefix-2026-10-31.json`: DBSF plus the query instruction for qwen3-embedding
(`EMBEDDING_QUERY_PREFIX`, operator 0.1.47, same chunks): hit@1 0.67, hit@5 0.71, MRR 0.68, i.e.
WORSE than DBSF alone. Questions 3, 9 and 11 drop out of the top 10, and 19 goes from 2 to 3. The
prefix only changes the dense query embedding (the sparse side is untouched), so the dense side
alone got worse with it. The live prefix ends with "Query: " (trailing space), where the model card
has "Query:".
`ranking-prefix-nospace-2026-10-31.json`: the same prefix in the model card's exact format ("Query:",
no space) gives the same numbers (0.67 / 0.71 / 0.68). The instruction does not help this corpus: by
the agreed rule it is removed, back to DBSF alone.

The first reranker (TEI on CPU, `BAAI/bge-reranker-base`, 30 candidates) timed out on every query: about
0.9 s per 512-token candidate, against the rag-server's 10 s read timeout. Every query fell back to the
fused order and paid the 10 s, so that run (0.67 / 0.90 / 0.76) measures DBSF. No report is kept.
`ranking-rerank-minilm-2026-10-31.json`: DBSF, then `cross-encoder/ms-marco-MiniLM-L-6-v2` (TEI on CPU)
reranks 10 candidates. That takes about 1.5 s per query at 512 tokens per candidate, and no query timed
out. Ranking is WORSE than DBSF alone: hit@1 0.62, hit@5 0.86, MRR 0.70. Questions 1 and 2 drop out of
the top 10, and 7, 9 and 19 each lose ranks. The score is now a relevance in 0-1:

- The no-answer questions top out at 1e-5 to 8e-5.
- Most answered questions are above 0.8.
- Four answered questions sit low: 3 and 11 (top result is Argo CD docs, 0.12 and 0.16), and 19 and 21,
  which are French Confluence questions (0.15 and 0.00015). The model is trained on English MS MARCO.

A threshold between 8e-5 and 1.5e-4 separates the two groups on this set, but with almost no margin.

`ranking-rerank-mmarco-2026-10-31.json`: DBSF, then the multilingual `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`
(TEI on CPU) reranks 10 candidates. That takes about 3 s per query at 512 tokens per candidate. Results: hit@1
0.67, hit@5 0.86, MRR 0.75. The French questions recover (19 goes to rank 1, 21 scores 0.048 instead of
0.00015), but questions 1, 2 and 12 stay out of the top 10. The no-answer questions top out at 0.004, 0.009
and 0.083. The last of these is above answered question 21 (0.048), so no threshold separates the two groups.
By the agreed rule (keep a reranker only if it matches or beats DBSF alone, 0.71 / 0.86 / 0.77), the
reranker is removed. The stack goes back to DBSF alone and has no relevance threshold.
`ranking-dbsf-final-2026-10-31.json`: DBSF alone after the reranker was removed. The scores are the same
as before: 0.71 / 0.86 / 0.77.
