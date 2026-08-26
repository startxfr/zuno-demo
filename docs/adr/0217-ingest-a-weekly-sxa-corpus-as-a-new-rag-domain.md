# ADR-0217: Ingest a weekly SXA corpus as a new RAG domain

- **Status:** Superseded by ADR-0219 (SXA served only as a historical RAG corpus)
- **Target:** v0.2
- **Date:** 2026-08-21
- **Decision owners:** Zuno Demo architecture team
- **Superseded:** 2026-08-26 by [ADR-0219](0219-serve-sxa-only-as-a-historical-rag-corpus.md)

## Historical context

A second SXA source arrived, distinct from ADR-0216/WP-065's: an
operator-supplied mysqldump (`sxa.schema.sql` + `sxa.data.sql`) intended to
refresh weekly and be readable by Comage, Advantage, and Finage (Cognos once
it exists as a real deployment).

ADR-0216 built `knowledge.sxa-legacy` for a deliberately narrower case: a
live MariaDB import backing exact-lookup MCP tools, `sales`/`board`-only
access (ADR-0340's access-intent matrix excluded `finance`/`cdp`), and an
immutable, on-demand-only refresh model (no scheduled cadence — "the source
is a point-in-time dump snapshot, not a live system",
`knowledge/sxa-legacy/domain.yaml`).

None of those constraints fit this source: it needed no live MariaDB/MCP path
(RAG-only), broader access (Comage, Advantage, Finage), and a real weekly
cadence. Reusing `knowledge.sxa-legacy` would have meant either weakening its
existing, tested security posture (WP-35's passing negative test denies
Advantage; ADR-0340's table denies finance) or silently redefining what that
domain means underneath WP-065's separate, still-open effort.

## Decision

1. **A new logical domain, `knowledge.sxa`, is introduced** —
   `knowledge/sxa/domain.yaml` (ADR-0202), independent of and untouched by
   `knowledge.sxa-legacy`. Both domains may coexist indefinitely; there is no
   plan to merge them, since they answer different provenance/trust
   questions.

2. ~~No transform stage — audit only.~~ **Superseded on 2026-08-23: no
   transform and no audit.** The upstream dump is trusted as-is and indexed
   unmodified, with no content scan of any kind. (Original text, for history:
   an additive `audit_pii_patterns()` function was to scan values against a
   column map and log a warning without altering or blocking anything — a
   visibility net, not an enforcement gate.)

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
`knowledge.sxa-legacy` (narrow access, on-demand) and `knowledge.sxa`
(broader access, weekly). Neither WP-065/ADR-0216's tests nor its own
eventual live completion are affected by this decision. A future decision to
converge them, or to extend this domain's access/schedule model, needs its
own ADR — this one does not pre-commit to either.

## Security considerations

Neither SXA domain scans or transforms content; both rely solely on access
control. `min_classification: C3` is kept on `knowledge.sxa` regardless
(commercial/financial-adjacent data), keeping it local-model-only
(ADR-0021/ADR-0035) exactly like `sxa-legacy`. No agent-facing tool can write
to this domain's pgvector store or the S3 source bucket — ingestion-only-
writable by construction, same posture as every other RAG domain.

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
- [ADR-0216](0216-import-real-sxa-content-via-s3-into-mariadb-served-through-mcp-and-rag.md)
- [ADR-0219](0219-serve-sxa-only-as-a-historical-rag-corpus.md) (supersedes this record)
- [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
- [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md)
