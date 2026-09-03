# WP-22: Ingestion source adapters and cadences (completes ADR-0204; promotes ADR-0105)

- **State:** Done (2026-08-26 - tech/legacy live cadence runs completed; the Salesforce and
  Aramis clauses were superseded by ADR-0218 rather than delivered here).
- **State (2026-08-30, amended by):** [WP-100](wp-100-split-tech-ingestion-cadence-by-source.md)
  splits `knowledge.tech`'s shared fetch-redhat+fetch-confluence schedule
  into two independently-cadenced KFP pipelines - this WP's own scope and
  `State: Done` above are unchanged (WP-100 is a new, dependent WP, not a
  reopening of this one).
- **State (2026-08-30, WP-100 closed):** WP-100 reached `Done` this same
  day - `rag-dspa` readiness (the blocker this WP's tracker row had carried
  since 2026-08-17) cleared, and the live operator confirmation both WPs
  were waiting on ran successfully, including a real concurrent-run proof
  (see WP-100's own status update). This WP's own scope/state remain
  unchanged; recorded here as the closing cross-reference.
- **State (2026-08-26):** [ADR-0218](../../adr/0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md)
  amended and enacted. Aramis is no longer merely untracked here: the
  `fetch-aramis` adapter and every trace of its wiring are removed from the
  repository - `_fetch_aramis`/`STAGES`/`SOURCE_ADAPTERS`/`IngestionConfig`
  and its fixture test in `components/rag-ingestion/`, the `domains.adv`
  entry + `aramis` ExternalSecret + `ARAMIS_SOURCES_JSON` keys + KFP
  component + `fetchStages` schema enum value in
  `gitops/charts/rag-ingestion/`, the `zuno/aramis/technical` Vault seed and
  `zuno_aramis_*` variables in `ansible/`, the source class in
  `knowledge/adv/domain.yaml`, the `domains.adv` pointer in
  `platform/bindings/knowledge/bindings.yaml`, and the Aramis attributions in
  `agents/advantage/`. `knowledge.adv` itself is retained (descriptor, policy
  entry, `rag-adv` binding) with no ingestion adapter of any kind. Salesforce
  is *deferred, not dropped*: `fetch-salesforce`, `domains.sales`
  (`enabled: false`) and the `zuno/salesforce/technical` seed all stay in the
  tree, and its cadence now has a real band - v0.7, not an unscheduled
  backlog. Deploy-side no-op: `domains.adv` was never enabled and the Aramis
  Vault path was never populated.
- **State (2026-08-23, amended by the above):** Salesforce and Aramis dropped from this WP's scope by
  [ADR-0218](../../adr/0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md) —
  Aramis will never be provisioned, and Salesforce's batch-ingestion cadence
  is deferred (to v0.7 since 2026-08-26; Comage's live Salesforce MCP-tool
  access and the `knowledge.sales` domain/database binding are unaffected).
  Remaining scope is the already-merged tech/legacy adapters and cadence
  automation below; no Salesforce/Aramis credential or snapshot follow-up
  is tracked here any longer. State: `Operator pending` only for the
  `rag-dspa`-readiness blocker on live per-domain runs (WP-07's 2026-08-17
  finding) — unrelated to the dropped adapters.
- **State (2026-08-17, superseded by the above):** ~~live check confirmed the exact blockers: `salesforce-technical-credentials` ExternalSecret genuinely has no Vault data (`SecretSyncedError`) - `ansible/roles/vault/tasks/install.yml` only seeds it when real credentials are supplied, working as designed; no Aramis ExternalSecret exists yet at all~~; full test suite (38 tests)/`helm lint`/`helm template`/`check_knowledge_refs.py` all still pass - no repo-side gap found. Repo work (below) unchanged from 2026-08-15.
- **State (2026-08-15, repo work):** ADR-0105 promoted to a full record; fetch stages refactored behind one SourceAdapter interface with a per-run domain guard (fail closed) and first-ever fixture tests for the pipeline (`components/rag-ingestion/tests/test_source_adapters.py`); `fetch-salesforce`/`fetch-aramis`/`load-sxa-dump` adapters added (fixture-driven, snapshot_id/import-timestamp/checksum on sxa records; per ADR-0218 `fetch-aramis` was since removed from the repository entirely and `fetch-salesforce` is inert, left in place unused pending v0.7); normalize writes `domain` + canonical `technology` (redhat slug map + explicit per-Confluence-source values) and the runtime forwards `technology`; chart gained a `domains:` map (per-domain ConfigMaps/ExternalSecrets/Pipeline CRs, per-domain S3 prefixes, all shipped `enabled: false`), one schedule ConfigMap per scheduled domain, and `ansible/roles/rag_ingestion` now creates recurring runs from those ConfigMaps (values cron is finally authoritative). Remaining operator follow-up: an approved SXA snapshot, per-domain live runs and KFP schedule confirmation for tech/legacy only.
- **ADRs:** ADR-0204 part 2 (-> Implemented with WP-21, Salesforce/Aramis bullets superseded by ADR-0218); ADR-0105 (Proposed -> To be implemented -> Partially implemented, Salesforce/Aramis clauses superseded by ADR-0218, retargeted to v0.7 on 2026-08-26 — roadmap reprioritization, unrelated to the WP-04/WP-11 GitHub-Actions v0.7 theme)
- **Depends on:** WP-21 (merged), WP-07 (merged)
- **Blocks:** — (2026-08-20 correction: previously listed WP-23/WP-33/WP-35
  here, but all three needed only the fixture-driven `load-sxa-dump`/
  `fetch-salesforce`/`fetch-aramis` adapters below, merged 2026-08-15 —
  not the recurring-cadence/live-credential automation this WP's
  Operator-pending state still tracks. That automation blocks nothing
  downstream today.)
- **Note (2026-08-26):** `load-sxa-dump` survives ADR-0219 but no longer
  imports into MariaDB - it parses the S3 dump in pure Python. Its stage name,
  domain binding and cadence are unchanged.
- **Estimated files touched:** ~10

> Execute this brief as a standalone task from the repository root.

## Goal

Turn `components/rag-ingestion` into the generic multi-source ingestion
framework ADR-0204 requires — adding a SQL-dump source adapter next to the
existing web/Confluence ones — and promote + implement ADR-0105's per-source
scheduled cadences (weekly tech / on-demand legacy, manual refresh retained).
Salesforce and Aramis adapters were originally in scope here but are dropped
per [ADR-0218](../../adr/0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md)
(2026-08-23, amended 2026-08-26) — Aramis will never be provisioned and its
implementation is now removed from the repository; Salesforce's cadence is
deferred to v0.7.

## ADR references

- [docs/adr/0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md](../../adr/0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md) — source-adapter mapping: web + Confluence → tech, validated SQL dump → sxa-legacy, through one generic ingestion framework (Salesforce → sales and Aramis → adv bullets superseded by ADR-0218).
- ADR-0105 stub (from `docs/roadmap/adr-decisions-v0.1.md`): ingestion runs per each source's freshness objective instead of one global monthly cadence — weekly minimum for tech (web/Confluence), on-demand for immutable legacy sources — manual refresh retained (the hours-scale Salesforce clause superseded by ADR-0218).
- [docs/adr/0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md](../../adr/0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md) — drops Salesforce/Aramis from this WP's scope.

## Preconditions (verify before starting)

- WP-21 merged: `test -f platform/bindings/knowledge/bindings.yaml`.
- WP-07 merged: catalog tooling exists in `components/rag-ingestion/tooling/`.
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `components/rag-ingestion/src/rag_ingestion.py` (the eight-stage CLI
  and how fetch-redhat/fetch-confluence are shaped),
  `gitops/charts/rag-ingestion/values.yaml` (`schedule.cron`, source config),
  `data/sxa/` (the legacy SQL representation), `knowledge/*/domain.yaml`
  (per-domain freshness objectives from WP-20).

## Step 0 — ADR-0105 promotion

1. Create `docs/adr/0105-automate-source-specific-knowledge-ingestion.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.1`).
   Decision: open with the promotion sentence, then carry the stub text
   verbatim as the decision core, adding: cadences are configured per domain
   in `knowledge/<domain>/domain.yaml` (freshness objective) and realized as
   per-source KFP recurring-run schedules in
   `gitops/charts/rag-ingestion/values.yaml`; manual refresh remains
   `make d1 install rag-ingestion` triggering an immediate run.
   Standard-clauses pointer + Related ADRs (0204, 0205, 0330).
