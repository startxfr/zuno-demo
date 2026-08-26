# WP-065: Real SXA content via S3 → MariaDB, served through MCP and RAG (promotes ADR-0216)

- **State:** **Abandoned 2026-08-26** — superseded by ADR-0219/WP-084. Part A
  merged 2026-08-21 and the 2026-08-23 amendment merged, but Part B's live
  steps never ran, and the decision they were promoting has been withdrawn:
  SXA is a closed pre-2021 record served through retrieval only, so the
  MariaDB structured store and the `sales-db` MCP tool surface this WP built
  are deleted rather than completed. The `load-sxa-dump` stage survives,
  reimplemented without MariaDB. Retained as a historical record of what was
  built and why it was dropped; do not execute this brief.
- **ADRs:** ADR-0216 (Superseded by ADR-0219)
- **Superseded by:** [WP-084](wp-084-retire-the-sxa-mcp-path-and-second-rag-domain.md)
- **Depends on:** WP-23 (repo work merged — policy/tooling/metadata-separation this WP extended)
- **Estimated files touched:** ~12 (Part A) + ~10 (2026-08-23 amendment)

> Execute this brief as a standalone task from the repository root. Read
> ADR-0216 in full (including its 2026-08-23 Amendment section) before
> editing — it's the source of truth for every decision below.

## Goal

Give `knowledge.sxa-legacy` real data for the first time: import a real
mysqldump-format SXA dump (S3-hosted, new dedicated bucket) natively into
a new MariaDB database, serve exact lookups through the existing
`sales-db` MCP server (engine-select mode), and serve semantic
chunks through the existing RAG pipeline — replacing the current
raw-DDL-chunking placeholder.

## ADR references

Primary: [docs/adr/0216-import-real-sxa-content-via-s3-into-mariadb-served-through-mcp-and-rag.md](../../adr/0216-import-real-sxa-content-via-s3-into-mariadb-served-through-mcp-and-rag.md) —
read all 5 Decision clauses and the Security considerations section (the
content gate is a named operator review, not implicit).

Related: ADR-0016 (superseded, live-target clause only — Postgres fixture
path stays), ADR-0206 (sales/SXA domain separation this extends), ADR-0017
(MCP-only, no raw SQL), ADR-0352 (the `embeddedMariaDB`/`externalMySQL`
mode-switch precedent this mirrors), ADR-0021/ADR-0035 (C1/C2/C3,
local-only — unchanged, not relaxed).

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `gitops/charts/mariadb/templates/database-mlops.yaml` (the exact
  `Database`/`User`/`Grant` pattern to mirror for a new `sxa` database);
  `gitops/charts/mariadb/values.yaml` (Vault path conventions);
  `gitops/charts/rag-ingestion/values.yaml`'s `sxa-legacy` domain block
  and the top-level `postgres`/S3 blocks (the bucket-wiring pattern to
  mirror for the new bucket); `components/rag-ingestion/src/
  rag_ingestion.py:906-995` (`load-sxa-dump`'s current placeholder
  implementation, to be replaced); `components/mcp-servers/sales-db/
  server.py` in full (the tool set and access-control pattern to extend,
  not rewrite); `data/sxa/schema/001_init.sql` (the schema the redaction
  column-map must cover completely).

## Repo changes (step by step)

### Part A — repo work, no real dump/bucket needed

Historical record of the 2026-08-21 merge. Items 2, 4 and 5 were
superseded by the 2026-08-23 amendment (reused bucket instead of a
dedicated one; no redaction module at all) — see ADR-0216's Amendment
section and this file's State line above for what actually shipped.

1. **MariaDB database wiring**: `gitops/charts/mariadb/templates/database-sxa.yaml`
   (new), mirroring `database-mlops.yaml` exactly — `Database`/`User`/
   `Grant` CRDs for a new `sxa` logical database on the existing shared
   instance. New Vault path + ExternalSecret for its credentials,
   matching the existing `mlops`/`mlpipeline` pattern. (Unaffected by the
   amendment — still current.)
2. ~~**S3 bucket wiring**: a dedicated SXA dump bucket~~ **Superseded**:
   no dedicated bucket was ever created; the amendment reuses WP-067's
   `zuno-demo-sxa-corpus` bucket/credentials instead.
3. **Native MariaDB import stage**: extend or replace `load-sxa-dump` in
   `components/rag-ingestion/src/rag_ingestion.py` — fetch the dump,
   load it directly into the new MariaDB `sxa` database (a raw SQL-file
   execution against the mariadb driver, no per-table regex
   splitting/truncation). Idempotent per snapshot id. (Amended
   2026-08-23: fetches a `schema.sql`+`data.sql` key pair from the reused
   bucket rather than one combined-mysqldump key.)
4. ~~**Anonymization module**: `components/rag-ingestion/src/sxa_anonymize.py`~~
   **Superseded**: removed entirely 2026-08-23. Content flows through
   unmodified.
