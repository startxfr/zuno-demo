# WP-38: AIAgent operator implementation (promotes ADR-0308; closes ADR-0113)

- **State:** Not started
- **ADRs:** ADR-0308 (Proposed -> To be implemented -> Partially implemented -> Implemented); ADR-0113 (Proposed -> Implemented alongside it)
- **Depends on:** WP-37 (merged)
- **Blocks:** WP-41
- **Estimated files touched:** ~15

> Execute this brief as a standalone task from the repository root. The
> WP-37 contract (`operator/aiagent-operator/CONTRACT.md` + CRD) is binding —
> any needed contract change goes back through a WP-37 amendment, not ad-hoc
> controller behavior.

## Goal

Promote stub ADR-0308 and implement the AIAgent operator: a controller
reconciling `AIAgent` CRs into the per-agent resources the WP-37 contract
enumerates (frontend/BFF Deployments/Services/Routes, OKF ConfigMap/
reference, NetworkPolicy/ServiceAccount/RBAC, optional binding objects,
status conditions), within the contract's hard boundaries. This finally
discharges ADR-0113's long-deferred CRD/operator decision.

## ADR references

- ADR-0308 stub (verbatim, from `docs/adr/0300-v0.3-roadmap.md`): "Automate
  more lifecycle, policy and deployment reconciliation around agent
  definitions."
- [docs/adr/0327-...md](../../adr/0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md)
  — remaining acceptance bullets discharged here (verbatim):
  "Creating an `AIAgent` CR through GitOps produces the expected per-agent
  frontend/BFF/configuration resources without modifying shared platform
  services." / "Deleting/suspending an `AIAgent` has a defined, safe
  lifecycle that does not delete shared data or secrets unexpectedly." /
  "Existing plain-manifest agents can be migrated incrementally without a
  flag day."
- [docs/adr/0113-provide-an-aiagent-kubernetes-crd-and-operator.md](../../adr/0113-provide-an-aiagent-kubernetes-crd-and-operator.md)
  — the original decision this implements.

## Preconditions (verify before starting)

- WP-37 merged: `test -f operator/aiagent-operator/CONTRACT.md` and the CRD
  + samples + `validate_contract.py` pass.
- `python3 platform/docs/check_docs.py` exits 0.
- Read: the operator scaffold (framework, language, build), CONTRACT.md, the
  CRD, one deployed agent chart (the resources the controller must
  generate).

## Step 0 — ADR-0308 promotion

1. Create `docs/adr/0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.3`).
   Decision: promotion sentence + stub text, then: "Implement the AIAgent
   Operator against the ADR-0327 contract exactly: the operator reconciles
   per-agent frontend/BFF/OKF-reference/NetworkPolicy/ServiceAccount/RBAC
   resources and status conditions from `zuno.ai/v1alpha1 AIAgent` CRs that
   Git/Argo CD owns; it never installs shared platform services, never
   becomes the source of truth for OKF semantics, never bypasses Argo CD
   for the CR itself, never broadens cluster RBAC dynamically, and never
   creates unrestricted credentials. Migration is incremental per agent
   with the plain-manifest path remaining valid until each agent's CR is
   adopted." Standard-clauses pointer + Related ADRs (0113, 0327, 0022,
   0008).
2. `docs/adr/0300-v0.3-roadmap.md`: KEEP the `### ADR-0308:` heading; body →
   `Promoted to a full decision record: see [ADR-0308](0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md) (WP-38 implementation).`
3. `docs/adr/README.md`: direct link + `To be implemented`.
4. `python3 platform/docs/check_docs.py` exits 0.

## Repo changes (step by step)

1. **Controller:** implement reconciliation in `operator/aiagent-operator/`
   using its scaffold's framework: for each `AIAgent`, generate exactly the
   CONTRACT.md resource set (template from the existing agent charts so
   generated resources match chart-deployed ones field-for-field where the
   contract covers them); set the five status condition types; safe
   delete/suspend semantics (owned resources garbage-collected via owner
   references; shared data/secrets untouched — no cross-resource deletes).
2. **Boundary enforcement in code:** admission/validation rejects
   cross-namespace references and inline secret material (defense in depth
   over the CRD schema); RBAC manifest grants only the per-agent resource
   kinds in the agent namespaces — nothing cluster-wide beyond CRD watch.
3. **Tests:** envtest-style (or the scaffold's harness): create CR →
   expected resources with owner refs; update CR → drift reconciled; delete
   CR → owned resources gone, shared untouched; invalid CR → rejected +
   condition set; condition transitions.
4. **Deployment:** operator Deployment manifests/chart +
   `gitops/apps/aiagent-operator/` Application; image into the build matrix;
   immutable tag rule applies.
5. **Migration path:** convert ONE agent (Arkos) to CR-managed as the proof,
   leaving others plain-manifest: add its `AIAgent` CR to GitOps and remove
   only the chart resources the operator now owns (document the exact
   diff in the PR; Tekos stays plain-manifest to prove coexistence).
6. **make check:** wire `status.conditions` consumption into the Day 1
   agents check (`ansible/roles/agents`) for CR-managed agents — discharges
   ADR-0327's `make check` bullet.

## What NOT to touch

- CONTRACT.md semantics (amend via WP-37 if genuinely needed); existing ADR
  Decision text; the ADR-0344 dirty set.
- Shared platform Applications; Tekos's plain-manifest deployment.
- `gitops/apps/*` `targetRevision` (WP-04).

## Acceptance checks (run from repo root; all must pass)

- Operator test suite passes (scaffold's runner); `validate_contract.py`
  still exit 0
- `python3 platform/supply-chain/check_build_matrix.py`;
  `python3 platform/security/check_workload_hardening.py`
- `helm lint` on touched charts; `ansible-playbook ansible/playbooks/day1_check.yml --syntax-check`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. Operator: deploy the operator on cluster; sync Arkos's `AIAgent` CR;
   verify generated resources, conditions, and `make d1 check agents`;
   exercise delete/suspend safely — discharges ADR-0327 bullets 2/3/6 and
   ADR-0308's claim.

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0308 →
  `Partially implemented (controller, boundaries, tests and Arkos migration merged; cluster reconciliation pending)`;
  ADR-0113 stays `Proposed` with a dated pointer note; index rows to match;
  tracker → `Operator pending`.
- After cluster verification: ADR-0308 →
  `Implemented - see \`operator/aiagent-operator/\`.`; ADR-0113 →
  `Implemented - see ADR-0327/ADR-0308 and \`operator/aiagent-operator/\`.`;
  index rows `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Migrating the remaining agents to CRs (mechanical follow-ups once proven).
- Self-service onboarding on top of the operator (WP-41).
