# ADR-0217: Ingest a weekly, already-anonymized SXA corpus as a new RAG domain

- **Status:** Partially implemented (repo work merged 2026-08-21: `knowledge.sxa`
  domain/policy/binding wiring, `fetch-sxa` source adapter, weekly schedule,
  agent access grants; real dedicated bucket and live verification pending)
- **Target:** v0.2
- **Date:** 2026-08-21
- **Decision owners:** Zuno Demo architecture team

## Context

A second SXA source has arrived, distinct from ADR-0216/WP-065's: an
operator-supplied mysqldump (`sxa.schema.sql` + `sxa.data.sql`) that is
**already anonymized upstream**, intended to refresh weekly and be readable by
Comage, Advantage, and Finage (Cognos once it exists as a real deployment).

ADR-0216 built `knowledge.sxa-legacy` for a different, deliberately narrower
case: a raw, unredacted dump that needs this platform's own
`sxa_anonymize.py` transform before anything reaches the vector index, a live
MariaDB import for exact-lookup MCP tools, `sales`/`board`-only access
(ADR-0340's access-intent matrix explicitly excludes `finance`/`cdp`), and an
immutable, on-demand-only refresh model (no scheduled cadence — "the source is
a point-in-time dump snapshot, not a live system", `knowledge/sxa-legacy/
domain.yaml`).

None of those constraints fit this new source: it needs no transform (already
anonymized), no live MariaDB/MCP path (RAG-only), broader access (Comage,
Advantage, Finage), and a real weekly cadence. Reusing `knowledge.sxa-legacy`
would mean either weakening its existing, tested security posture (WP-35's
passing negative test denies Advantage; ADR-0340's table denies finance) or
silently redefining what that domain means underneath WP-065's separate,
still-open effort.

## Decision

1. **A new logical domain, `knowledge.sxa`, is introduced** —
   `knowledge/sxa/domain.yaml` (ADR-0202), independent of and untouched by
   `knowledge.sxa-legacy`. Both domains may coexist indefinitely; there is no
   plan to merge them, since they answer different provenance/trust
   questions (this platform's own redaction vs. an upstream-supplied
   anonymized export).

2. **No transform stage — audit only.** The upstream dump is treated as
   already safe to index. `components/rag-ingestion/src/sxa_anonymize.py`
   gains an additive `audit_pii_patterns()` function (distinct from the
   existing `redact_row()`/`redact_value()` WP-065 uses) that scans
   PII-shaped values against the same `PII_COLUMNS` map and logs a warning —
   it never alters or blocks a value. This is insurance against the upstream
   anonymization missing something, not an enforcement gate: unlike
   ADR-0216's stricter posture (real record values, redaction is mandatory
   before embedding), this decision is that the caller's assertion that the
   dump is pre-anonymized is trusted.

3. **RAG-only — no MariaDB, no MCP tools.** The new `fetch-sxa` source
   adapter parses `sxa.schema.sql` (for column order per table) and
   `sxa.data.sql` (for `INSERT` row values) directly in Python — no SQL
   engine involved, ephemeral or persistent. mysqldump output is
   machine-generated and well-formed (the same assumption
   `_split_sql_statements`'s docstring already states elsewhere in this
   file), so a quote-aware `INSERT ... VALUES (...), (...);` parser is
   sufficient without a database round-trip. This keeps the domain's
   infrastructure footprint to S3 + pgvector only — no new database engine,
   no agent-facing write-capable tool of any kind.

4. **Weekly schedule, generic incremental updates.** `domains.sxa.schedule`
   ships `enabled: true` from the start (unlike `sxa-legacy`, which
   deliberately never schedules). No new change-detection code is needed:
   `stage_detect_changes`'s existing S3-manifest sha256 diff, generic across
   every domain, already re-embeds only rows that changed between runs and
   no-ops on an unchanged weekly snapshot.

5. **Access: Comage, Advantage, Finage now; Cognos declared but inert.**
   `policies/knowledge/knowledge-policy.yaml`'s new `knowledge.sxa` entry
   lists `allowed_groups: [sales, board, adv, finance]` — covering all four
   agents' business roles. Comage's, Advantage's and Finage's existing tasks
   gain `knowledge.sxa` in `allowed_knowledge`. Cognos has no running
   deployment at all (`status: placeholder`, no gitops chart or Application
   — `agents/cognos/NEXT_STEPS.md`); its first real task file is created
   with `allowed_knowledge: [knowledge.sxa]` per that file's own step 3
   ("add policy entries... when real tasks are authored"), but this grant is
   inert until a separate future ADR/WP promotes Cognos out of placeholder.

## Consequences

Two independently-evolving SXA knowledge sources now exist side by side —
`knowledge.sxa-legacy` (this platform's own redaction, narrow access,
on-demand) and `knowledge.sxa` (upstream-anonymized, broader access, weekly).
Neither WP-065/ADR-0216's tests nor its own eventual live completion are
affected by this decision. A future decision to converge them, or to extend
this domain's access/schedule model, needs its own ADR — this one does not
pre-commit to either.

## Security considerations

Trusting an upstream anonymization claim is a real posture change from
ADR-0216's (which trusts nothing and redacts deterministically before
embedding) — this decision accepts that trade explicitly, for this source
only, with the audit-only scan as a visibility net rather than a guarantee.
`min_classification: C3` is kept on `knowledge.sxa` regardless (still
commercial/financial-adjacent data — "already anonymized" does not lower its
classification), keeping it local-model-only (ADR-0021/ADR-0035) exactly like
`sxa-legacy`. No agent-facing tool can write to this domain's pgvector store
or the S3 source bucket — ingestion-only-writable by construction, same
posture as every other RAG domain.

## Operational considerations

Weekly ingestion runs against the dedicated bucket; a re-run against an
unchanged snapshot is a no-op (idempotent, per `stage_detect_changes`'s
generic behavior). The dedicated bucket's name/region and Vault-sourced
credentials are operator-supplied placeholders until provisioned, mirroring
ADR-0216's own bucket-wiring pattern.

## Acceptance criteria

- `fetch-sxa` parses a real `sxa.schema.sql` + `sxa.data.sql` pair into
  per-row text records without executing any SQL against any database.
- A weekly scheduled run against an unchanged snapshot leaves
  `document_embeddings` row counts/`updated_at` for this domain unchanged.
- Comage, Advantage, and Finage each successfully retrieve `knowledge.sxa`
  content; users without `sales`/`board`/`adv`/`finance` cannot.
- `knowledge.sxa-legacy`'s existing WP-35 negative test for Advantage still
  passes unmodified.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md)
- [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md)
- [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md)
- [ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md)
- [ADR-0216](0216-import-real-sxa-content-via-s3-into-mariadb-served-through-mcp-and-anonymized-rag.md)
- [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
- [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md)