2. `docs/roadmap/adr-decisions-v0.1.md`: KEEP the `### ADR-0105:` heading **and
   its explicit `<a id="adr-0105-automate-monthly-knowledge-ingestion"></a>`
   anchor line** (external links target it); replace only the body paragraph
   with `Promoted to a full decision record: see [ADR-0105](../../adr/0105-automate-source-specific-knowledge-ingestion.md) (WP-22 implementation).`
3. `docs/adr/README.md`: ADR-0105 row → direct link, `To be implemented`.
4. `python3 platform/docs/check_docs.py` exits 0.

## Repo changes (step by step)

1. **Adapter interface:** refactor the fetch stage of
   `components/rag-ingestion/src/rag_ingestion.py` so `fetch-redhat` /
   `fetch-confluence` become two implementations of one source-adapter
   interface (same S3 state round-trip). Pure refactor first — existing
   fixture tests must stay green unchanged.
2. **New adapters:** `fetch-salesforce` (REST query of configured objects →
   normalized records with ADR-0202 sales metadata), `fetch-aramis`
   (API/export ingestion → adv metadata; **removed from the repository
   2026-08-26 per ADR-0218** — this step is historical), `load-sxa-dump` (validated SQL
   dump snapshot → sxa-legacy metadata with versioned snapshot ID,
   import timestamp, checksum — per ADR-0206). Credentials via env/ESO;
   fixture-driven tests per adapter (no live calls in CI).
