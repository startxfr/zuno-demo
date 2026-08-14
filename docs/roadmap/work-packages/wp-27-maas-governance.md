# WP-27: MaaS governance plane completion

- **State:** Not started
- **ADRs:** ADR-0201 (To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-03 (merged)
- **Estimated files touched:** ~8

> Execute this brief as a standalone task from the repository root. This is
> the most cluster-dependent WP in Phase 2: the repo work is manifests,
> wiring and tests; every acceptance bullet needs the live MaaS environment
> to discharge.

## Goal

Complete OpenShift AI MaaS as the model access/consumption governance plane
behind WP-03's Zuno policy router: publish local models through MaaS, define
group-based subscriptions and authorization policies as GitOps manifests,
wire API-key lifecycle and usage-metric correlation, keeping Zuno the
stricter outer policy.

## ADR references

Primary: [docs/adr/0201-complete-the-openshift-ai-maas-governance-plane-integration.md](../../adr/0201-complete-the-openshift-ai-maas-governance-plane-integration.md)
(read its full "Required v0.1 implementation" numbered list — items 1–8).

Acceptance criteria: at least one local Zuno model is published and consumable through MaaS; at least two identity groups demonstrate different `MaaSSubscription`/model access; `MaaSAuthPolicy` enforcement is proven by positive and negative tests; a Zuno Agent Runtime request traverses Zuno policy routing and MaaS end to end; usage metrics can be correlated with a Zuno request trace; external-model egress, if enabled, is explicitly marked optional per its OpenShift AI lifecycle and is blocked for classifications/policies that disallow it.

Named resources: `DataScienceCluster.spec.components.kserve.modelsAsService.managementState`,
`maas-default-gateway`, `MaaSModelRef`, `MaaSSubscription`, `MaaSAuthPolicy`;
Connectivity Link + LeaderWorkerSet operators are already installed
prerequisites (ADR-0317).

## Preconditions (verify before starting)

- WP-03 merged (adapter exists, coverage doc started).
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `gitops/charts/openshift-ai/values.yaml` (whether
  `modelsAsService` is already Managed — ADR-0343 completed MaaS/Ray DSC
  prerequisites), `gitops/charts/models/` (how models deploy),
  `gitops/charts/keycloak/files/realm-zuno.json` (groups available for
  subscriptions), `components/ai-gateway/app/` (WP-03 adapter).

## Repo changes (step by step)

1. **Manifests:** add MaaS governance resources to a chart (extend
   `gitops/charts/models/` or create `gitops/charts/maas/` mirroring chart
   conventions): `MaaSModelRef` for at least one existing local model,
   two `MaaSSubscription`s bound to two distinct Keycloak-aligned groups,
   and `MaaSAuthPolicy` proving an unentitled group/model combination is
   denied. All parameterized in values; schema-check the CRD shapes against
   the OpenShift AI 3.5 documentation and mark any uncertain field with a
   `# verify-on-cluster` comment rather than guessing silently.
2. **API-key lifecycle:** document + wire the programmatic-client key flow
   (creation/rotation via MaaS) into the ai-gateway adapter configuration;
   browser-path requests keep trusted user identity through Zuno (no keys
   in the browser path).
3. **Usage correlation:** ensure the adapter forwards/records the Zuno trace
   ID such that MaaS token/request metrics can be joined to Zuno traces;
   add the correlation field to the gateway's usage instrumentation.
4. **External egress guard:** config flag marking external-model egress
   optional/lifecycle-gated; security-negative test that a policy-blocked
   classification cannot reach an external model through MaaS even when
   subscribed (reuses WP-03's test pattern).
5. **Day 1 check:** extend the models/openshift-ai check path to assert the
   MaaS resources reconcile (follow existing check-task style; skip
   gracefully when MaaS is not enabled).

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set
  (**`ansible/roles/openshift_ai/` may be in it** — stop and ask if still
  dirty).
- Zuno's outer-policy ordering from WP-03 (MaaS never widens Zuno policy).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `helm lint` + `helm template` on the touched chart (all MaaS resources render)
- `python3 -m pytest components/ai-gateway/ -q`
- `ansible-playbook ansible/playbooks/day1_check.yml --syntax-check`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. Operator: sync + verify each numbered acceptance bullet on the live
   cluster (publish, two-group subscription difference, AuthPolicy deny,
   end-to-end request, metric/trace correlation), correcting any
   `# verify-on-cluster` field mismatches as a follow-up change.
2. Operator + user: decide whether external-model egress via MaaS is enabled
   for this environment (lifecycle acceptability per the ADR).

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0201 →
  `Partially implemented (governance manifests, key lifecycle, correlation and guards merged; live MaaS verification pending)`;
  index row to match; tracker → `Operator pending`.
- After operator verification: ADR-0201 →
  `Implemented - see \`gitops/charts/\` MaaS resources, \`components/ai-gateway/app/\`.`;
  index row `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Removing legacy gateway capabilities (WP-03's post-comparison decision).
- vLLM-on-MaaS / llm-d Tech Preview paths (ADR-0201 item 8 — evaluate, do
  not force into the mandatory path).
