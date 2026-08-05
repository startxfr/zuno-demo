# ADR-0046: Make RAG retrieval metadata-aware and bilingual

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The current RAG direction combines pgvector with PostgreSQL full-text search, but Tekos requirements demand explicit product/version selection, source trust, classification, ACL handling, freshness and both French and English content. Similarity alone can return an incorrect OpenShift version even when the user names a version.

## Decision

Attach normalized metadata to every indexed chunk: product, version, language, source/source_type, classification, ACL/tenant scope where applicable, last_modified, stale_after and provenance. Apply deterministic metadata filters before ranking when the user specifies product/version or policy requires them. Support bilingual retrieval and hybrid vector/full-text ranking.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Tekos can answer version-specific questions more reliably and classification/ACL logic can be enforced at retrieval time.

## Security considerations

Retrieval must never return documents the user cannot access. C2/C3 metadata must propagate into effective classification according to ADR-0034.

## Operational considerations

Add test corpora containing conflicting versions and bilingual content; acceptance tests must prove the requested version is preferred or enforced.

## Implementation state

**Implemented (2026-08-05).** Every field the Decision names lives inside
`document_embeddings`'s existing `metadata jsonb` column (already present,
GIN-indexed, owned by another track's `002_pgvector.sql`) rather than as
new typed columns - `data/rag/schema/003_rag_metadata.sql` documents the
convention (`product`, `version`, `language`, `source_type`,
`classification`, `acl_groups`, `last_modified`, `stale_after`,
`provenance`) and adds expression indexes on the three fields actually
used as hot-path filters. **Tenant scope**: not applicable - this is a
single-tenant demo with no tenant concept anywhere else in the codebase;
`acl_groups` (the ACL half of "ACL/tenant scope where applicable") is
implemented and enforced, see Security considerations below.
`data/rag/fixtures/seed.sql` is a new fictional demo corpus (no such
corpus existed before this ADR - `data/rag/` was an empty stub) seeded by
a new `ansible/roles/rag` task, same one-shot-Job pattern as
`ansible/roles/sql_schema`.

Deterministic filters and bilingual ranking (Decision): `components/rag-service/app/search.py`'s
`_filter_clause` applies exact-match `product`/`version` predicates to
*both* the vector and full-text candidate queries before `LIMIT`, only
when the caller supplied them - `components/agent-runtime/app/graph/nodes.py`'s
new `_extract_product_version` regex (tested in
`components/agent-runtime/tests/test_retrieve_metadata.py`) is what
resolves "OpenShift AI 3.5"/"RHOAI 2.16"-style question text into that
filter, the exact scenario this ADR's Context names. `language` is
deliberately a soft rank boost rather than a hard filter (a small demo
corpus can have zero matches in one language for a given query); bilingual
full-text itself comes from a new generated `content_tsv` column whose
`english`/`french` text-search configuration is chosen per row from
`metadata.language` (the previous hardcoded `to_tsvector('english', ...)`
could never correctly match French content regardless of query language).
Freshness (`stale_after`) doesn't exclude a result but does apply a fixed
rank penalty and is surfaced in the response and the model's own context
block (`app/graph/nodes.py:_build_context_block` now tags each source with
its version/staleness, so the model can actually prefer the right one)
rather than either silently hiding or silently ignoring it.

Security considerations: ACL enforcement (`_filter_clause`'s jsonb `?|`
predicate) is mandatory, not conditional on the caller supplying groups -
an empty `caller_groups` still excludes every ACL-restricted document
(fail closed), never includes one by default. This was verified against a
**real** PostgreSQL 16 + pgvector instance in this phase's development
environment (`podman run pgvector/pgvector:pg16`, contrary to every
earlier phase's "no live database" constraint - this sandbox turned out
to have working container-registry access too): `003_rag_metadata.sql`
and `seed.sql` applied cleanly, and `hybrid_search` was called directly
against real rows proving (1) the version filter excludes the wrong
version, (2) an empty `caller_groups` excludes the ACL-restricted roadmap
doc while `["consultant"]` includes it, (3) a French-boosted query ranks
the French document first, (4) a stale document is down-ranked but still
returned, and (5) `POST /v1/search` over real HTTP returns the same
result. This surfaced and fixed a genuine, previously-latent bug
unrelated to this ADR's own new code: `app/db.py`'s asyncpg pool never
registered a `jsonb` type codec, so `metadata` came back as a raw JSON
string and `_row_to_doc`'s pre-existing `dict(row["metadata"])` call would
have raised `ValueError` on the very first real request against a live
database - never caught before because rag-service had never actually
been run against one. Fixed by registering a `jsonb` codec
(`json.dumps`/`json.loads`) on the pool's `init` callback.
`evaluations/tekos/security_checks.py` was not extended with a live
ACL-negative check in this pass despite the above (that suite targets a
full deployed stack - Keycloak, BFF entitlement, MCP Gateway policy -
none of which this standalone verification stood up); its coverage stays
`components/rag-service/tests/test_search_filters.py`'s SQL-fragment
assertions plus the ad hoc verification described above. Classification
propagation into `effective_classification` (ADR-0034) is implemented in
`retrieve_node`: the highest classification among retrieved docs now
escalates the turn's classification exactly like `tool_call_node` already
did for Confluence, closing that function's own former docstring
admission ("rag-service doesn't carry per-document classification
metadata yet") - also confirmed via the same live-database verification
(`caller_groups=["board"]` against the roadmap query returned
`classification: "C2"`).

Operational considerations ("Add test corpora containing conflicting
versions and bilingual content; acceptance tests must prove the requested
version is preferred or enforced"): `data/rag/fixtures/seed.sql` has two
conflicting-version document pairs (GPU sizing and ServingRuntime config,
OpenShift AI 2.16 vs. 3.5) and an EN/FR pair; the "requested version is
enforced" proof is
`components/agent-runtime/tests/test_retrieve_metadata.py` (the extraction
that drives the deterministic filter) plus
`components/rag-service/tests/test_search_filters.py` (the filter clause
itself, including that it always keys on the exact placeholder index
requested) - both run and passing in this phase's development
environment, no live database needed for either.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0015
- ADR-0109
- ADR-0110
- ADR-0034
- ADR-0035

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
