# WP-06: OGX migration and RAG provider parity

- **State:** Operator pending (2026-08-18 - operator authorized the live corpus proof this pass; genuine progress, genuine new blocker. `ogxServer.enabled` flipped true and applied for the first time. Surfaced real schema drift immediately: the ea.2 admission webhook (`vogxserver.kb.io`) accepts only `distribution.name: rh|rh-dev`, not `remote-vllm` (the 2026-08-14 `oc explain` pass predated this validation) - corrected to `rh`, committed. The `OGXServer` CR then created successfully (`zuno-ogx` in `redhat-ods-applications`) but hit a second, deeper blocker: the OGX operator's own in-process OCI-manifest fetch to `registry.redhat.io/rhoai/odh-ogx-core-rhel9@sha256:...` (needed to resolve `rh`'s generated config) returns HTTP 401, even though the cluster's global pull secret has valid `registry.redhat.io` credentials and those credentials were explicitly linked to the operator's own ServiceAccount (`oc secrets link ogx-k8s-operator-controller-manager ...  --for=pull`) with a pod bounce, user-authorized. No effect - `imagePullSecrets` govern kubelet image pulls, not an operator's own in-process HTTP registry client, which apparently needs different wiring this EA2 build doesn't document. Root cause is upstream/environment (an RHOAI 3.5 EA2 operator limitation), not a Zuno repo gap - recorded here rather than guessed around further. Corpus proof and provider-parity run remain blocked on this until either the operator ships a documented registry-credential mechanism or a newer RHOAI build fixes it. Part A (DSC migration) and the provider/tests from Part B stay merged and live as before.)
- **ADRs:** ADR-0322 (To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Blocks:** — (WP-21 benefits from the provider abstraction but does not hard-depend)
- **Estimated files touched:** ~9

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR fully before editing — its Decision section defines a v0
> migration scope and a v0.1 integration scope; this WP delivers both, but
> they can be two separate PRs in that order.

## Goal

Replace the legacy `llamastackoperator` configuration with the OGX component
on the `DataScienceCluster`, add Day 1 health checks for OGX, and implement
an OGX-backed RAG provider behind the existing retrieval contract with
parity tests — keeping pgvector as the durable vector store and the current
provider as default until parity is proven.

## ADR references

Primary: [docs/adr/0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md](../../adr/0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md)

Acceptance criteria: `llamastackoperator` is absent from the rendered `DataScienceCluster`; `spec.components.ogx.managementState: Managed` renders and reconciles; existing Tekos tests pass without the OGX provider; an OGX-backed RAG proof indexes/queries a controlled test corpus through PostgreSQL/pgvector; provider-parity tests prove metadata/ACL/classification/citation behavior before any default-provider migration.

Security: any OGX-backed retrieval path preserves initiating-user identity, source ACL/group filters, data classification, provenance/citations, and external-model egress restrictions.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- `grep -rn "llamastackoperator" gitops/ ansible/` shows where the legacy
  component is configured (expect `gitops/charts/openshift-ai/` and/or
  `ansible/roles/openshift_ai/`).
- Read: `gitops/charts/openshift-ai/values.yaml` + templates,
  `ansible/roles/openshift_ai/tasks/` (note: `install.yml`/`precheck.yml`
  may carry uncommitted ADR-0344 changes — if `git status` still shows them
  modified, coordinate with the user before touching this role),
  `components/rag-service/app/` (locate the retrieval provider abstraction),
  `docs/platform/*.md` mentions of OGX.

## Repo changes (step by step)

### Part A — v0 migration scope

1. In the `DataScienceCluster` rendering (chart values/templates found in
   preconditions): remove `llamastackoperator`, add
   `spec.components.ogx.managementState: Managed`.
2. Add a Day 1 health check proving the OGX component reconciles: follow the
   existing pattern in `ansible/roles/openshift_ai/tasks/` for how other DSC
   components' readiness is asserted.
3. Correct platform docs (`docs/platform/`, `docs/architecture/ai-architecture.md`
   if applicable) so OGX is described as the discrete OpenShift AI component,
   not an umbrella term. Run `python3 platform/docs/check_docs.py` after.

### Part B — v0.1 integration scope

4. Implement an OGX-backed retrieval provider in
   `components/rag-service/app/` behind the same provider interface the
   current pgvector provider implements (mirror the existing provider; do
   not change the retrieval contract). Selection via configuration; default
   remains the current provider.
5. Parity tests: same corpus fixture through both providers must produce
   equivalent metadata filtering, `acl_groups` enforcement, classification
   tagging and citations. Mock the OGX API in CI.
6. Trace the provider used per request (mirror existing telemetry fields).

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set
  (**high risk here** — `ansible/roles/openshift_ai/tasks/install.yml` and
  `precheck.yml` are in that set; if still uncommitted, stop and ask).
- Default retrieval provider — stays pgvector until the operator confirms
  parity on cluster.
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `! grep -rn "llamastackoperator" gitops/ ansible/`
- `helm template gitops/charts/openshift-ai | grep -A1 "ogx"` shows `managementState: Managed`
- `helm lint gitops/charts/openshift-ai`
- `python3 -m pytest components/rag-service/tests/ -q`
- `ansible-playbook ansible/playbooks/day1_check.yml --syntax-check`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. Operator: `make d0 install openshift-ai` (or `make d0 reconcile
   openshift-ai`) on the cluster; confirm the DSC reconciles with OGX
   Managed — discharges acceptance bullet 2.
2. Operator: run the OGX-backed proof against a controlled corpus on
   live PostgreSQL/pgvector — discharges bullet 4.
3. Operator + user: review parity evidence and decide whether/when any task
   switches provider default; record the lifecycle status of enabled OGX
   capabilities in `docs/platform/` per the ADR's operational section.

## Status updates (then re-run check_docs.py)

- After repo merge (parts A+B): ADR-0322 body status →
  `Partially implemented (DSC migration, health checks, OGX provider and parity tests merged; live reconciliation and corpus proof pending)`;
  index row to match; tracker → `Operator pending`; this file's State.
- After operator steps: ADR-0322 →
  `Implemented - see \`gitops/charts/openshift-ai/\`, \`components/rag-service/app/\`.`;
  index row `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Multi-domain RAG generalization (WP-21 / ADR-0204).
- Switching the default provider to OGX (operator decision post-parity).