3. **Domain targeting:** each pipeline run targets one domain and writes
   through WP-21's binding for that domain (correct database, correct
   metadata `domain` value).
4. **Cadences:** extend `gitops/charts/rag-ingestion/values.yaml` +
   templates so each domain/source has its own `schedule.cron` (defaults:
   tech weekly; sales hours-scale, configurable; adv configurable;
   sxa-legacy no schedule, on-demand only), reusing the recurring-run
   activation path in `ansible/roles/rag_ingestion/tasks/install.yml`.
   (The `adv` cadence no longer exists — its domain entry was deleted with
   the Aramis adapter on 2026-08-26, ADR-0218.)
5. **Manual refresh:** document and verify the on-demand path per domain.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- The existing eight-stage logic beyond the adapter-interface refactor.
- `images.*.tag` fields (WP-04); real source credentials (operator-supplied).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest components/rag-ingestion/ -q` (old + new fixture tests)
- `helm lint gitops/charts/rag-ingestion`; `helm template` renders one
  recurring-run schedule per scheduled domain
- `python3 platform/docs/check_knowledge_refs.py` (exit 0)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. Operator: supply an approved SXA dump snapshot (Aramis credentials no
   longer exist; Salesforce credentials are v0.7 work — ADR-0218).
2. Operator: run the tech/legacy adapters once on cluster (`make d1 install
   rag-ingestion` per domain), verify rows land in the correct per-domain
   database with correct metadata; confirm the recurring schedules exist in
   KFP.

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0105 →
  `Partially implemented (tech/legacy cadence merged; Salesforce/Aramis clauses superseded by ADR-0218)`;
  ADR-0204 stays as WP-21 left it plus a dated note; index rows to match;
  tracker → `Operator pending` (rag-dspa readiness only).
- After operator runs: ADR-0105 → `Implemented - see \`components/rag-ingestion/\`.`;
  ADR-0204 → `Implemented - see \`platform/bindings/knowledge/\`, \`components/rag-ingestion/\`.`
  (joint completion with WP-21); index rows `Implemented`; tracker → `Done`;
  MEMORY.md dated bullet.

## Out of scope / deferred

- Salesforce and Aramis ingestion adapters — superseded by
  [ADR-0218](../../adr/0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md)
  (2026-08-23, amended 2026-08-26): Aramis dropped entirely and its code
  removed from the repository; Salesforce cadence deferred to v0.7 with its
  adapter and inert chart scaffolding left in the tree.
- Deterministic SXA query capabilities + C3 policy (WP-23 / ADR-0206).
- Freshness-driven live-read routing (WP-24 / ADR-0205 + ADR-0109).
- ACL synchronization (WP-25 / ADR-0110).
