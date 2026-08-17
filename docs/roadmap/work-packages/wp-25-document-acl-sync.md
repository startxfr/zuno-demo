# WP-25: Document ACL synchronization (promotes ADR-0110)

- **State:** Operator pending (2026-08-17 — live attempt: ran `reconcile-acls` for real (not fixture-mocked) against the live Confluence API and the real `rag-tech` DB. Found the DB holds only seed/fixture rows (no real ingestion has ever run) and confirmed the configured `ARCH` space is genuinely empty on live Confluence (same real-space-key gap as WP-07). The run reached the real DELETE for the one fixture Confluence row - auth, live CQL listing, and DB connect all succeeded against real systems - then stopped on `ReadOnlySqlTransaction` because this session's ad hoc DB port-forward landed on a replica pod, not the primary; a retry against the primary was blocked by this session's own `oc port-forward` tooling permission, not by the code or cluster. See ADR-0110's 2026-08-17 note for the full trace. Repo work (below) unchanged from 2026-08-15.)
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

## Operator / human follow-up (not executable by the model)

1. Operator: supply real Confluence space keys/directories (same item
   WP-07 tracks) — without them the live space is confirmed empty
   (`space="ARCH"` → 0 results), so reconciliation has nothing real to
   propagate an update onto.
2. Operator: complete one real reconcile-acls write against the PG
   *primary* (`zuno-postgresql-primary.zuno-data.svc`, e.g. via
   `make d1 install rag-ingestion` or a properly-routed DB session) — the
   2026-08-17 attempt proved everything up to this point live except the
   final write, which hit a replica by accident of this session's ad hoc
   port-forwarding.
3. Operator: once real content exists, change a real Confluence page's
   restrictions, trigger a run, verify the index reflects it (update +
   removal cases) — discharges the decision's live claim.

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0110 →
  `Partially implemented (reconcile-acls stage and tests merged; live Confluence verification pending)`;
  index row to match; tracker → `Operator pending`.
- After operator verification: ADR-0110 →
  `Implemented - see \`components/rag-ingestion/src/rag_ingestion.py\`.`;
  index row `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Google Drive / Salesforce ACL sync (extend per source as their adapters
  gain private content; ADR-0408 in v0.4 generalizes removal).
