# rag-service

Shared RAG capabilities backed by PostgreSQL pgvector and hybrid
(vector + full-text) search. Backs the Agent Runtime's `retrieve` node -
currently used by Tekos.

Implementation: FastAPI (Python 3.11), `asyncpg`. Deployed by
`ansible/roles/rag` via `gitops/apps/rag/application-d1.yaml` ->
`gitops/charts/rag-service` into the shared `zuno-data` namespace.

## Observability

`app/telemetry.py` initializes an OTLP tracer/meter at startup and wraps
`POST /v1/search` in a `rag_search` span (query length, `top_k`, latency,
outcome, and `zuno.provider` - `pgvector` or `ogx`, see "OGX-backed
provider prototype" below) plus the `zuno.rag_searches` counter
(labeled `outcome`/`provider`) and `zuno.rag_result_count` histogram.

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

All four new fields are optional:

- **`product`/`version`** - deterministic pre-ranking filters (exact match
  against `metadata->>'product'`/`metadata->>'version'`), applied before
  ranking. Agent Runtime's `app/graph/nodes.py:_extract_product_version`
  sets these for Tekos.
- **`language`** - a soft ranking preference (small score boost for
  matching-language rows), not a hard filter.
- **`caller_groups`** - the caller's JWT groups, forwarded so this service
  can enforce ACL-restricted documents itself (see "Access control and
  classification" below). Omitted/empty means "no groups" -
  ACL-restricted documents are excluded, not included (fail closed).

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

## Retrieval metadata, ACL and classification

Every result now carries `classification`/`language`/`product`/`version`/
`stale`, read from the row's `metadata` jsonb (see
`data/rag/schema/003_rag_metadata.sql` for the exact field convention).
Callers are expected to use `classification` to escalate their own
effective classification (Agent Runtime's `retrieve_node` does this, same
pattern it already used for Confluence tool results). `stale` (from
`metadata.stale_after`, if present) doesn't exclude a result but does
apply a fixed rank penalty (`app/search.py:_STALE_PENALTY_FACTOR`).

**Access control**: a document tagged with `metadata.acl_groups` (a JSON
array of group names) is only returned to a caller whose `caller_groups`
intersects it, enforced as a SQL predicate (`app/search.py:_filter_clause`),
not a post-hoc filter. Even a request with no `caller_groups` still
applies the predicate (fail closed: excludes every ACL-restricted
document by default). A document with no `acl_groups` key, an empty
array, or a null value is unrestricted.

**Bilingual full-text search**: `data/rag/schema/003_rag_metadata.sql`
adds a generated `content_tsv` column whose PostgreSQL text-search
configuration (`english` vs `french`) is chosen per row from
`metadata.language`. The query side matches against an English-or-French
`tsquery` OR'd together, so a mixed or ambiguous query still matches rows
in either language; `language` in the request is what prefers one over
the other in ranking.

### `GET /healthz` / `GET /readyz`

Readiness returns `503` until the PostgreSQL pool is connected.

## Schema assumption

This service reads a table it does not own or migrate (that belongs to
another track's `sql_schema`/`postgresql` roles, base table created by
`data/sxa/schema/002_pgvector.sql`; this track's own `ansible/roles/rag`
extends it with `data/rag/schema/003_rag_metadata.sql`). It assumes:

```
document_embeddings(
  id          <pk>,
  source      text,        -- canonical URL or document identifier, used as the citation source, UNIQUE
  title       text,
  content     text,
  embedding   vector,       -- pgvector column, dimensionality matching EMBEDDING_MODEL_NAME; nullable
  metadata    jsonb,        -- retrieval metadata: product/version/language/source_type/classification/acl_groups/last_modified/stale_after/provenance - see 003_rag_metadata.sql's header comment for the exact convention
  content_tsv tsvector      -- generated column: bilingual (metadata.language-aware) full-text search vector
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
2. **Full-text**: PostgreSQL's generated `content_tsv` column (bilingual -
   see above) `@@ (plainto_tsquery('english', :query) ||
   plainto_tsquery('french', :query))`, ranked by `ts_rank_cd`.

Both candidate queries apply the same deterministic product/version
filter and mandatory ACL predicate (`app/search.py:_filter_clause`)
before `LIMIT`. Each list contributes only rank position, not its
literal score, to the fused ranking.

## Embedding backend

The query text is embedded via an OpenAI-compatible `POST
{EMBEDDING_SERVICE_URL}/v1/embeddings` call (default:
`http://embeddings-predictor.zuno-ai-run.svc:8080/v1/embeddings`,
override via env), assuming an embedding model served through OpenShift
AI's KServe/vLLM serving path, or any other OpenAI-compatible embeddings
endpoint. This is independent of the OGX Operator (see "OGX-backed
provider prototype" below). **Degradation:** if that endpoint is
unreachable or errors, this service logs a warning and falls back to
full-text-search only rather than failing the request - the top-level RAG
capability stays available even before an embedding model is deployed.

## OGX-backed provider prototype

`RAG_PROVIDER=ogx` (chart value `ogxProvider.enabled`, default `false`)
routes `POST /v1/search` to `app/ogx_provider.py` instead of the
pgvector+full-text hybrid search above. This is a **prototype, not a
default**: provider-parity tests must pass before any task switches from
the custom provider to OGX by default.

It targets the Red Hat OpenShift AI OGX Operator's data-plane API - a
separate `OGXServer` custom resource
(`gitops/charts/openshift-ai/templates/ogxserver.yaml`, also disabled by
default) configured against this repo's PostgreSQL/pgvector as OGX's
vector I/O provider and the KServe/vLLM stack as its inference provider.
No `OGXServer` instance has been applied to the test cluster, so
`app/ogx_provider.py` has never been exercised against a real OGX
endpoint; its request/response mapping follows the documented OpenAI
Vector Stores search API shape OGX advertises, not a verified wire
capture. It also does not push product/version/ACL filters down to OGX -
it over-fetches and applies the identical fail-closed product/version/
ACL-group checks `app/search.py:_filter_clause` enforces in SQL, in
Python, on the `attributes` each result carries.

`tests/test_ogx_provider.py` and `tests/test_provider_parity.py` (below)
cover the selection gate, filter/mapping logic, and structural parity
between the two providers' output against the shared `SearchResponse`
schema, without a live database or OGX endpoint. Real retrieval-quality
parity against a shared indexed corpus remains a residual operator action
(see the WP-06 roadmap brief).

## Database credentials

Sourced from individual `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD`
env vars, populated from the same `zunoapp` Vault-backed Secret the
`vault` role already generates at `zuno/postgresql/app` (see
`ansible/roles/vault/tasks/install.yml`), delivered via an
`ExternalSecret` registered by this service's chart
(`gitops/charts/rag-service/templates/externalsecret-db.yaml`). No
credential is ever hardcoded.

## Local development

```bash
cd components/rag-service
docker build -t zuno/rag-service:local .
docker run -p 8080:8080 \
  -e PGHOST=localhost -e PGUSER=zunoapp -e PGPASSWORD=... -e PGDATABASE=zuno \
  zuno/rag-service:local
```

## Tests

`tests/test_search_filters.py` covers the pure retrieval-metadata logic
(the filter-clause builder, staleness check, and the post-fusion
language-boost/staleness-penalty adjustment) without needing a live
database. `tests/test_ogx_provider.py` covers the OGX provider prototype's
selection gate, filter, and response-mapping logic (HTTP layer mocked -
see "OGX-backed provider prototype" above). `tests/test_provider_parity.py`
covers the provider-parity acceptance bar: the same logical document's
metadata/classification/staleness/citation fields come back identical
from both providers' row-mapping functions, and each provider's response
validates against the shared `SearchResponse` schema:

```bash
cd components/rag-service
pip install -r requirements.txt
python3 tests/test_search_filters.py
python3 tests/test_ogx_provider.py
python3 tests/test_provider_parity.py
```

`hybrid_search` and the full `POST /v1/search` HTTP path were additionally
verified once, ad hoc, against a real `pgvector/pgvector:pg16` container -
applying `data/rag/schema/003_rag_metadata.sql` and
`data/rag/fixtures/seed.sql`, then exercising the version filter, ACL
enforcement (deny and allow cases), the bilingual French boost, and the
staleness penalty against real rows. This caught a genuine bug:
`app/db.py`'s asyncpg pool never registered a `jsonb` type codec, so
`metadata` came back as a raw string and `app/search.py:_row_to_doc`'s
`dict(row["metadata"])` would have raised on the first real request
against a live database - fixed by registering a `jsonb` codec in
`db.py`'s new `_init_connection`. This isn't a standing, repeatable test
(no fixture container is wired into any `make` target) -
`tests/test_search_filters.py` above is what runs repeatably.
