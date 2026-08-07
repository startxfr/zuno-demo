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
{
  "query": "how do I size GPUs for OpenShift AI?",
  "top_k": 5,
  "product": "openshift-ai",
  "version": "3.5",
  "language": "fr",
  "caller_groups": ["consultant"]
}
```

`product`/`version`/`caller_groups` are new in ADR-0046; all four new
fields are optional:

- **`product`/`version`** - deterministic pre-ranking filters (exact match
  against the row's `metadata->>'product'`/`metadata->>'version'`),
  applied *before* ranking, not as a re-rank/boost - set these when the
  caller already knows the user named a specific product/version (Agent
  Runtime's `app/graph/nodes.py:_extract_product_version` does this for
  Tekos).
- **`language`** - a soft ranking preference (small score boost for
  matching-language rows), not a hard filter - a small bilingual corpus
  can easily have no matches in one language for a given query.
- **`caller_groups`** - the caller's JWT groups, forwarded so this service
  can enforce ACL-restricted documents itself (see "Access control and
  classification" below) rather than trusting the caller to have already
  filtered. Omitted/empty means "no groups" - ACL-restricted documents are
  excluded, not included (fail closed).

Response `200`:

```json
{
  "results": [
    {
      "id": "42",
      "source": "https://docs.redhat.com/...",
      "title": "vLLM ServingRuntime",
      "snippet": "...",
      "score": 0.031,
      "classification": "C1",
      "language": "en",
      "product": "openshift-ai",
      "version": "3.5",
      "stale": false
    }
  ],
  "vector_search_used": true
}
```

`vector_search_used` is `false` when the embedding backend was unreachable
for this request - the response still contains full-text-search-only
results rather than failing outright (see "Degradation" below).

## Retrieval metadata, ACL and classification (ADR-0046)

Every result now carries `classification`/`language`/`product`/`version`/
`stale`, read from the row's `metadata` jsonb (see
`data/rag/schema/003_rag_metadata.sql` for the exact field convention).
Callers are expected to use `classification` to escalate their own
effective classification (ADR-0034 - Agent Runtime's `retrieve_node` does
this, same pattern it already used for Confluence tool results) rather
than trusting a document is C1 just because it came from RAG. `stale`
(computed from `metadata.stale_after`, if present) doesn't exclude a
result - it's surfaced so the caller can down-weight or flag it - but this
service does apply a fixed rank penalty (`app/search.py:_STALE_PENALTY_FACTOR`)
so a stale document doesn't outrank a fresher one on relevance alone.

**Access control**: a document tagged with `metadata.acl_groups` (a JSON
array of group names) is only ever returned to a caller whose
`caller_groups` intersects it - enforced as a SQL predicate applied to
*both* the vector and full-text candidate queries
(`app/search.py:_filter_clause`), not a post-hoc filter on the response,
and not optional: even a request with no `caller_groups` at all still
applies the ACL predicate (excluding every ACL-restricted document, never
including one by default). A document with no `acl_groups` key, an empty
array, or a null value is unrestricted.

**Bilingual full-text search**: `data/rag/schema/003_rag_metadata.sql`
adds a generated `content_tsv` column whose PostgreSQL text-search
configuration (`english` vs `french`) is chosen per row from
`metadata.language`, replacing the previous hardcoded
`to_tsvector('english', ...)` expression, which could never correctly stem
French content regardless of the query's own language. The query side
matches against an English-or-French `tsquery` OR'd together, so a mixed
or ambiguous query still matches rows in either language - `language` in
the request is what actually prefers one over the other in ranking.

### `GET /healthz` / `GET /readyz`

Readiness returns `503` until the PostgreSQL pool is connected.

## Schema assumption

This service reads a table it does not own or migrate (that belongs to
another track's `sql_schema`/`postgresql` roles, per ADR-0015/ADR-0016,
base table created by `data/sxa/schema/002_pgvector.sql`; this track's own
`ansible/roles/rag` extends it with `data/rag/schema/003_rag_metadata.sql`,
ADR-0046). It assumes:

```
document_embeddings(
  id          <pk>,
  source      text,        -- canonical URL or document identifier, used as the citation source, UNIQUE (ADR-0046 - one row per source document, no chunking pipeline yet)
  title       text,
  content     text,
  embedding   vector,       -- pgvector column, dimensionality matching EMBEDDING_MODEL_NAME; nullable (ADR-0046 - a row can be full-text-searchable before a live embedding model has backfilled it)
  metadata    jsonb,        -- ADR-0046 retrieval metadata: product/version/language/source_type/classification/acl_groups/last_modified/stale_after/provenance - see 003_rag_metadata.sql's header comment for the exact convention
  content_tsv tsvector      -- ADR-0046, generated column: bilingual (metadata.language-aware) full-text search vector
)
```

with the `vector` extension already enabled on the target database. If the
real schema differs, `app/search.py`'s SQL statements and
`data/rag/schema/003_rag_metadata.sql` are the two places that need to
change.

## Hybrid search algorithm

Two ranked candidate lists are fetched independently, then merged by
reciprocal rank fusion (RRF, k=60):

1. **Vector**: `ORDER BY embedding <=> :query_embedding` (pgvector cosine
   distance operator).
2. **Full-text**: PostgreSQL's generated `content_tsv` column (ADR-0046,
   bilingual - see above) `@@ (plainto_tsquery('english', :query) ||
   plainto_tsquery('french', :query))`, ranked by `ts_rank_cd`.

Both candidate queries apply the same ADR-0046 deterministic
product/version filter and mandatory ACL predicate
(`app/search.py:_filter_clause`) before `LIMIT`, so filtering never
distorts the fusion by only narrowing one of the two ranked lists.

RRF avoids needing the two scores (cosine similarity vs. `ts_rank_cd`) to
be on a comparable scale - each list only contributes rank position, not
its literal score, to the fused ranking.

## Embedding backend

The query text is embedded via an OpenAI-compatible `POST
{EMBEDDING_SERVICE_URL}/v1/embeddings` call (default:
`http://embeddings-predictor.zuno-ai-run.svc:8080/v1/embeddings`,
override via env) - this assumes an embedding model is served through
OpenShift AI's KServe/vLLM serving path (ADR-0018's OGX definition), or
any other OpenAI-compatible embeddings endpoint. **Degradation:** if that
endpoint is unreachable or errors, this service logs a warning and falls
back to full-text-search only rather than failing the request - the
top-level RAG capability stays available even before an embedding model is
deployed.

