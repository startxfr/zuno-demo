# WP-09: Controlled semantic caching (promotes ADR-0104)

- **State:** Done (2026-08-14 — repo-provable, no operator step required)
- **ADRs:** ADR-0104 (Proposed -> To be implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Blocks:** —
- **Estimated files touched:** ~6

> Execute this brief as a standalone task from the repository root. Read the
> referenced files before editing. If the repository state contradicts a
> step, stop and report instead of improvising.

## Goal

Promote stub ADR-0104 to a full record, then add a semantic cache to the AI
Gateway that reduces latency/cost while provably never serving content
across user-authorization or classification boundaries.

## ADR references

Stub origin (`docs/roadmap/adr-decisions-v0.1.md`): reduce latency and cost
without leaking cross-user or cross-classification content.

Related: ADR-0021 (C1/C2/C3 routing), ADR-0034 (effective classification),
ADR-0035 (external-model restrictions), ADR-0029 (cost instrumentation).
Acceptance criteria: Standard clauses — security-negative tests are
mandatory (this touches a classification boundary).

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `components/ai-gateway/app/` (request path, where classification and
  user identity are available), `gitops/charts/redis/` +
  `ansible/roles/redis/` (Redis already exists as a Day 0 component — reuse
  it, do not add a new store), `gitops/charts/ai-gateway/values.yaml`.

## Step 0 — ADR promotion

1. Create `docs/adr/0104-introduce-controlled-semantic-caching.md` with the
   standard header block (`- **Status:** To be implemented`, Target `v0.1`,
   today's date, owners) and this Decision:

   > Promote this decision from a one-line v0.1-roadmap entry
   > (`../adr-decisions-v0.1.md`) to a full record.
   >
   > Add an opt-in semantic cache in the AI Gateway, stored in the existing
   > platform Redis. The cache key includes, at minimum: normalized prompt
   > embedding bucket, model identity, and the full authorization context —
   > user subject (or an authorization-equivalence hash of groups +
   > entitlements), effective classification, and task identity. A cache
   > entry is only ever served to a request whose authorization context is
   > identical; classification is never downgraded by a cache hit; C2/C3
   > content follows the same external-egress restrictions cached or not
   > (ADR-0035). Cache TTL and enablement are per-model configuration in
   > the ai-gateway chart values, default off. Hits/misses are traced and
   > counted in the existing cost/usage instrumentation (ADR-0029).
   >
   > See [Standard clauses](README.md#standard-clauses) for Alternatives
   > considered, Consequences, Security/Operational considerations,
   > Acceptance criteria and Review evidence.

   Related ADRs list: 0021, 0029, 0034, 0035.
2. In `docs/roadmap/adr-decisions-v0.1.md`: KEEP the `### ADR-0104: …` heading;
   replace the body with
   `Promoted to a full decision record: see [ADR-0104](../../adr/0104-introduce-controlled-semantic-caching.md) (WP-09 implementation).`
3. In `docs/adr/README.md`: flip the ADR-0104 row link to the new file;
   status `Proposed` → `To be implemented`.
4. `python3 platform/docs/check_docs.py` must exit 0 before continuing.

## Repo changes (step by step)

1. Cache module in `components/ai-gateway/app/` implementing the keying rule
   from the promoted Decision; Redis client configuration follows how other
   components reach Redis (see `gitops/charts/redis/` values and existing
   consumers).
2. Integration point: wrap the model-call path *after* routing/eligibility
   decisions (a cache hit must never bypass a policy denial — evaluate
   policy first, cache second).
3. Chart values: `semanticCache.enabled` (default `false`), TTL, per-model
   overrides in `gitops/charts/ai-gateway/values.yaml`.
4. Telemetry: hit/miss counters + trace attribute, wired into the existing
   usage instrumentation.
5. Tests, including the mandatory security-negatives:
   - identical request, same auth context → hit;
   - same prompt, different user/groups → miss;
   - same prompt, different effective classification → miss;
   - policy-denied request is denied even when a matching entry exists;
   - disabled cache → behavior identical to today.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Routing/eligibility logic itself (WP-03/WP-40 territory).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile` on touched ai-gateway files
- `python3 -m pytest components/ai-gateway/ -q`
- `helm lint gitops/charts/ai-gateway`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up

None required — repo-provable. Optional: enable on cluster for one model and
observe hit-rate/cost metrics.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0104 body status →
  `Implemented - see \`components/ai-gateway/app/\`.`; index row
  `Implemented`; tracker → `Done`; this file's State; MEMORY.md dated bullet.

## Out of scope / deferred

- Autonomous cache tuning (WP-42 / ADR-0309).
- Cross-request response streaming from cache (keep first version simple:
  cache complete responses only).
