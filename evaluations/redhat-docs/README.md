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
