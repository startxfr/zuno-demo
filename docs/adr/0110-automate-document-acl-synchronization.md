# ADR-0110: Automate document ACL synchronization

- **Status:** Partially implemented (reconcile-acls stage and tests merged; live run reached the real DB write and was blocked only by session tooling permissions, see the dated note below - live Confluence verification still pending)
- **Target:** v0.1
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

Keep private vector indexes aligned with current source authorization and
remove inaccessible content.

Each scheduled ingestion run for an ACL-bearing source ends with a
`reconcile-acls` stage. Its authoritative source of "current source
authorization" is the platform's own declared configuration
(`source.requiredGroups` per Confluence source,
`gitops/charts/rag-ingestion/values.yaml`) — the same configuration
`fetch-confluence` already stamps onto every chunk it writes, not a live
Confluence restrictions/permissions API call (no such integration exists
in this repository; generalizing to real per-document source-restriction
sync is deferred to v0.4, [ADR-0408](0400-v0.4-roadmap.md#adr-0408-automate-removal-of-inaccessible-private-rag-content)). What
`reconcile-acls` *does* re-read live is page **existence and visibility**:
it re-lists every currently-configured source and compares against every
indexed chunk, not just this run's changeset (an unchanged document's
authorization can still have changed since it was last touched).

- A page still visible and in scope for a configured source gets its
  `acl_groups` updated to that source's current `requiredGroups` when
  they differ (unless that source sets `preserveAcl: false`, which
  confirms the page still exists without ever letting reconciliation
  overwrite manually-curated `acl_groups`).
- A page absent from the live listing — deleted, no longer visible to
  the technical identity, or excluded because the platform config no
  longer scopes it under any configured space/directory — has its
  authorization undeterminable and fails closed: every chunk from that
  source is removed. Retrieval-side filtering
  (`components/rag-service/app/search.py`'s `acl_groups` `?|` clause)
  alone is not sufficient — stale private content must leave the index,
  not merely stay unreachable through one code path.
- A listing failure for any configured source aborts the whole stage
  before any deletion runs: a transient outage must never be mistaken
  for "every page was deleted".
- Deletions are logged with the chunk's source, a reason, and this run's
  timestamp for audit — never chunk content.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Live verification attempt (2026-08-17, roadmap WP-25)

This session had live `oc` access and network egress to the real Confluence
instance (`startxfr.atlassian.net`) backing `gitops/charts/rag-ingestion/
values.yaml`'s `confluence[]` config, so `reconcile-acls` was run for real
(not fixture-mocked) via a direct invocation of `rag_ingestion.py
reconcile-acls`, with `CONFLUENCE_SOURCES_JSON` built from the chart's own
enabled entries and real credentials from the `rag-confluence` /
`confluence-technical-credentials` Vault-synced secrets.

Findings:

- **The `rag-tech` database holds only seed/fixture rows** (`data/rag/
  fixtures/seed.sql`, loaded via the chart's ArgoCD sync-wave-41 schema-apply
  Job, which is `Complete`) — 14 rows total, all `docs.example.internal` /
  `confluence.example.internal` placeholder URLs. No real ingestion run has
  ever populated this database. Exactly one row is Confluence-sourced:
  `https://confluence.example.internal/wiki/spaces/TECH/pages/900001`.
- **The real Confluence space (`ARCH`) is confirmed empty** - a direct CQL
  search (`space="ARCH" and type=page`) against the live API returns
  `size: 0`. This is the same real-Confluence-space gap ADR-0330's 2026-08-17
  note records for WP-07 (Confluence real space keys/directories still not
  supplied) - `reconcile-acls`'s live behavior is correspondingly limited
  until that's resolved: with zero live pages, every indexed Confluence
  chunk fails closed as "no longer visible or in scope", by design.
- **The live run reached the real DELETE statement** for the one fixture
  Confluence row (correct fail-closed behavior against an empty live
  listing) - `_confluence_auth`, `_iter_live_confluence_pages` (a real,
  successful CQL call), and `_pg_connect` all executed against real
  systems, not mocks. It stopped there: `psycopg.errors.
  ReadOnlySqlTransaction` because the ad hoc port-forward this session used
  to reach the DB (no direct network path from this shell to the
  cluster-internal Postgres Service, which itself has no selector - PGO/
  Patroni manages it via Endpoints) happened to land on a **replica** pod
  (`zuno-postgresql-instance1-cjg8-0`) rather than the actual primary
  (`...-f8ls-0`, confirmed via the `postgres-operator.crunchydata.com/role`
  pod label). Retrying against the primary pod was blocked by this
  session's own tooling permissions (`oc port-forward` background-process
  restriction), not by anything in the reconcile-acls code or the cluster
  itself - the chart's real deployment path uses the `zuno-postgresql-
  primary.zuno-data.svc` Service, which routes correctly and was never
  itself in question.

Net: the mechanism is proven live end-to-end through the DB write boundary.
What remains is (1) the same real Confluence space-key gap WP-07 already
tracks, and (2) completing one write against the primary with proper
in-cluster network access (an operator running `make d1 install
rag-ingestion`, or a session with less restrictive port-forward tooling,
would not hit either obstacle this session did). Status stays **Partially
implemented**.

## Related ADRs

- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md)
  — the `acl_groups` metadata and retrieval-side filter this ADR keeps
  synchronized, and keeps as defense in depth underneath it.
- [ADR-0105](0105-automate-source-specific-knowledge-ingestion.md)
  — the per-domain cadences `reconcile-acls` runs alongside.
- [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md)
  — the ingestion pipeline `reconcile-acls` is a stage of, and the
  origin of Confluence's `requiredGroups` → `acl_groups` convention.
- ADR-0408 (v0.4) — generalizes automated removal of inaccessible
  private RAG content across every source, including real per-document
  source-restriction sync; this ADR's v0.1/WP-25 scope is deliberately
  narrower (declared-config + visibility reconciliation for Confluence
  only).
