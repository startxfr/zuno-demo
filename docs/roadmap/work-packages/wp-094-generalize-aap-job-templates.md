# WP-094: Generalize the Job Template mechanism, register every Day 1/2/3 playbook

- **State:** Repo work merged - live verification pending.
- **ADRs:** ADR-0418 (amended, clause 1 extended + new clause 6).
- **Depends on:** WP-093/ADR-0421 (final Day 0/Day 1 component placement
  had to be settled first - a Job Template's `playbook` field is
  `day<N>_<verb>.yml`).
- **Unblocks:** WP-095 (Workflow Templates), WP-096 (`make` routing via
  `zuno_make_aap_mode`).
- **Estimated files touched:** ~9 (`gitops/charts/aap-config/values.yaml`
  + 4 templates + 1 new; `ansible/roles/aap_config/` 1 new defaults file,
  1 new task file, `install.yml`, `README.md`; `docs/adr/0418-*.md`).

> Execute this brief as a standalone task from the repository root.

## Goal

Turn `aap-config`'s single hardcoded `zuno-day0-check` Job Template into a
data-driven mechanism registering one Job Template per Day 1/Day 2/Day 3
playbook (13 new, 14 total), each with the correct least-privilege
credential and, where the underlying Makefile verb takes a component, a
Controller Survey offering `target_component` as a `multiplechoice` list
- never free text.

## ADR references

ADR-0418 clause 1 (extended) and clause 6 (new) - see the 2026-08-30
amendment notes in `docs/adr/0418-*.md`.

## Preconditions (verify before starting)

- WP-093/ADR-0421 merged (Day 0/Day 1 component lists final).
- Live cluster access to confirm `oc api-resources | grep -i tower` still
  shows the same `tower.ansible.com` CRDs WP-073 originally inventoried
  (`JobTemplate`, `AnsibleCredential`, `AnsibleProject`, `AnsibleInventory`
  - read-only check, no mutation).

## Repo changes (step by step)

1. `gitops/charts/aap-config/values.yaml`: replace the singular
   `jobTemplate`/`credential`/`serviceAccount` keys with `jobTemplates`
   (14-entry list: name/playbook/credential/askVariablesOnLaunch/
   surveyComponents) and `credentials` (2-entry list:
   `zuno-cluster-reader`/`zuno-aap-installer`, each with
   serviceAccount/clusterRole/type/kubernetesApi/description).
2. `templates/jobtemplate.yaml`, `templates/serviceaccount.yaml`,
   `templates/ansiblecredential.yaml`: convert each from a single
   resource to a `{{- range ... }}` loop over the new lists.
   `templates/rolebinding-vault-secrets.yaml`: its Secrets-read Role stays
   scoped to the cluster-reader tier alone - fixed its subject lookup
   (previously `.Values.serviceAccount.name`, now a `range` that filters
   `.Values.credentials` for the `zuno-cluster-reader` entry).
