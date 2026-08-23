# ADR-0216: Import real SXA content via S3 into MariaDB, served through MCP and anonymized RAG

- **Status:** Partially implemented (WP-065 Part A merged 2026-08-21; **amended 2026-08-23** — see Amendment below — reusing ADR-0217's corpus bucket, no anonymization transform; chart wiring for MariaDB-mode `sales-db` and live verification pending)
- **Target:** v0.2
- **Date:** 2026-08-21
- **Decision owners:** Zuno Demo architecture team

## Amendment (2026-08-23)

Two operator decisions supersede clauses 2 and 4 below before Part B ever
ran:

1. **No separate raw dump exists.** Rather than wait on a dedicated
   bucket/dump, WP-065 reuses ADR-0217/WP-067's already-anonymized
   `zuno-demo-sxa-corpus` bucket (`sxa.schema.sql`/`sxa.data.sql`) as its
   source. The MariaDB import and the `sales-db` MCP tools therefore serve
   the same as-is content RAG does — not genuinely real/unredacted values,
   as clause 3 originally intended. This is a deliberate scope reduction,
   not a silent gap: there is currently no raw dump anywhere in this
   environment.
2. **The `sxa_anonymize.py` redaction step (clause 4) is removed
   entirely**, not just relaxed. Both the MCP path and the RAG path now
   index/serve SXA content exactly as it arrives from S3, whatever its
   actual anonymization state — the same trust-the-source posture
   ADR-0217 already used for its own corpus. `min_classification: C3` and
   `allowed_groups: [sales, board]` remain the only real safeguard; there
   is no longer a "vector index only gets anonymized text" claim to make.

## Context

ADR-0206 already separates current Salesforce knowledge (`knowledge.sales`)
from legacy SXA knowledge (`knowledge.sxa-legacy`) and establishes that SXA
is served two ways: deterministic structured-query tools for exact
aggregations, and a semantic RAG index for schema/record questions. What
it did not close is where the *real* data comes from — ADR-0016's
PostgreSQL migration target was built and tested only against synthetic
fixtures (`data/sxa/fixtures/seed.sql`); no real SXA dump has ever existed
in this environment, so neither the structured store nor the RAG index has
ever been proven against real content.

A real SQL dump (schema + data, mysqldump-format — the SXA schema was
always modeled on the real legacy MySQL table names, per ADR-0016's own
"MySQL 5.0-era" framing) is now being prepared. Landing it changes two
things ADR-0016/ADR-0206 didn't have to consider:

- **The dump's native format is MySQL, not PostgreSQL.** ADR-0016 chose
  PostgreSQL as "a migration target" when no real dump existed to migrate
  — reasonable at the time, but it means every real row would need lossy
  schema translation on the way in. A MariaDB-compatible target avoids
  that translation entirely, and this platform already runs MariaDB
  (`gitops/charts/mariadb/`) for Kubeflow Pipelines metadata, including a
  hard-won fix for MySQL's server-first wire protocol fighting Istio's
  sidecar sniffing (`traffic.sidecar.istio.io/excludeInboundPorts: "3306"`
  plus a plaintext `DestinationRule`) that a second logical database on
  the same instance inherits for free.
- **Real records carry real PII**, unlike the synthetic fixtures ADR-0206
  scoped its security considerations around. `knowledge.sxa-legacy` is
  already C3-by-default and local-model-only (ADR-0021/ADR-0035 keep C3
  content off external providers entirely), but nothing in this repo
  today anonymizes or redacts content before it is embedded into a shared
  vector index — a distinct risk from external-model exposure, since a
  vector embedding of raw PII text is harder to retract than a database
  row and offers weaker per-query access control than the existing
  deterministic MCP tools already provide.

## Decision

1. **Live structured store moves to MariaDB; supersedes ADR-0016's
   PostgreSQL-target clause for real data.** A new logical database
   (`sxa`) is added to the existing shared MariaDB instance
   (`gitops/charts/mariadb/`), provisioned the same way `mlpipeline`/
   `mlops` already are — `Database`/`User`/`Grant` CRDs mirroring
   `templates/database-mlops.yaml`, Vault-seeded credentials via
   ExternalSecret. The real mysqldump is imported into it **natively** —
   a direct SQL-file load, no schema re-derivation — versioned/idempotent
   by snapshot id, reusing the `sxaDump.s3Key`/`snapshotId` field shape
   `gitops/charts/rag-ingestion/values.yaml`'s `sxa-legacy` domain block
   already declares. ADR-0016's PostgreSQL schema
   (`data/sxa/schema/001_init.sql`) is **not removed** — it remains the
   local-dev/CI fixture path, exactly the role `embeddedMariaDB` vs.
   `externalMySQL` mode-switching already plays elsewhere in this same
   chart (ADR-0352): synthetic data stays cheap and fast for tests, real
   data lives where it's native.

2. ~~The real SXA S3 dump lives in its own bucket, separate from the
   shared corpus bucket~~ **Superseded by the 2026-08-23 amendment above:**
   the dump lives in ADR-0217/WP-067's dedicated `zuno-demo-sxa-corpus`
   bucket, reused rather than duplicated, since no separate raw dump
   exists. (Original text, for history: the real SXA S3 dump lives in its
   own bucket, separate from the shared corpus bucket
   (`zuno-demo-rag-corpus`) that holds Confluence/Redhat-docs/model
   content. This repo provisions no AWS infrastructure — every existing
   bucket is operator-pre-created; the bucket's name/region and
   Vault-sourced access credentials are wired the same way.)

3. **`components/mcp-servers/sales-db/` gains an engine-select mode**
   (`SXA_DB_ENGINE=postgres|mariadb`, default `postgres`) rather than a
   rewrite: identical tool set (`get_customer`, `aggregate_revenue_by_year`,
   `lookup_record`, etc.), identical parameterized-query-only posture
   (ADR-0017 — no path from LLM-constructed text to SQL), identical
   `allowed_groups`/`min_classification` gates in
   `policies/tools/tool-policy.yaml`. The operator flips the mode once
   real MariaDB data is confirmed loaded. This is the **primary**
   consumption path — deterministic, already access-controlled per call,
   and (per this ADR's security considerations below) the path real
   record values are allowed to flow through unredacted.

4. ~~RAG consumption is real but anonymized-first~~ **Superseded by the
   2026-08-23 amendment above: no redaction step.** The `load-sxa-dump`
   fetch stage (`components/rag-ingestion/src/rag_ingestion.py`) extracts
   real per-record text from the imported MariaDB tables and
   chunks/embeds it into `knowledge.sxa-legacy`'s pgvector index exactly
   as imported — no transform. `sxa_anonymize.py` (which would have done
   schema-aware deterministic redaction) was deleted; there is no longer
   a distinction between what the MCP path and the RAG path carry.

5. **No new agent-side wiring.** `knowledge.sxa-legacy`'s existing policy
   (`allowed_groups: [sales, board]`, `min_classification: C3`) already
   gates this content; any agent with that entitlement — Advantage and
   Comage are the named examples — receives real (MCP) or anonymized
   (RAG) SXA content through the pipelines that already exist, once real
   data replaces the synthetic/placeholder content flowing through them
   today.

## Consequences

The SXA legacy corpus goes from "structurally present, never proven
against real data" to actually usable — both for exact figures (MCP,
real values, access-controlled) and for semantic recall (RAG, anonymized).
The platform gains a second production database engine (MariaDB) for
business content, not just pipeline metadata, but reuses infrastructure
(instance, mesh-exclusion fix, ExternalSecret pattern) rather than
duplicating it. The Postgres-native SXA path stays alive for local
development and CI, so no existing test suite needs to change engines to
keep passing.

## Security considerations

**2026-08-23 amendment:** both the MCP path and the RAG path now carry
SXA content exactly as it arrives from S3 — there is no longer an
anonymization step distinguishing them, and no claim that the vector
index only ever holds redacted text. `allowed_groups`/`min_classification`
gating (ADR-0017's access-controlled, parameterized MCP path;
`knowledge.sxa-legacy`'s policy for RAG) is the sole safeguard for both
paths, same as ADR-0217 already accepted for its own corpus. C3
classification continues to keep both paths local-model-only
(ADR-0021/ADR-0035); this ADR does not relax that. The dump file itself
never enters git (ADR-0025) and lives only in the (reused) S3 bucket and
the MariaDB database it's imported into.

## Operational considerations

Each import remains a versioned snapshot (import timestamp, checksum/
provenance, validation report — ADR-0206's existing requirement,
unchanged). Re-running the import or the anonymized-RAG pass must stay
idempotent. The `sales-db` engine-mode switch and the MariaDB database
are independent of each other's rollout — the operator can load MariaDB
data before flipping `sales-db`'s mode, giving a window to verify the
import before it's agent-facing.

## Acceptance criteria

- The dump (schema.sql + data.sql from the reused ADR-0217 corpus bucket)
  loads natively into the MariaDB `sxa` database with no schema-translation
  step.
- `sales-db` in `mariadb` mode answers `get_customer`/
  `aggregate_revenue_by_year`/`lookup_record` with the imported content,
  gated by the same `allowed_groups`/`min_classification` policy as today.
- RAG-embedded `knowledge.sxa-legacy` chunks derived from the imported
  records match the source content byte-for-byte — no transform applied
  (spot-checked, not merely asserted).
- Users without Sales/Direction legacy authorization still cannot reach
  either path (ADR-0206's existing acceptance bar, re-verified against
  real data).
- The Postgres fixture path continues to pass unchanged for local
  dev/CI.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0016](0016-migrate-the-legacy-sxa-schema-to-postgresql.md) (superseded, live-target clause only)
- [ADR-0017](0017-access-sales-data-through-controlled-mcp-tools.md)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0025](0025-keep-sensitive-and-real-commercial-data-outside-the-public-repository.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- [ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md)
- [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md)
