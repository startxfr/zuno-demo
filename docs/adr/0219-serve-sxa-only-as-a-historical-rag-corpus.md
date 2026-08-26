# ADR-0219: Serve SXA only as a pre-2021 historical RAG corpus

- **Status:** Implemented
- **Target:** v0.2
- **Date:** 2026-08-26
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0216](0216-import-real-sxa-content-via-s3-into-mariadb-served-through-mcp-and-rag.md) and [ADR-0217](0217-ingest-a-weekly-sxa-corpus-as-a-new-rag-domain.md) in full — the MariaDB live structured store, the `sales-db` MCP tool surface, and the second `knowledge.sxa` domain are all abandoned, not deferred.

## Context

ADR-0216 built SXA access on three pillars: a live MariaDB structured store,
a deterministic MCP tool surface over it (`components/mcp-servers/sales-db/`,
the five `sxa.*` capabilities), and a RAG index. ADR-0217 then added a second
domain, `knowledge.sxa`, with its own `fetch-sxa` adapter and weekly cadence.
Both were left partially implemented.

Two facts have since settled the question:

- **SXA is a closed historical record.** It is the company's commercial data
  from before 2021. There is no live SXA system behind it, so there is nothing
  for a deterministic query tool to be authoritative *about* — the exactness
  argument that justified the MCP path (ADR-0017, ADR-0206) presumed a live
  store of record. A frozen dump is a corpus, not a database.
- **The two RAG domains were already reading the same bytes.** Both
  `knowledge.sxa-legacy` (`load-sxa-dump`) and `knowledge.sxa` (`fetch-sxa`)
  fetch `sxa.schema.sql`/`sxa.data.sql` from the same
  `zuno-demo-sxa-corpus` bucket. ADR-0216's originally-planned separate raw
  bucket never existed. The only real difference was the parsing mechanism —
  a MariaDB round-trip versus a pure-Python parse — and the access policy.

Carrying a MariaDB logical database, an MCP server, a Day-2 `sql-schema`
install component and a duplicate vector index to serve one frozen SQL dump
is cost without a corresponding capability.

## Decision

1. **SXA is served through RAG only.** No live SQL content, no MCP tool
   surface, no structured store. Retrieval over the indexed corpus is the
   single access path.

2. **`knowledge.sxa-legacy` is the one surviving domain.** Its identity is
   preserved: source class `sxa-dump`, `sxa-dump://<table>/<id>` record URLs,
   `min_classification: C3`, `exempt_from_freshness_enforcement: true`, and
   the on-demand refresh model (`schedule.enabled: false`,
   `staleAfter: none`). **ADR-0217's weekly cadence is not inherited** — a
   pre-2021 record does not go stale, which is exactly what
   `_IMMUTABLE_LEGACY_DOMAINS` already encodes in
   `components/rag-service/app/search.py` and
   `components/rag-ingestion/src/rag_ingestion.py`.

3. **`knowledge.sxa` is retired**, together with the `fetch-sxa` adapter, the
   `rag-sxa` pgvector database, `knowledge/sxa/domain.yaml`, its physical
   binding and its policy entry. It indexed the same source into a second
   place.

4. **`knowledge.sxa-legacy`'s `allowed_groups` widens to
   `[sales, board, adv, finance]`.** This is the union of what the two
   domains granted, so retiring `knowledge.sxa` costs no agent the reach it
   had: Comage and Cognos keep theirs, and Advantage and Finage keep the
   access ADR-0217 gave them. **This amends [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md)'s
   access-intent table**, whose `knowledge.sxa-legacy` row marked `adv` and
   `finance` as excluded, and it retires WP-35's negative test asserting
   Advantage is denied this domain — that property moved to
   `knowledge.sales`, which still excludes `adv`.

5. **`load-sxa-dump` keeps its name and drops MariaDB.** It now parses the S3
   `schema.sql`/`data.sql` pair in pure Python, reusing the helpers ADR-0217
   introduced for `fetch-sxa` (`_parse_create_table_columns`,
   `_parse_insert_rows`, the sha256 snapshot short-circuit). ADR-0217's
   clause 3 reasoning — mysqldump output is machine-generated and
   well-formed, so no SQL engine is needed — is adopted wholesale as the
   surviving implementation. This also corrects a latent drift: the adapter
   emitted `sxa-mariadb://` URLs and a `sxa-mariadb` source type while
   `knowledge/sxa-legacy/domain.yaml` declared source class `sxa-dump`.

6. **The following are deleted, not deferred:**
   `components/mcp-servers/sales-db/` and its chart, ArgoCD Applications and
   NetworkPolicy; the five `sxa.*` capabilities in
   `platform/bindings/tools/tool-bindings.yaml` and
   `policies/tools/tool-policy.yaml`; the `sql-schema` Day-2 run component
   (`gitops/charts/sql-schema/`, `ansible/roles/sql_schema/`); the
   `data/sxa/` PostgreSQL schema and synthetic fixtures; and the `sxa`
   logical database on the shared MariaDB instance with its Vault seed. The
   MariaDB instance itself stays — it serves Kubeflow Pipelines metadata, and
   its Istio `excludeInboundPorts: "3306"` fix is unrelated to SXA.

7. **[ADR-0016](0016-migrate-the-legacy-sxa-schema-to-postgresql.md) is now
   fully superseded.** ADR-0216 had superseded only its live-target clause,
   leaving the PostgreSQL schema alive as the dev/CI fixture path. With
   `sales-db` gone there is no consumer of that schema in any environment.

