# WP-095: Register Day 1/Day 2 Workflow Templates with parallelization

- **State:** Repo work merged - live verification pending.
- **ADRs:** ADR-0418 (amended, clause 6 - Workflow Template half).
- **Depends on:** WP-094 (every workflow node launches an already-
  registered Job Template).
- **Unblocks:** WP-096 (`make` routing needs a Workflow Template to route
  to).
- **Estimated files touched:** 4 (`gitops/charts/aap-config/values.yaml`,
  1 new template, `ansible/roles/aap_config/defaults/main.yml`,
  `tasks/install.yml`, `README.md`; `docs/adr/0418-*.md`).

> Execute this brief as a standalone task from the repository root.

## Goal

Register 7 AAP Workflow Templates (Day 1: install/check/reconcile/build;
Day 2: install/check/build) that orchestrate each verb's components as a
DAG, parallelizing components with no dependency on each other, using
only the Job Templates WP-094 already registered - no new Job Template
per component.

## ADR references

ADR-0418 clause 6 (Workflow Template half) - see the 2026-08-30 amendment
in `docs/adr/0418-*.md`.

## Preconditions (verify before starting)

- WP-094 merged (all 14 Job Templates registered, each with the correct
  credential/Survey).
- Live, read-only confirmation that `tower.ansible.com/v1alpha1` ships a
  `WorkflowTemplate` CRD on this cluster (`oc api-resources | grep -i
  workflow` - **qualify the resource explicitly as
  `workflowtemplates.tower.ansible.com`**, the bare `workflowtemplate`
  name resolves to Argo's own unrelated CRD of the same kind name on this
  cluster, confirmed live 2026-08-30 via `oc explain workflowtemplate`
  vs `oc explain workflowtemplates.tower.ansible.com`).
