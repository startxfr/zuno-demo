# ADR-0216: Import real SXA content via S3 into MariaDB, served through MCP and anonymized RAG

- **Status:** To be implemented
- **Target:** v0.2
- **Date:** 2026-08-21
- **Decision owners:** Zuno Demo architecture team

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

2. **The real SXA S3 dump lives in its own bucket, separate from the
   shared corpus bucket** (`zuno-demo-rag-corpus`) that holds Confluence/
   Redhat-docs/model content. This repo provisions no AWS infrastructure
   (no Terraform, no AWS Ansible collections — every existing bucket,
   including the corpus one, is operator-pre-created); the new bucket's
   name/region and Vault-sourced access credentials are wired the same
   way, left as explicit placeholders until the operator supplies real
   values and creates the bucket.

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

4. **RAG consumption is real but anonymized-first.** The current
   `load-sxa-dump` fetch stage (`components/rag-ingestion/src/
   rag_ingestion.py`) is a placeholder that regex-splits the dump into
   raw, truncated DDL/INSERT text and chunks *that* — never exercised
   against real content because none existed. It is replaced with a
   stage that extracts real per-record semantic text from the imported
   MariaDB tables, passes it through a new, explicit, **schema-aware
   deterministic redaction step** (`components/rag-ingestion/src/
   sxa_anonymize.py` — a fixed map of known PII-bearing columns, e.g.
   `customers.contact_name`/`email`/`phone`, to pseudonymized/redacted
   values; not a heuristic NER scanner, since the schema is fully known
   and this keeps the transform auditable), and only then chunks/embeds
   the anonymized result into `knowledge.sxa-legacy`'s pgvector index.
   Real values never enter vector space; the MCP path above is what
   carries them, under its existing access control.

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

Real SXA record values reach agent context only through the
access-controlled, parameterized MCP path (ADR-0017), gated by
`allowed_groups`/`min_classification` per tool exactly as today. Anything
that reaches the shared vector index is anonymized first — this is a
stricter posture than ADR-0206 required (which only classified the whole
domain C3), because embeddings are effectively permanent and harder to
scope per-query than a live SQL grant. C3 classification continues to
keep both paths local-model-only (ADR-0021/ADR-0035); this ADR does not
relax that. The real dump file itself never enters git (ADR-0025) and
lives only in the new S3 bucket and the MariaDB database it's imported
into. `sxa_anonymize.py`'s column map must be reviewed against the real
schema before the operator loads real data — an incomplete map is a
silent PII leak into vector space, not a fail-closed error, so this
review is a named operator gate, not an implicit assumption.

## Operational considerations

Each import remains a versioned snapshot (import timestamp, checksum/
provenance, validation report — ADR-0206's existing requirement,
unchanged). Re-running the import or the anonymized-RAG pass must stay
idempotent. The `sales-db` engine-mode switch and the MariaDB database
are independent of each other's rollout — the operator can load MariaDB
data before flipping `sales-db`'s mode, giving a window to verify the
import before it's agent-facing.

## Acceptance criteria

- A real mysqldump loads natively into the new MariaDB `sxa` database
  with no schema-translation step.
- `sales-db` in `mariadb` mode answers `get_customer`/
  `aggregate_revenue_by_year`/`lookup_record` with real values, gated by
  the same `allowed_groups`/`min_classification` policy as today.
- RAG-embedded `knowledge.sxa-legacy` chunks derived from real records
  never contain unredacted values for the columns `sxa_anonymize.py`
  declares as PII-bearing (spot-checked, not merely asserted).
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
