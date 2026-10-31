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
