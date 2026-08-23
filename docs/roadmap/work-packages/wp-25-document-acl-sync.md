# WP-25: Document ACL synchronization (promotes ADR-0110)

- **State:** Done (2026-08-23 — completed live. The 2026-08-17 attempt's premises were both stale: `rag-tech` was not seed-only (a real, already-running recurring pipeline had populated it with 846 real chunks/500 pages), and the six real Confluence sources point at `SXSI`, not the empty `ARCH` this WP had been targeting (that gap is WP-07's, unrelated). Investigating that pipeline's own live `reconcile-acls` run found a real bug: `_list_confluence_space_pages` paginated via `start=`/`limit=` offset arithmetic, which never terminates against Confluence Cloud's actual cursor-based `content/search` endpoint at this space's real scale - the run failed after 58 minutes with a `504` at `start=294425`, fail-closed (zero deletions). Fixed to reuse `stage_fetch_confluence`'s already-correct `_links.next` cursor pagination; live-reconfirmed. With the fix, `reconcile-acls` ran for real against the Postgres primary (via `zuno-postgresql-pgbouncer.zuno-data.svc`, the same path production uses) three times, proving propagation-no-op (499 real pages), propagation-update (one real page's `acl_groups` drifted then corrected), and fail-closed removal (the seed fixture row removed, then restored to its exact original state). Final DB: 846/500, unchanged from baseline. See ADR-0110's 2026-08-23 note for the full trace.)
- **State (2026-08-15, repo work):** ADR-0110 promoted to a full record, honestly scoped to reconciliation against the platform's own declared `requiredGroups` config plus live page-existence re-listing (the brief's "re-reads current source authorization" corrected to reflect there is no live Confluence restrictions API in this repo — see the ADR's Decision text); new `reconcile-acls` stage (`components/rag-ingestion/src/rag_ingestion.py`) runs after `validate` over every indexed Confluence chunk (not just the run's changeset), updates `acl_groups` on drift, removes chunks whose source is no longer visible or in scope (fail closed), aborts with zero deletions on a listing failure, and gives the previously-unused `preserveAcl` field real meaning (false = confirm existence, never overwrite `acl_groups`); wired into the KFP DAG for every domain (a no-op where no Confluence source is configured) and CI. 7 fixture tests cover propagation, deletion, scope-narrowing, no-op-on-unchanged, fail-closed-on-outage, `preserveAcl: false`, and the no-sources no-op.
- **ADRs:** ADR-0110 (Proposed -> To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-21 (merged), WP-02 (merged — real Confluence access)
- **Estimated files touched:** ~6

> Execute this brief as a standalone task from the repository root.

## Goal

Promote stub ADR-0110, then add an ACL-reconciliation stage to the ingestion
pipeline that keeps `acl_groups` metadata aligned with current source
authorization and removes chunks whose source content became inaccessible —
fail closed, scheduled with each domain's refresh.

## ADR references

Stub (from `docs/adr/0100-v0.1-roadmap.md`): keep private vector indexes aligned with current source authorization and remove inaccessible content.

Related: ADR-0046 (`acl_groups` metadata + retrieval filter), ADR-0330
(Confluence `acl_groups` tagging from `requiredGroups`), ADR-0105/WP-22
(cadences), ADR-0408 (v0.4 automates removal for *private RAG content*
generally — this WP covers the v0.1-scoped source-ACL sync; keep scopes
distinct). Acceptance criteria: Standard clauses — security-negative tests
mandatory (authorization boundary).

## Preconditions (verify before starting)

- WP-21 and WP-02 merged; `python3 platform/docs/check_docs.py` exits 0.
- Read: `components/rag-ingestion/src/rag_ingestion.py` (fetch-confluence's
  `acl_groups` tagging and detect-changes' deleted-handling — the
  reconciliation stage extends these), `components/rag-service/app/search.py`
  (the `?|` group filter — unchanged, defense in depth).

## Step 0 — ADR promotion

1. Create `docs/adr/0110-automate-document-acl-synchronization.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.1`).
   Decision: promotion sentence + stub text verbatim, plus:

   > Each scheduled ingestion run for an ACL-bearing source ends with a
   > reconcile-acls stage that re-reads current source authorization,
   > updates `acl_groups` on changed chunks, and deletes chunks whose
   > source document is no longer readable by any mapped group or no
   > longer exists. Reconciliation is fail closed: if source authorization
   > cannot be determined for a chunk, the chunk is removed (retrieval
   > filtering alone is not sufficient — stale private content must leave
   > the index). Deletions are logged with provenance for audit.

   Standard-clauses pointer + Related ADRs (0046, 0105, 0330, 0408).
2. `docs/adr/0100-v0.1-roadmap.md`: KEEP heading; body →
   `Promoted to a full decision record: see [ADR-0110](0110-automate-document-acl-synchronization.md) (WP-25 implementation).`
3. `docs/adr/README.md`: direct link + `To be implemented`.
4. `python3 platform/docs/check_docs.py` exits 0.

## Repo changes (step by step)

1. Add a `reconcile-acls` stage to
   `components/rag-ingestion/src/rag_ingestion.py` following the existing
   stage pattern (S3 state round-trip, per-domain DB via WP-21 bindings):
   re-fetch source ACL state (Confluence `requiredGroups` via the same API
   the fetch stage uses), diff against indexed `acl_groups`, update/delete.
2. Wire the stage into the pipeline definition after `validate`, and into
   each scheduled run (WP-22 cadence config).
3. Audit logging of deletions (chunk source, snapshot, reason), no content
   in logs.
4. Tests (fixtures): ACL change propagates to `acl_groups`; inaccessible
   document's chunks are deleted; undeterminable ACL → chunk removed (fail
   closed); untouched documents unaffected.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- The retrieval-side `?|` filter (stays as defense in depth).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest components/rag-ingestion/ -q`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up

All discharged live 2026-08-23 - see ADR-0110's dated note. `ARCH`
remains empty and is tracked separately under WP-07 (it was never one of
this WP's own configured sources).

## Status updates (then re-run check_docs.py)

- After repo merge (2026-08-15): ADR-0110 →
  `Partially implemented (reconcile-acls stage and tests merged; live Confluence verification pending)`;
  index row to match; tracker → `Operator pending`.
- After live verification (2026-08-23): ADR-0110 →
  `Implemented - see \`components/rag-ingestion/src/rag_ingestion.py\`.`;
  index row `Implemented`; tracker → `Done`.

## Out of scope / deferred

- Google Drive / Salesforce ACL sync (extend per source as their adapters
  gain private content; ADR-0408 in v0.4 generalizes removal).
