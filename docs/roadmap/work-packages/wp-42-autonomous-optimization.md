# WP-42: Policy-driven autonomous optimization (promotes ADR-0309)

- **State:** Repo work merged (2026-08-15); observed live autonomy cycle +
  user sign-off pending - **the roadmap's final WP; this closes the
  v0.1-v0.3 repo work.** Step 0 promoted ADR-0309 verbatim. New
  `policies/optimization/optimization-policy.yaml` + README: ships
  `enabled: false` (autonomy off until the operator's own per-scope
  sign-off), `kill_switch`, an evaluation window, rollback triggers
  (max_error_rate 0.05 / quality_floor 0.75 - the same [0,1]
  scenario_rate scale WP-40's objectives use), and exactly two scopes:
  `cache_ttl` (min/max seconds range) and `routing`
  (`pre_approved_equivalents: []` - empty today, since no two deployed
  candidates have been human-judged interchangeable yet; only a reviewed
  PR can add pairs). Tuning controller (D12: in-process ai-gateway
  extension, no 12th component -
  `components/ai-gateway/app/optimizer.py`): `TuningController` applies
  in-range recommendations to the RUNTIME configuration surface only -
  `semantic_cache.set_runtime_ttl_override()` (a new seam; the effective
  TTL reverts to the deployment value on pod restart, and the one
  Redis-write site now reads `effective_ttl_seconds()`), and a runtime
  adapter-override map `app/main.py` consults strictly AFTER the
  Git-declared model-routing policy resolves (the override can only ever
  hold values drawn from the pre-approved-equivalents list, and WP-39's
  own `chat_model_for()` guard re-checks candidate.kind downstream
  regardless of where an adapter name came from). Never writes to Git.
  Hard structural guarantee beyond the policy file: a code-level
  `_FORBIDDEN_PARAMETERS` denylist means classification/authorization
  can never be auto-tuned even by a mis-edited policy. Every applied
  change records a complete audit entry (parameter, old/new, the
  recommendation evidence verbatim, timestamps, status) and registers
  its own rollback closure; `report_outcome()` auto-reverts every open
  action on a trigger breach; `kill()` (or `kill_switch: true` on a
  policy reload) refuses all new actions AND reverts everything applied,
  in one step. Admin surface (`/admin/optimizer/{audit,outcome,kill,apply}`,
  in-cluster only - same trust model as `/admin/reload-routing`, which
  now also reloads this policy and honors a kill_switch flip
  immediately). Dockerfile bakes `policies/optimization/` in (absent
  file = autonomy fully disabled, the fail-safe direction). Tests
  (`tests/test_optimizer.py`, 14): every one of the brief's named cases -
  out-of-range refused (never clamped), classification/authorization
  untouchable, rollback on simulated regression (error-rate AND
  quality-floor variants), kill switch halts + reverts, audit entries
  complete - plus policy-loader defaults, the real shipped policy file's
  own values, and kill-via-reload. Full ai-gateway suite (6 files) green;
  the WP-39/40/42 test files are now all wired into lint.yml's
  ai-gateway test step (39/40's were an omission caught here).
  `check_docs.py` PASS; `check_workload_hardening.py` 188/188;
  `check_build_matrix.py` PASS (no new component).
  **Completed 2026-08-15 (follow-up commit)**: the Decision text's
  "TTL/**enablement per model**" clause, which the first commit's
  cache_ttl scope alone didn't cover, is now implemented - a new
  `cache_enabled` scope (per-model allow-list in the policy file;
  the toggle substitutes for the per-model provider-routing
  `cache_enabled` flag only, and can never override the deployment-level
  `SEMANTIC_CACHE_ENABLED` switch - autonomy tunes within the
  deployment's envelope, never widens it), a
  `set_runtime_cache_enabled_override()` seam in `semantic_cache.py`,
  the `/admin/optimizer/apply` parameter `cache_enabled`, and 4 more
  tests (applied end-to-end through `should_use_cache()`,
  global-switch-supremacy, allow-list refusal, rollback/kill revert) -
  18 total, all green.
- **ADRs:** ADR-0309 (Partially implemented merged here -> Implemented after the observed live cycle + user sign-off)
- **Depends on:** WP-40 (merged + live loop done); WP-09 (cache tuning surface)
- **Estimated files touched:** ~7

> Execute this brief as a standalone task from the repository root. This is
> the roadmap's final WP. Autonomy here is narrow and governed — when in
> doubt, keep the human in the loop.

## Goal

Promote stub ADR-0309, then allow *bounded* automated application of a
defined subset of WP-40's recommendations (and WP-09 cache parameters) under
an explicit governance policy: caps, allowed parameter ranges, mandatory
audit trail, automatic rollback triggers, and a kill switch.

## ADR references

Stub (verbatim, from `docs/adr/0300-v0.3-roadmap.md`): "Allow bounded
automated tuning of routing, caching and model choices under explicit
governance."

## Preconditions

- WP-40 done through its live loop (recommendations proven trustworthy at
  least once); WP-09 merged.
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `evaluations/routing_report.py` (recommendation format),
  `policies/model-routing/` objectives, the ai-gateway cache config (WP-09).

## Step 0 — ADR promotion

1. Create `docs/adr/0309-introduce-policy-driven-autonomous-optimization.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.3`).
   Decision: promotion sentence + stub text, then: "A governance policy
   (`policies/optimization/optimization-policy.yaml`) enumerates exactly
   which parameters may be auto-tuned (initial scope: semantic-cache TTL/
   enablement per model within declared ranges; routing choices between
   *pre-approved equivalent* model/adapter candidates only), the allowed
   ranges, the evaluation window, and rollback triggers (quality-floor or
   error-rate breach reverts automatically). Every automated change is
   recorded with its evidence and is reversible; classification and
   authorization policies are never auto-tunable; a kill switch disables
   all autonomy in one configuration change. Anything outside the
   enumerated scope remains a human-reviewed PR (ADR-0304)." Related:
   0104, 0304, 0305.
2. `docs/adr/0300-v0.3-roadmap.md`: KEEP heading; body →
   `Promoted to a full decision record: see [ADR-0309](0309-introduce-policy-driven-autonomous-optimization.md) (WP-42 implementation).`
3. `docs/adr/README.md`: direct link + `To be implemented`.
4. `python3 platform/docs/check_docs.py` exits 0.

## Repo changes

1. `policies/optimization/optimization-policy.yaml` + README (the governed
   scope, commented in the policy-file house style).
2. Tuning controller (extend the ai-gateway or a small
   `components/optimizer/` job — choose whichever keeps the audit/rollback
   loop simplest; if a new component: build-matrix + role + hardening rules
   apply): reads recommendations + policy, applies in-range changes to the
   *runtime configuration surface* (not Git), records an audit entry,
   monitors the window, auto-rolls-back on trigger. Kill switch honored at
   every step.
3. Tests: out-of-range recommendation refused; classification/authorization
   parameters untouchable even if recommended; rollback fires on simulated
   regression; kill switch halts pending actions; audit entries complete.

## What NOT to touch

Standard list; plus: `policies/model-routing/` Git content (autonomy acts on
runtime config only — Git changes stay human-reviewed); authorization/
classification policies (never auto-tunable).

## Acceptance checks

- `python3 -m pytest` on the tuning component's tests
- `python3 platform/security/check_workload_hardening.py`;
  `python3 platform/supply-chain/check_build_matrix.py` (if new component)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up

1. Operator: enable autonomy for the cache-TTL scope only on cluster;
   observe one full tune-evaluate cycle and one forced rollback; user signs
   off before the routing scope is enabled.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0309 →
  `Partially implemented (governance policy, bounded tuner, rollback and kill switch merged; live cycle pending)`;
  after the observed live cycle: ADR-0309 →
  `Implemented - see \`policies/optimization/\`.`; index row + tracker +
  MEMORY.md accordingly. **This closes the v0.1–v0.3 roadmap.**

## Out of scope / deferred

- Any autonomy over authorization, classification, or agent definitions.
- Cross-environment/fleet optimization (new ADR territory).