- Since the CRD's `workflow_nodes` field has no CRD-documented schema
  (`x-kubernetes-preserve-unknown-fields: true`), fetch the underlying
  resource-operator role's actual `awx.awx.workflow_job_template` Ansible
  module invocation (`curl -s https://raw.githubusercontent.com/ansible/
  awx-resource-operator/devel/roles/workflowtemplate/tasks/main.yml`) and
  the module's own documented `workflow_nodes` argument spec (`curl -s
  https://raw.githubusercontent.com/ansible/awx/devel/awx_collection/
  plugins/modules/workflow_job_template.py`) to confirm the exact field
  names before writing the chart template - do not guess or trust a
  generic web-search example verbatim (one such example found during this
  WP had `unified_job_template.inventory.organization.name` instead of
  the module's actually-documented, mutually-exclusive-correct
  `unified_job_template.organization.name` for a `job_template`-type
  node).

## Repo changes (step by step)

1. `gitops/charts/aap-config/values.yaml`: add `workflowTemplates` (7
   entries: `name`, `jobTemplate` - the underlying Job Template every
   node launches - and `nodes`, each `{id, successNodes, 
   allParentsMustConverge?}`). Day 1 install/check/reconcile share an
   identical component graph via a YAML anchor (`&day1ComponentDag`) -
   only which Job Template the workflow launches differs.
2. New `templates/workflowtemplate.yaml`: renders each entry into a
   `WorkflowTemplate` CR, mapping `nodes[]` 1:1 into `workflow_nodes`
   (`identifier`, `unified_job_template: {name: <jobTemplate>,
   organization: {name: <org>}, type: job_template}`,
   `extra_data.target_component`, `related.success_nodes` from
   `successNodes`, `all_parents_must_converge` when set). Sync-wave `"0"`
   - after every JobTemplate's `"-5"`, since a workflow node resolves
   `unified_job_template.name` against an already-existing Controller
   Job Template.
3. `ansible/roles/aap_config/defaults/main.yml`: add
   `aap_config_workflow_templates` (names only - no credential/Survey
   data needed, workflows carry none of their own).
4. `ansible/roles/aap_config/tasks/install.yml`: extend the existing
   census loop (`workflow_job_templates` path) and force-reconcile loop
   (`WorkflowTemplate` kind) to also cover
   `aap_config_workflow_templates`; add a new "wait for every Workflow
   Template to exist in Controller" loop (existence-only, no
   credential/Survey wiring needed).
5. `ansible/roles/aap_config/README.md`: new "Workflow Templates
   orchestrate Job Templates, never duplicate them" section; add a
   Workflow Template row to the CR-vs-API-call table.
6. `docs/adr/0418-*.md`: clause 6 updated from "not decided by this
   clause" to "decided and registered - repo work merged, live
   verification pending" for the Workflow Template half specifically
   (routing, WP-096, stays fully open). Implementation state section
   updated to mention WP-095 alongside WP-094.

## DAG design (verify against a live Controller before fully trusting)

Day 1 install/check/reconcile (20 nodes, identical graph): `smtp`/`nfd`/
`custom-metrics-autoscaler` launch as roots (no dependency beyond Day 0's
`machines`); `nvidia-gpu` waits on `nfd` alone (ADR-0047); `redis` waits
on all three of `smtp`/`custom-metrics-autoscaler`/`nvidia-gpu`
(`allParentsMustConverge`); serial `observability` → `service-mesh` →
`mesh-monitoring`; `kiali`/`grafana` both wait on `mesh-monitoring` alone
(**not yet confirmed no runtime dependency exists between them beyond
config** - re-verify before trusting); `mariadb` waits on both
(`allParentsMustConverge`); serial `tempo` → `openshift-oauth` →
`connectivity-link`; `lws`/`jobset`/`kueue` all wait on
`connectivity-link` alone; `openshift-ai` waits on all three
(`allParentsMustConverge`); serial `lightspeed` → `aiagent-operator`
(terminal). Day 1 build (3 nodes): `supply-chain-signer` (root) →
`ai-gateway`/`aiagent-operator` (parallel, image-signing dependency only).
Day 2 install (9 nodes)/check (10 nodes, adds a `supply-chain` tail):
serial `namespaces` → `llm` → `models`; `rag`/`rag-ingestion`/`mcp` all
wait on `models` alone (**less documented than Day 1's edges - re-verify**);
`agents` waits on all three (`allParentsMustConverge`); serial `mlops` →
`lightspeed-config` (→ `supply-chain` for check). Day 2 build (5 nodes):
`mcp`/`rag`/`rag-ingestion`/`agent`/`mlops` all launch as independent
roots, no edges - separate BuildConfigs with no ordering dependency.

## What NOT to touch

- Any of WP-094's Job Templates, their credentials, or their Surveys -
  Workflow Templates only reference them by name, never modify them.
- Live cluster state - this WP's own verification was repo-only (`helm
  lint`/`helm template` plus an offline Python script validating every
  rendered DAG: no broken edges, no cycles, every `allParentsMustConverge`
  node has ≥2 incoming edges and vice versa, every node's
  `target_component` set matches its Job Template's Survey exactly).
  Applying the chart and launching any Workflow Template for real is
  deferred to an operator-run session.

## Acceptance checks

- `helm lint`/`helm template gitops/charts/aap-config --set
  aapConfig.enabled=true` renders exactly 7 `WorkflowTemplate` objects
  with the expected node counts (20/20/20/3/9/10/5).
- Offline DAG validation (Python, `yaml.safe_load_all` on the rendered
  manifests): zero broken edges, zero cycles, `all_parents_must_converge`
  set on every node with >1 incoming edge and only those, every
  workflow's node-id set equal to its underlying Job Template's
  `surveyComponents` set.
- `ansible-playbook --syntax-check ansible/playbooks/day0_install.yml`
  (exercises the extended census/nudge/wait loops).
- `python3 platform/docs/check_docs.py` passes.

## Operator / human follow-up

- Run `make d0 install aap-config` for real (same operator action WP-094
  already deferred - this WP adds to the same install run, not a second
  one).
- Confirm all 7 Workflow Templates appear in the Controller API (`GET
  /api/controller/v2/workflow_job_templates/`) and that
  `GET .../workflow_nodes/` on at least one shows the expected
  identifier/edge structure - this is the first real confirmation that
  the `awx.awx.workflow_job_template`-derived `workflow_nodes` shape this
  WP assumed actually reconciles against this cluster's resource-operator
  version (flagged as unconfirmed throughout this WP's own comments).
- Launch `zuno-day1-check` (read-only, safe) and confirm live in the
  Controller UI/API that each wave's nodes start with the same/near-
  identical timestamp (proving real parallelism, not an accidental serial
  fallback) and that the workflow completes successfully end to end.
- Re-verify the two flagged uncertain edges (`kiali`/`grafana`; Day 2's
  `rag`/`rag-ingestion`/`mcp`) against real component behavior; adjust
  `values.yaml` if either turns out to have a real dependency the current
  graph is missing.

## Status updates

- 2026-08-30: Repo changes merged, `check_docs.py`/`helm lint`/syntax-
  checks/offline DAG validation all green. State: `Repo work merged -
  live verification pending`.

## Rollback

`git revert` - no live cluster state depends on this WP yet.

## Out of scope / deferred

- `make` routing via `zuno_make_aap_mode` (WP-096).
- A Workflow Template for Day 0 or Day 3 - explicitly not decided by
  ADR-0418 clause 6 (Day 0 bootstraps AAP itself; Day 3 has no
  cross-component sequencing to orchestrate).
- Per-launch Survey on a Workflow Template (e.g. "run only this one
  component's subtree") - every workflow always runs its full DAG,
  matching `make d1 install` with no component argument; a narrower
  per-node launch stays available directly via the underlying Job
  Template (WP-094), unchanged.
