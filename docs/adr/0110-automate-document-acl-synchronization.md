# ADR-0110: Automate document ACL synchronization

- **Status:** Partially implemented (reconcile-acls stage and tests merged; live Confluence verification pending)
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
