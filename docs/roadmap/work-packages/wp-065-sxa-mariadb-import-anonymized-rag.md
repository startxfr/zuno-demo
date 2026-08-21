# WP-065: Real SXA content via S3 → MariaDB, served through MCP and anonymized RAG (promotes ADR-0216)

- **State:** Not started
- **ADRs:** ADR-0216 (To be implemented -> Partially implemented -> Implemented); supersedes ADR-0016's live-target clause
- **Depends on:** WP-23 (repo work merged — policy/tooling/metadata-separation this WP extends)
- **Blocks:** WP-23's remaining "real snapshot load" operator action, which now targets this WP instead
- **Estimated files touched:** ~12

> Execute this brief as a standalone task from the repository root. Read
> ADR-0216 in full before editing — it's the source of truth for every
> decision below. Part A is pure repo work (chart/code/tests, no real
> dump or bucket needed); Part B is operator-only.

## Goal

Give `knowledge.sxa-legacy` real data for the first time: import a real
mysqldump-format SXA dump (S3-hosted, new dedicated bucket) natively into
a new MariaDB database, serve exact lookups through the existing
`sales-db` MCP server (engine-select mode), and serve anonymized semantic
chunks through the existing RAG pipeline — replacing the current
raw-DDL-chunking placeholder.

## ADR references

Primary: [docs/adr/0216-import-real-sxa-content-via-s3-into-mariadb-served-through-mcp-and-anonymized-rag.md](../../adr/0216-import-real-sxa-content-via-s3-into-mariadb-served-through-mcp-and-anonymized-rag.md) —
read all 5 Decision clauses and the Security considerations section (the
anonymization gate is a named operator review, not implicit).

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
  not rewrite); `data/sxa/schema/001_init.sql` (the schema the anonymization
  column-map must cover completely).

## Repo changes (step by step)

### Part A — repo work, no real dump/bucket needed

1. **MariaDB database wiring**: `gitops/charts/mariadb/templates/database-sxa.yaml`
   (new), mirroring `database-mlops.yaml` exactly — `Database`/`User`/
   `Grant` CRDs for a new `sxa` logical database on the existing shared
   instance. New Vault path + ExternalSecret for its credentials,
   matching the existing `mlops`/`mlpipeline` pattern.
2. **S3 bucket wiring**: a new block in `gitops/charts/rag-ingestion/values.yaml`
   (or wherever the existing corpus-bucket block lives) for the dedicated
   SXA dump bucket — name/region as explicit, clearly-commented
   placeholders (`# OPERATOR-SUPPLIED — see ADR-0216`), new Vault path for
   its access key/secret, separate from the existing `rag/s3` credential.
3. **Native MariaDB import stage**: extend or replace `load-sxa-dump` in
   `components/rag-ingestion/src/rag_ingestion.py` — fetch the dump from
   the new bucket via `sxaDump.s3Key`/`snapshotId` (unchanged field
   shape), load it directly into the new MariaDB `sxa` database (a raw
   SQL-file execution against the mariadb driver, no per-table regex
   splitting/truncation — that was only ever a workaround for not having
   a real relational target). Idempotent per snapshot id.
4. **Anonymization module**: `components/rag-ingestion/src/sxa_anonymize.py`
   (new) — a fixed, reviewable map of PII-bearing columns (per
   `data/sxa/schema/001_init.sql`: at minimum `customers.contact_name`/
   `email`/`phone`, `contacts.*` equivalents) to a deterministic
   pseudonymization/redaction function. No heuristic scanning — every
   column not in the map passes through unchanged, every column in the
   map is transformed, and an explicit test asserts the map covers every
   PII-shaped column the schema defines (name/email/phone patterns) so a
   newly added column can't silently leak.
5. **Real-content extraction for RAG**: a new stage (or extension of the
   normalize stage) that pulls real per-record text from the MariaDB `sxa`
   database, runs it through `sxa_anonymize.py`, and feeds the result into
   the existing `normalize → chunk → embed → index-pgvector` pipeline
   unchanged — the anonymized text is the only thing that reaches the
   embedding call.
