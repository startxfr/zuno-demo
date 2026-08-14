# WP-42: Policy-driven autonomous optimization (promotes ADR-0309)

- **State:** Not started
- **ADRs:** ADR-0309 (Proposed -> To be implemented -> Partially implemented -> Implemented)
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