3. New `templates/clusterrole-installer.yaml`: the `zuno-aap-installer`
   ClusterRole - resource-type-scoped to this repo's own GitOps
   Applications, OLM Subscription/OperatorGroup objects, ExternalSecrets,
   core/apps/batch/networking/route objects, namespaced Role/RoleBinding,
   and every CRD group the live cluster's `oc api-resources` confirmed for
   service-mesh/Kuadrant/MariaDB/Kueue/JobSet/KEDA/NVIDIA-GPU/Lightspeed/
   OpenShift AI/RHOAI/`zuno.zuno.ai` (Day 2's AIAgent). Deliberately
   excludes ClusterRole/ClusterRoleBinding (no privilege-escalation path)
   and `aap.ansible.com`/`tower.ansible.com`/
   `automation{controller,hub}.ansible.com`/`eda.ansible.com` themselves.
4. New `ansible/roles/aap_config/defaults/main.yml`: `aap_config_
   job_templates`/`aap_config_credentials`, mirroring the chart's
   values.yaml (kept in sync by convention, same as this role's existing
   `aap_config_project_name`/`aap_config_inventory_name` pattern - no
   shared templating engine exists between Helm and this role).
5. New `ansible/roles/aap_config/tasks/wire_job_template.yml`: per-
   template credential attachment + Survey PATCH, included once per
   `aap_config_job_templates` entry from `install.yml`. The **original**
   `zuno-day0-check`-specific block in `install.yml` is left untouched
   (still feeds `_aap_config_jt_lookup`/`_aap_config_credential_lookup`
   for the mcp-aap least-privilege-identity section further down,
   ADR-0355/WP-074) - the new loop is purely additive.
6. `ansible/roles/aap_config/tasks/install.yml`: generalize the census
   (four hardcoded GETs → project/inventory + every credential + every
   Job Template) and the force-reconcile-annotation loop the same way;
   add the new `include_tasks: wire_job_template.yml` loop right after
   the existing credential-attach block.
7. `ansible/roles/aap_config/README.md`: document the data-driven
   mechanism, the two credential tiers, and the Survey/credential-
   attachment API-vs-CRD table addition.
8. `docs/adr/0418-*.md`: amend clause 1 (Day 2/Day 3 phases, two
   credential tiers, Survey-satisfies-Security-considerations), add
   clause 6 (Workflow Templates/routing named but deferred to WP-095/096),
   correct the Operational considerations section's dangling
   `ansible/tasks/aap_sync_job_templates.yml` reference (never existed -
   point at the real `values.yaml`/`wire_job_template.yml` mechanism
   instead), update Status/Implementation state to `Partially
   implemented`. `docs/adr/README.md`'s index row status updated to match.

## What NOT to touch

- The original `zuno-day0-check`-specific credential-attach block in
  `install.yml` (lines ~437-480) - still load-bearing for the mcp-aap
  section below it (ADR-0355/WP-074's least-privilege launch permission is
  deliberately scoped to that one template's `object_id`).
- `ansible/roles/aap_config/tasks/precheck.yml` - its JobTemplate-CR
  existence check stays scoped to `zuno-day0-check` alone, a deliberate
  "cheap proxy for CR presence" (its own header comment), not a
  per-template health check.
- `docs/roadmap/work-packages/wp-072-*.md`/`wp-073-*.md` - immutable
  historical records of the pre-WP-094 single-template state.
- Live cluster state - this WP's own verification was repo-only (`helm
  lint`/`helm template`/`ansible-playbook --syntax-check`/a standalone
  Jinja expression test for the generalized census/nudge loops). Applying
  the chart for real (`make d0 install aap-config`) and launching any of
  the 13 new templates is deferred to an operator-run session.

## Acceptance checks

- `helm lint gitops/charts/aap-config --set aapConfig.enabled=true` and
  `helm template ... | grep -c "^kind: JobTemplate"` show 14.
- `ansible-playbook --syntax-check ansible/playbooks/day0_install.yml`
  (exercises the whole `aap_config` role's `install.yml`/
  `wire_job_template.yml` include chain).
- A standalone offline test of the generalized census/nudge Jinja loop
  expressions (no cluster needed) confirms they enumerate all 2
  credentials + 14 Job Templates correctly.
- `python3 platform/docs/check_docs.py` passes.

## Operator / human follow-up

- Run `make d0 install aap-config` for real, confirm all 14 Job Templates
  appear in the Controller API (`GET /api/controller/v2/job_templates/`),
  each with its correct credential attached and (for the 13 with a
  Survey) `survey_enabled: true`/the expected `multiplechoice` spec.
- Manually launch at least one read-only template beyond `zuno-day0-check`
  (e.g. `zuno-day1-check` with `target_component=kiali`) to confirm the
  Survey/credential wiring actually works end to end, not just that the
  API calls that configure it returned 2xx.
- Confirm the `zuno-aap-installer` ClusterRole is sufficient for at least
  one real install-type launch (e.g. `zuno-day1-install` against a single,
  low-risk component) - widen only the specific missing verb/resource if
  a launch fails on a permissions error, never swap in a broader built-in.

## Status updates

- 2026-08-30: Repo changes merged, `check_docs.py`/`helm lint`/syntax-
  checks green. State: `Repo work merged - live verification pending`.

## Rollback

`git revert` - no live cluster state depends on this WP yet (the chart
was never applied with `aapConfig.enabled: true`'s new values during this
WP's own execution).

## Out of scope / deferred

- Workflow Templates and their parallelization DAG (WP-095).
- `make` routing via `zuno_make_aap_mode` (WP-096).
- Tightening `zuno-aap-installer` from resource-type-scoped to
  per-namespace Role scoping - a possible future refinement once live
  testing shows whether the coarser grant is actually a problem.
- Phase 3/4 launch-RBAC (who may launch which template) - ADR-0418's own
  Security considerations still flags this as open.
