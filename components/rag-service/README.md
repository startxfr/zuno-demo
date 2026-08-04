# rag-service

Shared RAG capabilities backed by PostgreSQL pgvector and hybrid
(vector + full-text) search. Backs the Agent Runtime's `retrieve` node
(ADR-0018) - currently used by Tekos.

Implementation: FastAPI (Python 3.11), `asyncpg`. Deployed by
`ansible/roles/rag` via `gitops/apps/rag/application.yaml` ->
`gitops/charts/rag-service` into the shared `zuno-data` namespace.

## Observability (ADR-0029)

`app/telemetry.py` initializes an OTLP tracer/meter at startup and wraps
`POST /v1/search` in a `rag_search` span (query length, `top_k`, latency,
outcome) plus the `zuno.rag_searches` counter and
`zuno.rag_result_count` histogram.

## HTTP API contract

### `POST /v1/search`

Request:

```json
{ "query": "how do I configure a KServe ServingRuntime for vLLM?", "top_k": 5 }
```

Response `200`:

```json
{
  "results": [
    { "id": "42", "source": "https://docs.redhat.com/...", "title": "vLLM ServingRuntime", "snippet": "...", "score": 0.031 }
  ],
  "vector_search_used": true
}
```

`vector_search_used` is `false` when the embedding backend was unreachable
for this request - the response still contains full-text-search-only
results rather than failing outright (see "Degradation" below).

### `GET /healthz` / `GET /readyz`

Readiness returns `503` until the PostgreSQL pool is connected.

## Schema assumption

This service reads a table it does not own or migrate (that belongs to
another track's `sql_schema`/`postgresql` roles, per ADR-0015/ADR-0016).
It assumes:

```
document_embeddings(
  id        <pk>,
  source    text,        -- canonical URL or document identifier, used as the citation source
  title     text,
  content   text,
  embedding vector,       -- pgvector column, dimensionality matching EMBEDDING_MODEL_NAME
  metadata  jsonb
)
```

with the `vector` extension already enabled on the target database. If the
real schema differs, only `app/search.py`'s two SQL statements need to
change.

## Hybrid search algorithm

Two ranked candidate lists are fetched independently, then merged by
reciprocal rank fusion (RRF, k=60):

1. **Vector**: `ORDER BY embedding <=> :query_embedding` (pgvector cosine
   distance operator).
2. **Full-text**: PostgreSQL `to_tsvector('english', title || ' ' ||
   content) @@ plainto_tsquery('english', :query)`, ranked by
   `ts_rank_cd`.

RRF avoids needing the two scores (cosine similarity vs. `ts_rank_cd`) to
be on a comparable scale - each list only contributes rank position, not
its literal score, to the fused ranking.

## Embedding backend

The query text is embedded via an OpenAI-compatible `POST
{EMBEDDING_SERVICE_URL}/v1/embeddings` call (default:
`http://embeddings-predictor.zuno-ai.svc:8080/v1/embeddings`,
override via env) - this assumes an embedding model is served through
OpenShift AI's KServe/vLLM serving path (ADR-0018's OGX definition), or
any other OpenAI-compatible embeddings endpoint. **Degradation:** if that
endpoint is unreachable or errors, this service logs a warning and falls
back to full-text-search only rather than failing the request - the
top-level RAG capability stays available even before an embedding model is
deployed.

## Database credentials

Sourced from individual `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD`
env vars, populated from the same `zuno_app` Vault-backed Secret the
`vault` role already generates at `secret/zuno/postgresql/app` (see
`ansible/roles/vault/tasks/configure.yml`), delivered via an
`ExternalSecret` registered by this service's chart
(`gitops/charts/rag-service/templates/externalsecret-db.yaml`). No
credential is ever hardcoded (ADR-0024).

## Local development

```bash
cd components/rag-service
docker build -t zuno/rag-service:local .
docker run -p 8080:8080 \
  -e PGHOST=localhost -e PGUSER=zuno_app -e PGPASSWORD=... -e PGDATABASE=zuno \
  zuno/rag-service:local
```