6. **`sales-db` engine-select mode**: `components/mcp-servers/sales-db/server.py`
   gains `SXA_DB_ENGINE=postgres|mariadb` (default `postgres`, no
   behavior change until the operator sets it), switching only the
   connection/driver — every tool, its parameterized-query shape, and its
   `allowed_groups`/`min_classification` gate in `policies/tools/
   tool-policy.yaml` stay exactly as they are.
7. **Tests**: fixture-driven unit tests for `sxa_anonymize.py` (every
   PII-shaped column redacted, everything else untouched), the MariaDB
   import path (mocked driver, real SQL-file fixture), and `sales-db`'s
   engine switch (both modes return the same shape against equivalent
   fixture data) — follow each component's existing test conventions
   (own venv per `mcp-gateway-test-venv`-style precedent).

### Part B — operator steps (not executable by the model)

1. Create the new S3 bucket; supply its name/region and provision Vault
   credentials at the new path this WP's repo work references.
2. Upload the real dump; set `sxaDump.s3Key`/`snapshotId` to the real
   values.
3. Seed the new MariaDB `sxa` database's Vault-sourced credentials
   (mirrors the existing `zuno/mariadb/root` precondition).
4. Run the import; confirm real rows exist in MariaDB (`SELECT count(*)`
   per table, not just "the Job succeeded").
5. Run the RAG ingestion pass; spot-check several embedded chunks against
   their source rows to confirm PII columns are genuinely redacted, not
   merely believed to be.
6. Flip `sales-db` to `SXA_DB_ENGINE=mariadb`; re-run WP-23's original
   live acceptance pass (real-snapshot load-and-verify, role-denial check
   with the already-confirmed-real Keycloak users `sales-role-only-user-01`/
   `board-role-only-user-01`/etc.) against the now-real data.
7. Review `sxa_anonymize.py`'s column map against the real schema one more
   time before this step is called done — per ADR-0216's Security
   considerations, an incomplete map is a silent leak, not a fail-closed
   error.

## What NOT to touch

- `data/sxa/schema/*.sql`, `data/sxa/fixtures/seed.sql` — the Postgres
  dev/CI fixture path stays as-is, unaffected by this WP.
- `policies/tools/tool-policy.yaml`'s existing `sxa.*` entries'
  `allowed_groups`/`min_classification` values — unchanged, only the
  connection target behind them changes.
- The uncommitted ADR-0344 change set, if still present — standard list.
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `helm lint`/`helm template` on `mariadb` and `rag-ingestion` charts.
- Component test suites (own venv per component) for `sxa_anonymize.py`,
  the import stage, and `sales-db`'s engine switch — all fixture-driven,
  no real dump needed.
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`.

## Operator / human follow-up

See Part B above in full — every step there is operator-only.

## Status updates (then re-run check_docs.py)

- After Part A merge: ADR-0216 → `Partially implemented (MariaDB
  database wiring, S3 bucket wiring, native import stage, anonymization
  module, sales-db engine switch, and tests merged; real dump/bucket and
  live verification pending)`; index row to match; tracker → `Operator
  pending`; this file's State.
- After Part B: ADR-0216 → `Implemented - see gitops/charts/mariadb/,
  components/rag-ingestion/src/sxa_anonymize.py,
  components/mcp-servers/sales-db/server.py.`; index row `Implemented`;
  tracker → `Done`; MEMORY.md dated bullet; WP-23's brief updated to
  reflect its operator action was discharged here.

## Out of scope / deferred

- A dedicated (non-shared) MariaDB instance for SXA — the user chose the
  shared-instance option; revisit only if isolation needs later outweigh
  the operational simplicity of one shared operand.
- Anonymizing/masking values in the MCP path itself — the user chose to
  keep it as the real-value, access-controlled path; a future ADR could
  revisit this if entitlement scope ever broadens beyond Sales/Direction.
- Any change to `knowledge.sxa-legacy`'s `allowed_groups`/
  `min_classification` policy values (a separate, field-level data-review
  decision ADR-0206 already deferred).