## Database credentials

Sourced from individual `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD`
env vars, populated from the same `zunoapp` Vault-backed Secret the
`vault` role already generates at `secret/zuno/postgresql/app` (see
`ansible/roles/vault/tasks/install.yml`), delivered via an
`ExternalSecret` registered by this service's chart
(`gitops/charts/rag-service/templates/externalsecret-db.yaml`). No
credential is ever hardcoded (ADR-0024).

## Local development

```bash
cd components/rag-service
docker build -t zuno/rag-service:local .
docker run -p 8080:8080 \
  -e PGHOST=localhost -e PGUSER=zunoapp -e PGPASSWORD=... -e PGDATABASE=zuno \
  zuno/rag-service:local
```

## Tests

`tests/test_search_filters.py` covers ADR-0046's pure retrieval-metadata
logic (the filter-clause builder, staleness check, and the post-fusion
language-boost/staleness-penalty adjustment) without needing a live
database:

```bash
cd components/rag-service
pip install -r requirements.txt
python3 tests/test_search_filters.py
```

`hybrid_search` and the full `POST /v1/search` HTTP path were additionally
verified once, ad hoc, against a real `pgvector/pgvector:pg16` container
in this phase's development environment (contrary to every earlier
phase's "no live database" constraint - this sandbox turned out to have
container-registry access too) - applying `data/rag/schema/003_rag_metadata.sql`
and `data/rag/fixtures/seed.sql`, then exercising the version filter, ACL
enforcement (both the deny and the allow case), the bilingual French
boost, and the staleness penalty against real rows. This is what caught a
genuine, ADR-0046-unrelated latent bug: `app/db.py`'s asyncpg pool never
registered a `jsonb` type codec, so `metadata` came back as a raw string
and `app/search.py:_row_to_doc`'s `dict(row["metadata"])` would have
raised on the first real request against a live database. Fixed by
registering a `jsonb` codec in `db.py`'s new `_init_connection`. This ad
hoc verification isn't a standing, repeatable test (no fixture container
is wired into any `make` target) - `tests/test_search_filters.py` above
is what actually runs repeatably.
