# WP-11: SecNumCloud hardening increment (promotes ADR-0111)

- **State:** Done (2026-08-14 — first-increment scope fully merged: control matrix, NetworkPolicy audit closing a real zuno-ai-run gap, hardcoded-secret check. ADR-0111 itself stays Partially implemented since the matrix still tracks gap rows owned by WP-12/WP-13/WP-26 and live-cluster verification items - that's expected, not unfinished work in this WP.)
- **ADRs:** ADR-0111 (Proposed -> To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-00 (done); benefits from WP-04/WP-05 but does not block on them
- **Estimated files touched:** ~7

> Execute this brief as a standalone task from the repository root.

## Goal

Promote stub ADR-0111 to a full record scoped as a concrete control-gap
matrix plus a first increment of repo-implementable controls, extending the
existing hardening checker so the new controls are enforced in CI.

## ADR references

Stub (verbatim, from `docs/adr/0100-v0.1-roadmap.md`): "Harden deployment,
supply chain, identity, network and data controls toward SecNumCloud-oriented
expectations."

Related: ADR-0052 (restricted-SCC/SecNumCloud objectives — the v0 baseline
this increments), ADR-0115 (supply chain), ADR-0037 (network/workload
identity boundaries), ADR-0041 (no static credentials in Git).
Acceptance criteria: Standard clauses.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `platform/security/check_workload_hardening.py` (what the 70-check
  baseline already covers), `docs/security/` (existing security docs),
  `docs/adr/0052-*.md` (the baseline decision).

## Step 0 — ADR promotion

1. Create `docs/adr/0111-strengthen-secnumcloud-oriented-security-controls.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.1`) with
   this Decision:

   > Promote this decision from a one-line v0.1-roadmap entry
   > (`0100-v0.1-roadmap.md`) to a full record.
   >
   > Maintain a SecNumCloud-oriented control matrix at
   > `docs/security/secnumcloud-controls.md` mapping control families
   > (deployment, supply chain, identity, network, data) to their concrete
   > repo/cluster mechanisms and one of: `enforced-in-ci`,
   > `enforced-on-cluster`, `gap`. Each roadmap increment closes named
   > `gap` rows; CI-enforceable controls are added to
   > `platform/security/check_workload_hardening.py` (or a sibling checker)
   > so regressions block. The matrix is derived documentation — the
   > authoritative sources remain the policy/checker files it cites.
   >
   > First increment (this WP): NetworkPolicy default-deny coverage for all
   > first-party namespaces; PodDisruptionBudget presence is WP-12's
   > concern; secrets-mount hardening checks (no env-var secrets where a
   > file mount is supported); image-provenance rows point at ADR-0115.

   Standard-clauses pointer + Related ADRs (0037, 0041, 0052, 0115).
2. `docs/adr/0100-v0.1-roadmap.md`: KEEP the heading, body →
   `Promoted to a full decision record: see [ADR-0111](0111-strengthen-secnumcloud-oriented-security-controls.md) (WP-11 implementation).`
3. `docs/adr/README.md`: direct link + `To be implemented`.
4. `python3 platform/docs/check_docs.py` exits 0.

## Repo changes (step by step)

1. Write `docs/security/secnumcloud-controls.md` — the matrix, seeded from
   what `check_workload_hardening.py`, ADR-0052 and ADR-0115 already
   enforce; every row cites its enforcing file. Mark honest `gap` rows.
2. Close the first-increment gaps: audit `gitops/charts/*/templates/` for
   missing default-deny NetworkPolicies (mirror an existing chart's
   NetworkPolicy template) and env-var-mounted secrets.
3. Extend `platform/security/check_workload_hardening.py` with checks for
   the newly closed controls, following its existing check style.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Cluster-side controls that need operator action (matrix rows say
  `enforced-on-cluster`/`gap` — do not fake them as done).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 platform/security/check_workload_hardening.py` (exit 0 — including your new checks)
- `helm lint` every chart you touched
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`
- `test -f docs/security/secnumcloud-controls.md`

## Operator / human follow-up (not executable by the model)

1. Operator: verify cluster-side rows (SCC assignments, actual NetworkPolicy
   enforcement, Vault/ESO posture) and update matrix rows from `gap` /
   `enforced-on-cluster` claims to verified state.

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0111 →
  `Partially implemented (control matrix and first CI-enforced increment merged; cluster-side verification pending)`;
  index row to match; tracker → `Operator pending`.
- After operator verification: ADR-0111 →
  `Implemented - see \`docs/security/secnumcloud-controls.md\`.` **only if**
  no `gap` rows remain in scope for v0.1; otherwise it stays Partially
  implemented with the open rows enumerated — record which. Index row to
  match; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- HA/PDB controls (WP-12), backup controls (WP-13), signing gates (WP-04/05)
  — the matrix references them, their WPs implement them.
