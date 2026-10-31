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

`ranking.yaml` (24 questions) measures the retriever's ranking (hit@1, hit@5, MRR) before and after a
change to UnifAI's search: natural questions with the book or Confluence page that answers them,
and three questions with no answer in the corpus, to calibrate the relevance threshold. Query
`query.bearer` with each entry's `sourceType` and `tags` and `top_k_results` (not `top_k`), as a
member of `agent_tekos`. See the file header for the matching rule.

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
