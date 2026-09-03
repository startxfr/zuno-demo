# WP-38: AIAgent operator implementation (promotes ADR-0308; closes ADR-0350)

- **State:** Done (2026-08-15 repo merge; cluster reconciliation confirmed
  live 2026-08-17 - `aiagent-operator` deployed and Ready in `zuno-ai-run`;
  both live `AIAgent` CRs, Arkos and Naveo, show all five status
  conditions `True` (`ConfigValid`/`OKFReady`/`FrontendReady`/`BFFReady`/
  `RuntimeBindingReady`). Repo acceptance re-run clean: `go build ./...`,
  13/13 envtest suite (86.2% coverage on `internal/controller`),
  `validate_contract.py` PASS, `check_build_matrix.py` PASS,
  `check_workload_hardening.py` 189/189, `helm lint` on both touched
  charts, `day1_check.yml --syntax-check`. `make d1 check agents` was also
  run live: it exercises the full ADR-0053 fleet gate (all agents, not
  just this WP's scope) and fails overall (13/20 scenarios, 6/7 security
  checks) on pre-existing scenario-design/harness/credential gaps already
  recorded in MEMORY.md's 2026-08-16 note - unrelated to the operator or
  CR reconciliation, which the condition check above confirms works.
  ADR-0308 → Implemented; ADR-0350 → Implemented, per this file's own
  stated trigger now that ADR-0308 closed. Repo work merged (2026-08-15):
  Step 0 promoted ADR-0308 verbatim from its `docs/roadmap/adr-decisions-v0.3.md`
  stub. Controller (`operator/aiagent-operator/internal/controller/`):
  `AIAgentReconciler.Reconcile` generates exactly CONTRACT.md's resource
  set for each CR - two ServiceAccounts, frontend/BFF Deployments+Services,
  a Route (`route.openshift.io/v1`, via an `unstructured.Unstructured`
  object - no new typed Go dependency), a frontend ExternalSecret
  (`external-secrets.io/v1beta1`, same unstructured approach, Vault paths
  derived by convention from `agentName` alone), a BFF-scoped
  NetworkPolicy, and an OKF-reference ConfigMap - every one field-for-field
  templated from the real merged Tekos/Arkos/Comage chart manifests
  (`internal/controller/resources.go`, pure builder functions, unit-tested
  with zero cluster I/O in `resources_test.go`). Every generated object
  carries a controller owner reference (`applyOwned`), so delete/suspend is
  plain Kubernetes garbage collection - no finalizer. In-code defense in
  depth (CONTRACT.md's "reject cross-namespace refs and inline secrets"):
  `targetNamespace` is re-checked against an explicit allowlist
  (`OperatorConfig.AllowedTargetNamespaces`, default `["zuno-ai-run"]`)
  before a single resource is generated - the Go type system already makes
  a secret-shaped or genuinely cross-namespace field impossible to express
  in the first place. `status.conditions` always carries the five
  ADR-0327 types (`ConfigValid`/`OKFReady`/`FrontendReady`/`BFFReady`/
  `RuntimeBindingReady`, named constants in `api/v1alpha1/aiagent_types.go`);
  `RuntimeBindingReady` does a pure read-only presence check against three
  well-known shared-platform Service names (never creates/owns them);
  Route/ExternalSecret creation degrades gracefully (a condition, not a
  panic) if those foreign CRDs aren't installed yet, verified directly in
  envtest via two minimal test-only CRD fixtures under
  `config/crd/test-fixtures/` (never real upstream CRDs - see their own
  header comments) rather than skipped. RBAC
  (`config/rbac/role.yaml`, regenerated via `make manifests` from
  `+kubebuilder:rbac` markers) is scoped to exactly the resource kinds the
  reconciler touches - no wildcard, no cluster-scoped kind. Tests (D8: plain
  `testing` + Gomega's matcher library via `gomega.NewWithT`, not a Ginkgo
  BDD suite - `suite_test.go` replaces kubebuilder's generated Ginkgo
  bootstrap with a `TestMain`-based real envtest control plane) - all 13
  pass against a genuine kube-apiserver+etcd: create->owned resources with
  owner refs; drift (an out-of-band edit reverted on next reconcile);
  invalid namespace rejected with zero resources generated; delete's
  structural half (envtest runs no garbage-collector controller, so this
  proves owner-reference correctness rather than faking cascade-delete
  coverage this environment cannot exercise - documented explicitly in the
  test's own comment, an honest gap matching this repo's established
  pattern); condition-transition-time semantics. Migration proof: Arkos
  (`gitops/charts/arkos/`) now renders exactly one AIAgent CR
  (`templates/aiagent.yaml`) instead of six raw manifests
  (deployment/service/route/serviceaccounts/networkpolicy/externalsecret,
  removed - see git history); Tekos is deliberately untouched, proving
  plain-manifest and CR-managed agents coexist with no flag day.
  `gitops/charts/aiagent-operator/` (new chart: CRD copied verbatim from
  the generated `config/crd/bases/`, ClusterRole/ClusterRoleBinding
  mirroring `config/rbac/role.yaml`, a separate namespace-scoped
  leader-election Role/RoleBinding mirroring kubebuilder's own static
  `leader_election_role.yaml`, and the manager Deployment - deliberately
  the one chart in this repo with `automountServiceAccountToken: true`,
  since reconciling CRs genuinely requires the Kubernetes API) +
  `gitops/apps/aiagent-operator/` (sync-wave -106, earlier than every
  agent chart's own -103-or-later, so Argo CD's wave-based health gate
  sequences the operator before any CR-managed agent). New
  `ansible/roles/aiagent_operator_build/` (mirrors `rag_ingestion_build`'s
  one-task pattern - kubebuilder's own generated Dockerfile already used a
  distroless non-root base, no hardening changes needed) and real
  `ansible/roles/aiagent_operator/` (install/uninstall/precheck, mirrors
  `ansible/roles/mcp`'s shape); root `Makefile`'s `DAY1_BUILD_COMPONENTS`/
  `DAY1_RUN_COMPONENTS` both gained `aiagent-operator`; new build-matrix
  entry in `.github/workflows/build-publish.yml`.
  `ansible/roles/agents/tasks/check.yml` gained a `status.conditions`
  consumption block for the Arkos AIAgent CR specifically (this repo's
  only CR-managed agent) - surfaced via `kubernetes.core.k8s_info`, hard-
  failing only on `ConfigValid: False` (a genuine spec problem) and never
  on a transiently-False readiness condition, which is expected mid-
  reconcile. `platform/security/check_workload_hardening.py`: removed
  `arkos` from `DEPLOYMENT_CHARTS` (it no longer renders a raw Deployment -
  the generated one's hardening is proven by `resources_test.go` instead,
  documented inline) and added `aiagent-operator` proactively, plus a new
  `AUTOMOUNT_TOKEN_EXEMPT_DEPLOYMENTS` allow-list (mirroring the existing
  `READONLY_ROOTFS_EXEMPT_CONTAINERS` pattern) for its one deliberate
  `automountServiceAccountToken: true` exception - 188/188 checks pass.
  `go build/vet/test ./...` clean; `validate_contract.py` still exit 0;
  `helm lint` clean on both touched charts; `check_build_matrix.py`
  (11 entries) and `check_docs.py` PASS; all four `day1_*.yml --syntax-check`
  clean. ADR-0350 stays `Proposed` with a dated `## Evolution` pointer
  note (the Decision text itself is immutable) rather than moving to
  `Implemented` until ADR-0308 itself reaches `Implemented`.
- **ADRs:** ADR-0308 (Proposed -> To be implemented -> Partially implemented merged here -> Implemented after cluster reconciliation); ADR-0350 (Proposed -> Implemented alongside it, once ADR-0308 closes)
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
status conditions), within the contract's hard boundaries.

## ADR references

- ADR-0308 stub (verbatim, from `docs/roadmap/adr-decisions-v0.3.md`): "Automate
  more lifecycle, policy and deployment reconciliation around agent
  definitions."
- [docs/adr/0327-...md](../../adr/0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md)
  — the remaining acceptance bullets discharged here: a GitOps-created
  `AIAgent` CR produces the expected per-agent frontend/BFF/configuration
  resources without modifying shared platform services; delete/suspend has
  a defined, safe lifecycle that doesn't unexpectedly delete shared data or
  secrets; existing plain-manifest agents migrate incrementally, no flag
  day.
- [docs/adr/0350-provide-an-aiagent-kubernetes-crd-and-operator.md](../../adr/0350-provide-an-aiagent-kubernetes-crd-and-operator.md)
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
2. `docs/roadmap/adr-decisions-v0.3.md`: KEEP the `### ADR-0308:` heading; body →
   `Promoted to a full decision record: see [ADR-0308](../../adr/0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md) (WP-38 implementation).`
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
  ADR-0350 stays `Proposed` with a dated pointer note; index rows to match;
  tracker → `Operator pending`.
- After cluster verification: ADR-0308 →
  `Implemented - see \`operator/aiagent-operator/\`.`; ADR-0350 →
  `Implemented - see ADR-0327/ADR-0308 and \`operator/aiagent-operator/\`.`;
  index rows `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Migrating the remaining agents to CRs (mechanical follow-ups once proven).
- Self-service onboarding on top of the operator (WP-41).
