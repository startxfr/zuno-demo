# WP-067: Weekly SXA corpus as a new RAG domain (promotes ADR-0217)

- **State:** **Abandoned 2026-08-26** — superseded by ADR-0219/WP-084. Part A
  merged 2026-08-21 and Part B was live-verified 2026-08-23, but the domain
  it created (`knowledge.sxa`) duplicated `knowledge.sxa-legacy` over the
  same bucket and the same bytes, so ADR-0219 retired it and kept one domain.
  Its real contribution survives: the pure-Python mysqldump parser it built
  for `fetch-sxa` is now `load-sxa-dump`'s implementation, and the access it
  granted Advantage and Finage was preserved by widening
  `knowledge.sxa-legacy`'s `allowed_groups`. Retained as a historical record;
  do not execute this brief.
- **Superseded by:** [WP-084](wp-084-retire-the-sxa-mcp-path-and-second-rag-domain.md)
- **ADRs:** ADR-0217 (Superseded by ADR-0219) (To be implemented -> Partially implemented, amended
  2026-08-23); related to but does not modify ADR-0216/WP-065
- **Depends on:** none (independent of WP-065/WP-23's own open operator work)
- **Blocks:** nothing - `knowledge.sxa-legacy` and its tests are untouched
- **Estimated files touched:** ~20

> Execute this brief as a standalone task from the repository root. Read
> ADR-0217 in full before editing - it's the source of truth for every
> decision below. Part A is pure repo work (chart/code/docs/tests, no real
> export or bucket needed); Part B is operator-only.

## Goal

Give Comage, Advantage, and Finage weekly-refreshed RAG access to an
SXA commercial corpus (`sxa.schema.sql` + `sxa.data.sql`,
mysqldump format), without building or depending on a MariaDB import or any
new MCP tool - RAG-only, distinct from `knowledge.sxa-legacy`
(ADR-0216/WP-065).

## ADR references

Primary: [docs/adr/0217-ingest-a-weekly-sxa-corpus-as-a-new-rag-domain.md](../../adr/0217-ingest-a-weekly-sxa-corpus-as-a-new-rag-domain.md) -
read all 5 Decision clauses and the Security considerations section (the
"trust the source as-is" posture is a named, explicit
trade-off, not an oversight).

Related: ADR-0216/WP-065 (the related-but-distinct MariaDB-backed effort -
this WP does not modify it), ADR-0202/ADR-0203/ADR-0204 (logical knowledge
domains, policy-intersection authorization, multi-domain RAG platform), ADR-0206
(sales/SXA domain-separation precedent this extends), ADR-0326 (Comage/
Advantage/Finage's existing cross-domain authorization boundaries - Advantage's
and Finage's exclusion from `knowledge.sxa-legacy` stays intact; this WP adds a
new, separate grant rather than touching that boundary), ADR-0340 (the
access-intent matrix `knowledge.sxa`'s `allowed_groups` should be read
alongside, without editing that matrix's existing sxa-legacy row).

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` and
  `python3 platform/docs/check_knowledge_refs.py` both exit 0.
- Read: `knowledge/sxa-legacy/domain.yaml` and
  `gitops/charts/rag-ingestion/values.yaml`'s `domains.sxa-legacy` block (the
  patterns being deliberately NOT reused - MariaDB import, on-demand
  schedule, sales/board-only access); `components/rag-ingestion/src/
  rag_ingestion.py`'s `_fetch_salesforce` (the plain-adapter
  shape `fetch-sxa` follows; `_fetch_aramis` was the other example until
  ADR-0218 removed it on 2026-08-26) and `_split_sql_statements` (the quote-aware
  parsing idiom `fetch-sxa`'s own parser extends); `gitops/charts/rag-ingestion/
  files/pipeline.py.tpl` in full (CONFIG_KEYS/SOURCE_SECRETS wiring a new
  domain must extend in two places or a key silently drops - the
  `mcp-gateway-test-venv`-adjacent "CONFIG_KEYS fix" precedent this repo has
  already hit once).

## Repo changes (step by step)

### Part A - repo work, no real export/bucket needed

1. **Knowledge domain**: `knowledge/sxa/domain.yaml` (new) - `id:
   knowledge.sxa`, weekly freshness objective (not on-demand),
   `exempt_from_freshness_enforcement: false` (unlike sxa-legacy). A `sxa:`
   block added to `knowledge/metadata-schema.yaml`'s `domains:` section,
   mirroring sxa-legacy's taxonomy fields.
2. **Policy + binding**: `policies/knowledge/knowledge-policy.yaml` gains a
   `knowledge.sxa` entry, `allowed_groups: [sales, board, adv, finance]`,
   `min_classification: C3`. `platform/bindings/knowledge/bindings.yaml`
   gains a `knowledge.sxa -> rag-sxa` entry (`RAGSXA` credential prefix).
3. **Postgres database**: `gitops/charts/postgresql/values.yaml`'s
   `ragSxaDatabase` block (owner `ragsxa`, database `rag-sxa`), wired into
   `templates/postgrescluster.yaml`'s `spec.users`,
   `templates/configmap-init-sql.yaml`'s one-time `CREATE EXTENSION
   vector`/`GRANT` block, and a new
   `templates/externalsecret-ragsxa.yaml` mirroring
   `externalsecret-ragsxalegacy.yaml`.
4. **rag-service wiring**: `gitops/charts/rag-service/values.yaml`'s
   `knowledgeDomains` list gains a `sxa` entry (`enabled: false` until the
   operator provisions credentials, same as every other new domain) - no
   template changes needed, that chart's ExternalSecret/Deployment/
   schema-apply templates already range generically over this list.
5. **Source adapter**: `fetch-sxa` in `components/rag-ingestion/src/
   rag_ingestion.py` - `_parse_create_table_columns()` (extracts column
   order per table from `schema.sql`, skipping `PRIMARY KEY`/`KEY`/
   `CONSTRAINT`/etc. table-level definitions), `_parse_insert_rows()`
   (yields `(table, row_dict)` from `data.sql`'s `INSERT ... VALUES`
   statements via a quote-aware, paren-depth-aware tokenizer -
   `_split_top_level`/`_split_row_tuples`/`_convert_sql_literal`), and
   `_fetch_sxa()` tying it together: fetch both files from the dedicated
   bucket, parse, render via the existing `_render_record_text`, emit one
   raw record per row stamped `domain: knowledge.sxa` - untouched,
   trusted as-is (2026-08-23 amendment: no PII scan either). No SQL
   engine, ephemeral or persistent, is involved anywhere in this path.
6. ~~**Audit function**: `sxa_anonymize.py` gains
   `audit_pii_patterns()`~~ **Superseded 2026-08-23**: removed entirely,
   along with the rest of `sxa_anonymize.py` (WP-065's own amendment
   dropped its enforcing path the same day, leaving the module with no
   caller at all).
7. **Chart wiring**: `gitops/charts/rag-ingestion/values.yaml`'s
   `domains.sxa` entry (`fetchStages: [fetch-sxa]`, its own
   `sxaCorpus.s3` block - a bucket dedicated to this source, distinct from
   both the shared corpus bucket and sxa-legacy's own dedicated
   `sxaDump` bucket - `postgres.database: rag-sxa`,
   `schedule: {enabled: true, cron: "0 0 4 * * 0"}`). `templates/
   domain-configmaps.yaml` and `templates/external-secrets.yaml` gain
   `if $domain.sxaCorpus` blocks emitting `SXA_CORPUS_*` env vars and the
   bucket-credential ExternalSecret. `files/pipeline.py.tpl` gains the
   `SXA_CORPUS_*` `CONFIG_KEYS` entries, a `fetch_sxa` component, and a
   `SOURCE_SECRETS` entry for its bucket credential (the plain one-secret
   pattern salesforce uses, not the two-secret `SXA_SOURCE_SECRETS`
   pattern sxa-legacy needs for its extra MariaDB credential).
8. **Agent access**: `agents/comage/tasks/compare-historical-deals.md`,
   `agents/advantage/tasks/answer-project-question.md`, and
   `agents/finage/tasks/answer-finance-question.md` each gain
   `knowledge.sxa` in `allowed_knowledge`. `agents/cognos/tasks/
   review-historical-commercial-data.md` (new) declares
   `allowed_knowledge: [knowledge.sxa]` - Cognos's `agent.okf.md` gains it
   in its `tasks:` list, but this grant is inert: Cognos has no gitops
   chart/Application/running workflow (`status: placeholder`,
   `agents/cognos/NEXT_STEPS.md`), so nothing serves it until a separate
   future promotion. `knowledge.sxa-legacy`'s existing `allowed_knowledge`
   entries and WP-35's negative test for Advantage are untouched.
9. **Tests**: `components/rag-ingestion/tests/test_source_adapters.py`
    gains fixture-driven coverage for `_parse_create_table_columns`,
    `_parse_insert_rows` (quoted commas, escaped quotes, `NULL`), the
    `fetch-sxa` adapter end-to-end (one record per row, idempotent
    re-import, refuses missing keys/non-schema content) and
    `audit_pii_patterns` (flags without mutating). All run via the
    component's own venv (`mcp-gateway-test-venv`-style precedent).

### Part B - operator steps (not executable by the model)

1. ~~Create the dedicated SXA corpus S3 bucket~~ DONE 2026-08-21:
   `zuno-demo-sxa-corpus` (eu-west-2), `sxa.schema.sql`/`sxa.data.sql`
   uploaded, IAM user `zuno-sxa-corpus-s3` scoped to this bucket.
2. ~~Upload the approved weekly export; set the real S3 keys~~ DONE
   2026-08-21, folded into step 1 above.
3. ~~Seed Vault, create the `rag-sxa` Postgres database, flip
   `domains.sxa.enabled: true` and sync~~ DONE, confirmed live
   2026-08-23: `rag-sxa-corpus-s3`/`rag-postgres-sxa` ExternalSecrets
   synced, `zuno-postgresql-pguser-ragsxa` Secret exists,
   `domains.sxa.enabled: true` in both `rag-ingestion` and `rag-service`.
4. ~~Extend `compile_pipeline_version.yml`'s domain loop to compile `sxa`~~
   DONE, confirmed live 2026-08-23: `_rag_ingestion_compile_targets`
   includes `sxa`, and a `PipelineVersion` (`v0-3-0-sxa`) exists in
   `zuno-ai-build`.
5. Run the ingestion pipeline once; confirm real rows land in
   `document_embeddings` (row count, not just "the Job succeeded"). **In
   progress as of 2026-08-23**: a workflow
   (`rag-corpus-ingestion-sxa-65wsz-1-*`) was running at last check, ~2h
   after start, following an earlier attempt that errored 42h before that
   - confirm this run's outcome (and if it also failed, check why the
   prior one errored before retrying blind).
6. Confirm the weekly schedule ConfigMap was picked up by
   `ansible/roles/rag_ingestion/tasks/install.yml`'s recurring-run
   reconciliation (`oc get configmap -l zuno.io/rag-ingestion-schedule=true`,
   then the KFP recurring run itself).
7. Spot-check retrieval as Comage/Advantage/Finage (real or fixture
   Keycloak users with the matching business roles) and confirm a user
   without `sales`/`board`/`adv`/`finance` cannot retrieve `knowledge.sxa`
   content.
8. Re-run a second time against an unchanged export; confirm
   `document_embeddings` row count and `updated_at` are unchanged
   (idempotent no-op).

## What NOT to touch

- `knowledge/sxa-legacy/domain.yaml`, `gitops/charts/rag-ingestion/values.yaml`'s
  `domains.sxa-legacy` block, `components/rag-ingestion/src/rag_ingestion.py`'s
  `_load_sxa_dump`/`_import_sxa_dump_native`/`_mariadb_connect` - WP-065's
  own path, unaffected by this WP (though both WPs' 2026-08-23 amendments
  landed the same day and both touch `rag_ingestion.py`).
- `policies/knowledge/knowledge-policy.yaml`'s existing `knowledge.sxa-legacy`
  entry and `policies/tools/tool-policy.yaml`'s `sxa.*` capabilities -
  unchanged; this WP adds a new domain, never edits an existing one's
  `allowed_groups`.
- `agents/advantage/**` beyond the one `allowed_knowledge` addition -
  Advantage's exclusion from `knowledge.sxa-legacy` (ADR-0326, WP-35) is not
  touched or reversed.
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `helm lint`/`helm template` on `postgresql`, `rag-ingestion`, and
  `rag-service` charts.
- Component test suite (own venv) for `rag_ingestion.py` -
  `tests/test_source_adapters.py`, `tests/test_reconcile_acls.py`.
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`.
- `python3 platform/docs/check_knowledge_refs.py` → `RESULT: PASS`.
- `python3 platform/okf/generate_authorization_matrix.py` regenerates
  Comage/Advantage/Finage/Cognos's `agent.okf.md` authorization matrices
  cleanly (no manual edits to the generated block).

## Operator / human follow-up

See Part B above in full - every step there is operator-only.

## Status updates (then re-run check_docs.py)

- After Part A merge: ADR-0217 → `Partially implemented (knowledge.sxa
  domain/policy/binding wiring, fetch-sxa adapter, weekly schedule, agent
  access grants, and tests merged; dedicated bucket/real export and live
  verification pending)`; index row to match; tracker → `Operator pending`;
  this file's State.
- After Part B: ADR-0217 → `Implemented`; index row `Implemented`; tracker →
  `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- A MariaDB import or any new MCP deterministic-lookup tool for this source
  - the user chose RAG-only; revisit only via a new ADR if a live-lookup
    need for this specific corpus emerges later.
- Converging `knowledge.sxa` and `knowledge.sxa-legacy` into one domain -
  ADR-0217 explicitly keeps them separate; a future ADR could revisit this.
- Promoting Cognos out of `status: placeholder` - its `knowledge.sxa` grant
  is declared and ready but inert until a separate future WP does that
  promotion (gitops chart, Application, evaluations skeleton, ADR-0502
  Stage-1 -> Stage-2 checklist).
- The write-request gate for any future SXA write capability - WP-068.