8. **No anonymization is claimed on any path.** ADR-0216's and ADR-0217's own
   2026-08-23 amendments had already removed `sxa_anonymize.py` and the
   audit-only scan; this ADR removes the remaining language asserting
   otherwise, including in both superseded ADRs' titles and filenames.
   Access control (`allowed_groups` ∩ agent declaration ∩ task declaration)
   plus `min_classification: C3` is the sole safeguard, as it has been in
   practice since 2026-08-23.

## Consequences

Comage loses exact historical aggregation and Finage loses deterministic
revenue/billing lookups; both are re-grounded on retrieval over the same
underlying records. This is a real capability reduction, accepted knowingly:
the deterministic tools were never proven against real data, and a frozen
corpus cannot support the authoritative-figure claim they made.

The platform sheds a database engine tenant, an MCP server, a Day-2 install
component and a vector index. `sales.*` remains a deliberately vacant
capability namespace reserved for a future live-Salesforce server (ADR-0206),
which is now the only route by which deterministic commercial queries could
return.

**[ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md)'s
two-way SXA access model loses its deterministic half.** Its separation of
`knowledge.sales` from `knowledge.sxa-legacy` stands unchanged; only the
"structured-query tools for exact aggregations" half is withdrawn.

**[ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md)'s mandatory
gateway-bypass acceptance test is retargeted** from `sales-db-mcp` to
`confluence-mcp`, which carries the identical gateway-pod-only NetworkPolicy
and `GatewayTokenMiddleware`. The test is retargeted, not dropped.

## Security considerations

Widening `knowledge.sxa-legacy` to `adv` and `finance` grants no access that
did not already exist — those two groups reached the same content through
`knowledge.sxa`. The net change is a reduction in attack surface: one fewer
MCP server, one fewer database tenant, one fewer credential path, and no
SQL-executing code path anywhere in the SXA chain. `min_classification: C3`
is unchanged and continues to keep SXA content on local models only
(ADR-0021/ADR-0035). The dump never enters git (ADR-0025) and now lives only
in S3 and the pgvector index derived from it.

## Operational considerations

Changing the record URL scheme from `sxa-mariadb://` to `sxa-dump://` changes
every `doc_id`. With `deleteOrphans` and `incremental` both enabled, the next
`load-sxa-dump` run therefore deletes and re-embeds the entire
`rag-sxa-legacy` index — a correct but one-time expensive re-ingestion, not a
steady-state cost.

**That re-ingestion is 314,428 documents** — the dump renders one record per
table row, measured live on 2026-08-26. At that scale it was not merely
expensive but impossible: `normalize`, `chunk`, `embed` and `index-pgvector`
were strictly serial, at one to two S3 round-trips per document. `normalize`
alone was measured at 747 documents/minute (~7h for that stage), the whole
run projected past 30h, and the three real attempts died at 2h08, 5h41 and
6h28. `embed` was the worst of them: its batching loop sat *inside* a single
record, and since the average document is ~1.2 KB against a 320-token budget
almost every document is one chunk — so `EMBEDDING_BATCH_SIZE` was inert and
the stage issued one request per document. Commit `3258a1f` parallelised the
three S3-bound stages on the pool idiom `detect-changes` already used, pooled
`embed`'s chunks *across* documents into full batches, and moved
`index-pgvector` from a commit per document to a commit per window. Four
knobs (`NORMALIZE_CONCURRENCY`, `CHUNK_CONCURRENCY`, `EMBED_CONCURRENCY`,
`INDEX_READ_CONCURRENCY`) tune it per cluster. The projected gain has not yet
been observed end-to-end — no full run has been executed against the new
image.

A second trap this exposed, generic to every domain: `manifest.json` lives in
S3 and survives a database recreation, so `detect-changes` can report zero
changes against an index that is empty. Runs then report `SUCCEEDED` having
written nothing. `rag-sxa-legacy` sits in exactly that state today (0 rows),
as do `rag-sales` and the retired `rag-sxa`. A green pipeline is not evidence
of a populated index; check the row count.

Removing the uninstall paths for `sales-db`, `sql-schema` and the MariaDB
`sxa` database leaves those resources stranded on any already-installed
cluster. WP-084 carries a one-time operator teardown checklist to be run
**before** the deletion commits are deployed.

## Acceptance criteria

- `load-sxa-dump` ingests the S3 dump into `knowledge.sxa-legacy` with no
  database engine involved, emitting `sxa-dump://` URLs.
- No `sxa.*` capability resolves anywhere: absent from tool bindings, tool
  policy, both OKF schemas, and every agent bundle.
- Comage, Cognos, Advantage and Finage each retrieve `knowledge.sxa-legacy`
  content; a caller in none of `[sales, board, adv, finance]` is denied.
- `knowledge.sxa` resolves nowhere, and `rag-sxa` is not provisioned.
- No `sales-db`, `sql-schema`, `data/sxa/` or MariaDB `sxa` artifact remains
  in the repository.
- The full repository gate set passes, including
  `platform/supply-chain/check_mcp_server_conformance.py` at three servers.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0016](0016-migrate-the-legacy-sxa-schema-to-postgresql.md) (fully superseded by this record)
- [ADR-0017](0017-access-sales-data-through-controlled-mcp-tools.md)
- [ADR-0025](0025-keep-sensitive-and-real-commercial-data-outside-the-public-repository.md)
- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md) (bypass test retargeted)
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md)
- [ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md) (deterministic half withdrawn)
- [ADR-0216](0216-import-real-sxa-content-via-s3-into-mariadb-served-through-mcp-and-rag.md) (superseded)
- [ADR-0217](0217-ingest-a-weekly-sxa-corpus-as-a-new-rag-domain.md) (superseded)
- [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md) (access-intent row amended)
