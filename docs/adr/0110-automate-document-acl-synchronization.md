# ADR-0110: Automate document ACL synchronization

- **Status:** Implemented - see `components/rag-ingestion/src/rag_ingestion.py`. Live-verified against the real Postgres primary and real Confluence content 2026-08-23 (see the dated note below).
- **Target:** v0.1
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`../roadmap/adr-decisions-v0.1.md`) to a full record.

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
sync is deferred to v0.4, [ADR-0408](../roadmap/adr-decisions-v0.4.md#adr-0408-automate-removal-of-inaccessible-private-rag-content)). What
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

## Live verification completed (2026-08-23)

Two corrections to the 2026-08-17 note above, found while completing the
remaining write: **the `rag-tech` database is not seed-only** - a
real, currently-configured, recurring pipeline (`rag-corpus-ingestion-
scheh5w56`, weekly, ArgoCD app `zuno-rag-ingestion-d1`) had already
populated it with 846 real chunks across 500 real pages by this date.
And **`ARCH` was never the space that matters**: the six real
`knowledge.tech` Confluence sources (`gitops/charts/rag-ingestion/
values.yaml`) all point at `SXSI`, which holds real content (Openshift/
Satellite/Gitlab/AnsibleAutomationPlatform procedures) - `ARCH` is a
separate, still-empty space unrelated to this ADR's own sources (WP-07's
gap, not WP-25's).

That same recurring pipeline's own `reconcile-acls` run was live,
in progress, against the real primary, when this session started
investigating - and it failed after 58 minutes with a Confluence `504
Gateway Timeout` at pagination offset `start=294425`. Root cause: a real
bug. `_list_confluence_space_pages` (added for WP-25) paginates via
`start=`/`limit=` offset arithmetic, but Confluence Cloud's `content/
search` endpoint is cursor-based (`_links.next`) and this real space
never returns a page shorter than `limit` - the loop's only termination
condition. `stage_fetch_confluence`'s own listing loop had already been
fixed to use `_links.next` for exactly this reason (see that function's
own comment), but this second, WP-25-era implementation reintroduced the
old approach instead of reusing the fix. The stage's fail-closed design
worked correctly regardless - the failed run made zero deletions, not a
mass one. Fixed to match `stage_fetch_confluence`'s cursor-based
pagination; live-reconfirmed afterward: the same real space now lists
correctly (1446 raw pages) in under 20 seconds.

With the fix in place, `reconcile-acls` was run for real against the
Postgres primary (routed the same way the production pipeline itself
does, via `zuno-postgresql-pgbouncer.zuno-data.svc`) three times,
proving all three live outcomes end to end:

- **Propagation (no-op):** 499 real, in-scope pages confirmed with
  correct `acl_groups`, zero unnecessary writes.
- **Propagation (update):** one real page's `acl_groups` was
  deliberately drifted to a wrong value directly in the DB (no
  Confluence write needed - just simulating staleness on real data), then
  corrected back to the real config's `requiredGroups` on the next run.
- **Fail-closed removal:** the one pre-existing seed/fixture row
  (`confluence.example.internal`, never real) was correctly removed as
  no-longer-visible, then restored via its exact original insert
  (`data/rag/fixtures/seed.sql`) to leave that fixture available for
  other tests. Final DB state: 846 chunks / 500 pages, byte-identical to
  the pre-verification baseline.

No throwaway Confluence page was needed for either case - the DB's own
real content and the pre-existing fixture row were sufficient, so this
verification made zero writes to Confluence itself, only to the RAG
index (and all of those are either the mechanism's own real behavior or
fully reverted).

Status: **Implemented**.

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