5. ~~**Real-content extraction for RAG**: runs it through
   `sxa_anonymize.py`~~ **Superseded**: the extraction stage still feeds
   `normalize → chunk → embed → index-pgvector`, but with no redaction
   step in front of it.
6. **`sales-db` engine-select mode**: `components/mcp-servers/sales-db/server.py`
   gains `SXA_DB_ENGINE=postgres|mariadb` (default `postgres`, no
   behavior change until the operator sets it), switching only the
   connection/driver — every tool, its parameterized-query shape, and its
   `allowed_groups`/`min_classification` gate in `policies/tools/
   tool-policy.yaml` stay exactly as they are. (Unaffected by the
   amendment — still current. The chart wiring to actually turn this mode
   on, `gitops/charts/mcp-sales-db/`, was added by the 2026-08-23
   amendment; `server.py` itself always supported it.)
7. **Tests**: fixture-driven unit tests for the MariaDB import path
   (mocked driver, real SQL-file fixture) and `sales-db`'s engine switch
   (both modes return the same shape against equivalent fixture data) —
   follow each component's existing test conventions (own venv per
   `mcp-gateway-test-venv`-style precedent). (Amended 2026-08-23:
   `test_sxa_anonymize.py` deleted along with the module; redaction
   assertions flipped to pass-through assertions.)

### Part B — live steps (2026-08-23 amended scope)

The bucket, MariaDB `sxa` database credentials, and S3 credentials are
already provisioned (reused from WP-067 — no new bucket, no new Vault
seeding needed). What's left is deploying the amended code and running it:

1. `make day2 build rag-ingestion` (image must be rebuilt — `_load_sxa_dump`
   changed; push to `origin/main` first, BuildConfig clones from there).
2. `make d1 install rag-ingestion` (re-render ConfigMap/values for the
   now-`enabled: true` `sxa-legacy` domain) and `make d1 install
   mcp-sales-db` (deploy the new `SXA_DB_ENGINE=mariadb` wiring — no image
   rebuild needed, `server.py` already supported this mode).
3. Run the `compile_pipeline_version` ansible task (now includes
   `sxa-legacy` in its compile targets) to create its PipelineVersion CR.
4. Trigger an on-demand `load-sxa-dump` run (ADR-0105: no schedule, manual
   only).
5. Confirm real rows landed in MariaDB (`SHOW TABLES`/`SELECT count(*)`
   per table in `mariadb-0`, not just "the Job succeeded").
6. Confirm `sales-db` MCP tools (`get_customer`, `aggregate_revenue_by_year`,
   `lookup_record`) return content via a live call through `mcp-gateway`.
7. Confirm `knowledge.sxa-legacy` chunks landed in `rag-sxa-legacy`
   Postgres; re-run WP-23's original live acceptance pass (role-denial
   check with the already-confirmed-real Keycloak users
   `sales-role-only-user-01`/`board-role-only-user-01`/etc.) against the
   now-live data.

## What NOT to touch

- `data/sxa/schema/*.sql`, `data/sxa/fixtures/seed.sql` — the Postgres
  dev/CI fixture path stays as-is, unaffected by this WP.
- `policies/tools/tool-policy.yaml`'s existing `sxa.*` entries'
  `allowed_groups`/`min_classification` values — unchanged, only the
  connection target behind them changes.
- The uncommitted ADR-0344 change set, if still present — standard list.
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `helm lint`/`helm template` on `mariadb`, `rag-ingestion`, `mcp-sales-db`,
  and `rag-service` charts.
- Component test suites (own venv per component) for `rag_ingestion.py`'s
  `load-sxa-dump` adapter and `sales-db`'s engine switch — all
  fixture-driven, no real dump needed.
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`.

## Operator / human follow-up

See Part B above — live cluster steps (build, deploy, trigger, verify).

## Status updates (then re-run check_docs.py)

- After Part B live steps complete: ADR-0216 → `Implemented - see
  gitops/charts/mariadb/, gitops/charts/mcp-sales-db/,
  components/rag-ingestion/src/rag_ingestion.py.`; index row
  `Implemented`; tracker → `Done`; MEMORY.md dated bullet noting the
  2026-08-23 amendment (reused bucket, no redaction); WP-23's brief
  updated to reflect its operator action was discharged here.

## Out of scope / deferred

- A dedicated (non-shared) MariaDB instance for SXA — the user chose the
  shared-instance option; revisit only if isolation needs later outweigh
  the operational simplicity of one shared operand.
- Any change to `knowledge.sxa-legacy`'s `allowed_groups`/
  `min_classification` policy values (a separate, field-level data-review
  decision ADR-0206 already deferred).
- A genuinely separate raw dump / dedicated bucket for this domain — the
  2026-08-23 amendment reuses WP-067's corpus instead; revisit only if a
  real raw dump becomes available and the operator wants to restore
  ADR-0216's original real-value/redacted-RAG split.
