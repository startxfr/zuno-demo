# WP-24: Freshness routing and trust scoring (implements ADR-0205; promotes ADR-0109)

- **State:** Done (2026-08-15 — both ADRs repo-provable with mocked live tools, per this brief: ADR-0109 promoted to a full record; metadata split into `source_modified_at` (source's own signal, or a best-effort HTTP Last-Modified header for product docs, or `fetched_at`)/`indexed_at` (pipeline clock)/`stale_after` (derived from each domain's `STALE_AFTER` chart value, mirroring `knowledge/*/domain.yaml`'s new `freshness.operation_classes` blocks), enforced fail-closed for operational-domain chunks by `rag-ingestion`'s validate stage (sxa-legacy exempt); `rag-service` trust scoring (`_apply_soft_adjustments`) adds provenance weight, continuous freshness decay (replacing the old flat penalty) and a `freshness_untrusted` rank-last-and-flag treatment for chunks missing the freshness trio, mirrored in `ogx_provider.py` for schema parity; Agent Runtime's live-read trigger (`_live_read_trigger_reason`) fires on an explicit current-state question, a policy-marked freshness-sensitive domain, or a retrieved doc past its `stale_after`, and `source_mode` (`indexed`/`live`/`both`/`none`) is now traced (a new `agent_graph_run` OTel span) and returned in both the REST and SSE chat responses; a write-path invariant test lands in all three components (rag-service, rag-ingestion, agent-runtime); per-domain freshness-lag histogram (`zuno.rag_freshness_lag_seconds`) plus a gated `PrometheusRule` (`gitops/charts/observability`) alerting each domain against its own objective. No operator follow-up required by this brief; optional live Salesforce confirmation once WP-33 lands.)
- **ADRs:** ADR-0205 (To be implemented -> Implemented); ADR-0109 (Proposed -> To be implemented -> Implemented)
- **Depends on:** WP-20, WP-21 (merged); WP-01 (live-tool capabilities resolvable)
- **Blocks:** WP-33 (Comage's indexed-read/live-write proof builds on this)
- **Estimated files touched:** ~9

> Execute this brief as a standalone task from the repository root. ADR-0205
> is the routing principle; ADR-0109 (v0.1 carve-out completing here) is the
> scoring/trigger mechanism — implement them together.

## Goal

Enforce freshness metadata on every operational chunk, define per-domain
freshness policy, rank retrieval results with provenance/freshness trust
scoring, trigger live MCP reads when indexed data exceeds the allowed
freshness window, keep RAG write-free, and expose lag metrics — with traces
that always distinguish indexed vs live vs both.

## ADR references

- [docs/adr/0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md](../../adr/0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md)
- ADR-0109 stub (from `docs/roadmap/adr-decisions-v0.1.md`): rank knowledge using provenance, `source_modified_at`, `indexed_at` and source/domain freshness policy; signal stale content; trigger a live MCP/API read when an indexed answer isn't fresh enough for the requested operation.

ADR-0205 acceptance criteria: a normal sales semantic question is answered from `knowledge.sales` without a live Salesforce call; a question explicitly asking for the current value of a mutable Salesforce field can trigger live verification; every Salesforce mutation goes through a write capability, never through RAG; technical Confluence content is answered from `knowledge.tech`, while an authorized live Confluence action can still read/update the source page; traces show whether a response used indexed knowledge, live verification, or both.

ADR-0205 body constraints: chunks must record at least `source_modified_at`,
`indexed_at`, `stale_after`; freshness policy is per domain/source/operation,
never one global duration; "no silent source substitution"; metrics expose
`now - indexed_at` (and `indexed_at - source_modified_at` when available)
with alerts against domain objectives.

## Preconditions (verify before starting)

- WP-20/WP-21 merged; `python3 platform/docs/check_docs.py` exits 0.
- Read: `components/rag-service/app/search.py` (ranking hook),
  `components/rag-ingestion/src/rag_ingestion.py` (where `indexed_at` etc.
  get written), `components/agent-runtime/app/graph/build.py` (the
  retrieve/tool_call/reason/respond flow — where the live-read trigger
  decision belongs), `knowledge/*/domain.yaml` (freshness objectives),
  `gitops/charts/observability/` (metric/alert conventions).

## Repo changes (step by step)

1. **Step 0 — ADR-0109 promotion:** create
   `docs/adr/0109-implement-source-freshness-and-trust-scoring.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.1`);
   Decision = promotion sentence + the stub text verbatim + one binding
   addition: "Scoring inputs and the staleness decision are implemented in
   `rag-service` ranking and the Agent Runtime retrieval step; thresholds
   come from the domain descriptors (`knowledge/<domain>/domain.yaml`), not
   code." Standard-clauses pointer + Related ADRs (0046, 0105, 0202, 0205).
   In `docs/roadmap/adr-decisions-v0.1.md`: KEEP the `### ADR-0109:` heading,
   body → promotion pointer (`(WP-24 implementation)`).
   `docs/adr/README.md`: direct link + `To be implemented`. Run
   `check_docs.py`.
2. **Metadata enforcement:** ingestion validate stage fails operational-
   source chunks missing `source_modified_at`/`indexed_at`/`stale_after`
   (immutable legacy sources exempt per policy); rag-service treats missing
   freshness metadata on operational domains as untrusted (rank last +
   flag), fail closed per WP-20 rules.
3. **Freshness policy:** per-domain `freshness:` blocks in
   `knowledge/<domain>/domain.yaml` (objective, allowed staleness per
   operation class: `semantic-read`, `current-state-read`); validator
   (`check_knowledge_refs.py`) checks their presence/shape.
4. **Trust scoring:** ranking adjustment in `search.py` combining provenance
   weight and freshness decay; stale results are flagged in the response
   metadata (`stale: true`), never silently dropped.
5. **Live-read trigger:** in the Agent Runtime retrieval step: explicit
   user current-state ask, policy-marked freshness-sensitive source, or
   `stale_after` exceeded for the operation class → invoke the authorized
   live logical capability (via WP-01 bindings) instead of/alongside
   indexed retrieval. Record `source_mode: indexed|live|both` in the trace
   and response — no silent substitution.
6. **Write-path invariant:** test that no RAG code path performs a mutation
   against a source system (writes only via live tool capabilities).
7. **Metrics:** export per-domain lag gauges + alert rules in the
   observability chart against each domain's objective.
8. **Tests:** one per ADR-0205 acceptance bullet (mock live tools), plus
   ranking unit tests (fresh beats stale at equal similarity; missing
   metadata ranks last and flags).

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- The retrieval contract shape (additive metadata only).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest components/rag-service/tests/ components/rag-ingestion/ components/agent-runtime/tests/ -q`
- `python3 platform/docs/check_knowledge_refs.py` (exit 0)
- `helm lint gitops/charts/observability`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up

Optional live confirmation (Salesforce current-value question on cluster
once WP-33 lands) — both ADRs are repo-provable with mocked live tools, so
they move to Implemented on merge; note the live confirmation when done.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0205 →
  `Implemented - see \`components/rag-service/app/search.py\`, \`components/agent-runtime/app/\`.`;
  ADR-0109 → `Implemented - see \`components/rag-service/app/search.py\`.`;
  index rows `Implemented`; tracker → `Done`; this file's State; MEMORY.md
  dated bullet.

## Out of scope / deferred

- ACL-driven removal of inaccessible content (WP-25 / ADR-0110).
- Salesforce live write tooling itself (WP-33).
