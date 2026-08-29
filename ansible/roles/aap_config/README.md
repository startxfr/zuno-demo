# Ansible role: aap_config

Registers this repository in the running AAP instance (ADR-0354 clause 4,
WP-073, Path A; extended by ADR-0418/WP-094/WP-095): the `zuno`
organization, a Controller API token, the `zuno-demo` Project / `zuno`
inventory / two credentials (`zuno-cluster-reader`, `zuno-aap-installer`)
/ 14 Job Templates - one per Day 0/1/2/3 playbook, `zuno-day0-check` plus
13 more covering every Day 1 verb (check/build/install/reconcile), Day 2
(check/build/install) and Day 3 (test/stresstest/backup/restore/check/
sign) - / 7 Workflow Templates orchestrating Day 1's and Day 2's
multi-component verbs as a DAG, as AAP resource-operator CRs
(`tower.ansible.com/v1alpha1`), and the Keycloak SSO authenticator on the
Gateway (closing ADR-0354 clause 6). Runs in `day0_components` immediately
after `aap` (ADR-0421 moved both here from Day 1, into this repo's
"always-on infra" core) - it configures a running instance, never
installs one.

## Data-driven Job Template registration (ADR-0418/WP-094)

The full set of Job Templates and their credential/Survey wiring lives in
one place, `gitops/charts/aap-config/values.yaml`'s `jobTemplates`/
`credentials` lists - `templates/jobtemplate.yaml`/`serviceaccount.yaml`/
`ansiblecredential.yaml` all `range` over them, so adding a Job Template
means adding one list entry, never touching the templates themselves.
`ansible/roles/aap_config/defaults/main.yml`'s `aap_config_job_templates`/
`aap_config_credentials` mirror the same data on the Ansible side (this
role has no templating engine to read the chart's values.yaml directly,
so the two are kept in sync by convention - the same way
`aap_config_project_name`/`aap_config_inventory_name` already mirrored
the chart's project/inventory names before this change). Only
`zuno-day0-check` (the original, live-verified-since-2026-08-25 template)
keeps its own hand-written credential-attach block in `tasks/install.yml`
- every other template is wired via `tasks/wire_job_template.yml`,
included once per `aap_config_job_templates` entry.

## Workflow Templates orchestrate Job Templates, never duplicate them (ADR-0418 clause 6/WP-095)

`gitops/charts/aap-config/values.yaml`'s `workflowTemplates` list defines
7 `WorkflowTemplate` CRs (Day 1 install/check/reconcile/build, Day 2
install/check/build - no Day 3, its verbs have no cross-component
sequencing). **Every node in every workflow launches the SAME underlying
Job Template** named by the workflow's own `.jobTemplate` field (already
registered above) - a workflow does not need one Job Template per
component, only a different `extra_data.target_component` per node.
`templates/workflowtemplate.yaml` renders each node's
`identifier`/`unified_job_template`/`extra_data`/
`related.success_nodes`/`all_parents_must_converge` straight from each
`workflowTemplates[].nodes[]` entry's `id`/`successNodes`/
`allParentsMustConverge` - the DAG shape lives entirely in data, the
template only maps it 1:1 into the CR.

Confirmed live 2026-08-30: this cluster's AAP resource operator ships a
`WorkflowTemplate` CRD (`tower.ansible.com/v1alpha1`, same Path A as every
other CR here - `oc api-resources | grep -i workflow`, careful to qualify
`workflowtemplates.tower.ansible.com` explicitly since the bare
`workflowtemplate` resource name resolves to Argo's own unrelated
`argoproj.io` CRD of the same kind name on this cluster). Its
`workflow_nodes` field carries **no CRD-documented schema**
(`x-kubernetes-preserve-unknown-fields: true` - `oc explain
workflowtemplates.tower.ansible.com.spec` lists it as `required` but
undocumented). The shape `templates/workflowtemplate.yaml` renders is the
underlying resource-operator role's own `awx.awx.workflow_job_template`
Ansible module's documented `workflow_nodes` argument spec, fetched from
its upstream source (not assumed) - **not yet confirmed to reconcile
successfully against this specific cluster's resource-operator version**;
that live confirmation is WP-095's own deferred Acceptance check.

No credential or Survey wiring exists for Workflow Templates themselves
(unlike Job Templates) - nothing to attach, since every node's Job
Template already carries its own credential from the section above.
`tasks/install.yml` only waits for each Workflow Template CR to produce a
real Controller object (`aap_config_workflow_templates`, defaults/
main.yml - names only, no credential/survey data needed).

The DAG edges themselves (which components run in parallel, which
converge) are a best-effort encoding of the dependency rationale already
documented in `ansible/playbooks/day1_install.yml`'s/`day2_install.yml`'s
header comments and each component role's own README - cross-checked
mechanically (no broken edges, no cycles, every multi-parent node flagged
`allParentsMustConverge`, every node's `target_component` matches its
Job Template's Survey component list exactly) but **not yet exercised
against a real Controller**. Two edges are flagged in `values.yaml`'s own
comments as needing live re-verification before being trusted: whether
`kiali`/`grafana` truly have no install-order dependency on each other
(only a runtime config reference is confirmed), and Day 2's `rag`/
`rag-ingestion`/`mcp` parallel group (less documented than Day 1's).

## What is a CR vs an API call

The `tower.ansible.com` CRDs are shipped by `gitops/charts/aap`'s own
operator Subscription (confirmed live, WP-072's CRD inventory - no second
Subscription; `application-d0.yaml` is a no-op). Everything that *has* a
CRD is rendered declaratively by `gitops/charts/aap-config`; the rest is
driven through the Gateway/Controller API by `tasks/install.yml`, all
idempotent GET-then-POST (same `ansible.builtin.uri` Basic-auth pattern
`ansible/roles/aap`'s subscription step proved live):

| Object | Mechanism | Why |
|---|---|---|
| Project, Inventory, Credential, Job Template, Workflow Template | CRs (chart) | CRDs exist |
| Organization `zuno` | API | no CRD; `AnsibleProject.spec.organization` is required and only "Default" exists on a fresh install |
| Controller API token | API + Vault | tokens are shown once; Vault `zuno/aap/controller-token` is the durable source, the chart's ExternalSecret re-materializes it as the `connection_secret` (keys `token`+`host`) every CR references |
| Inventory host `localhost` | API | the `AnsibleInventory` CRD has no host field |
| Credential→JT attachment (all 14 templates) | API | the `JobTemplate` CRD has no credentials field |
| `target_component` Survey (13 of 14 templates) | API | the `JobTemplate` CRD has no survey_spec/survey_enabled field either - `ask_variables_on_launch` alone IS a CRD field, set directly in `templates/jobtemplate.yaml` |
| Keycloak SSO authenticator + maps | API | authenticators are gateway API objects, no CRD |
| Removing AAP's shipped "Demo Project"/"Demo Job Template"/"Demo Inventory" (WP-098) | API | neither `JobTemplate` nor `AnsibleProject`'s CRD has a `state` field (only `AnsibleInventory` does), so a uniform declarative removal can't cover all three; done idempotently by name in `tasks/remove_aap_defaults.yml`, tolerant of any of the three already being absent |

## Least-privilege machine credentials (two tiers, ADR-0418/WP-094)

- `zuno-cluster-reader`: read-only Job Templates (`zuno-day0-check`, every
  `*-check`/`*-test` template) authenticate as the `aap-day0-check`
  ServiceAccount (zuno-aap) bound to the built-in `cluster-reader`
  ClusterRole.
- `zuno-aap-installer`: mutating Job Templates (install/build/reconcile on
  Day 1/Day 2, backup/restore/sign on Day 3) authenticate as the
  `aap-installer` ServiceAccount bound to the repo-defined
  `zuno-aap-installer` ClusterRole
  (`gitops/charts/aap-config/templates/clusterrole-installer.yaml`) -
  resource-type-scoped to this repo's own GitOps Applications, OLM
  objects and the CRDs each Day 1/Day 2 operator owns, confirmed against
  this cluster's live `oc api-resources` output. Deliberately excludes
  ClusterRole/ClusterRoleBinding (no privilege-escalation path) and
  `aap`/`tower`/`automationcontroller`/`automationhub`/`eda`.ansible.com
  themselves (`aap`/`aap-config` are Day 0 bootstrap components with their
  own kubeconfig-based install path, not something a Day 1/2 Job Template
  should reconfigure).

Both are consumed through `AnsibleCredential`'s native
`kubernetes_api`/`kubernetes_bearer_token_secret` fields - never the
bootstrap cluster-admin kubeconfig (ADR-0354 Security considerations,
narrowed per WP-073, extended per WP-094). If a precheck or install ever
fails on permissions, widen with a targeted extra Role/ClusterRole entry,
never swap in a broader built-in or cluster-admin.
`ansible/tasks/load_k8s_auth_env.yml` detects the credential's injected
`K8S_AUTH_HOST` and skips its kubeconfig resolution, so the same
playbooks run unmodified from an operator shell and from AAP.

## Keycloak SSO

The 2.7 gateway ships a native `keycloak` authenticator plugin (confirmed
live via `/api/gateway/v1/authenticator_plugins/`). `tasks/install.yml`
creates an authenticator "Keycloak zuno" against the `aap` realm client
WP-072 registered (secret read from zuno-auth's `aap-client-secret`, the
realm's RSA public key fetched live from the realm's public endpoint, both
OAuth URLs set explicitly - the plugin's defaults carry the legacy
`/auth/` prefix RHBK dropped, `GROUPS_CLAIM=groups`), plus two maps:
`ocp-paas-ops` → superuser (revoking - membership tracked both ways) and
allow-all-authenticated (viewer-level until Controller RBAC grants more -
launch-RBAC hardening is ADR-0418's scope). The local admin login stays as
fallback. If `aap-client-secret` isn't materialized yet, the SSO wiring is
skipped with a message and picked up on the next install run.

An existing authenticator is never PATCHed - config drift (e.g. a rotated
client secret) is fixed by deleting the authenticator in the Gateway UI
and re-running `make d0 install aap-config`.

## Known limitation: `aap-day0-check` cannot confirm vault's seal state

Confirmed live 2026-08-25, first real `zuno-day0-check` run: `vault`'s
`precheck.yml` calls `vault status` via `pods/exec` to determine whether
the server is unsealed - `cluster-reader` does not grant `pods/exec`
(unlike `secrets`, it's not merely excluded, it's entirely absent from
the built-in role), so that step never runs and `vault` always reports
"NOT installed" through this credential, even when it's healthy. **This
was left unfixed on purpose**: unlike the Secrets read
(`rolebinding-vault-secrets.yaml`, existence/metadata only), `pods/exec`
is execute-any-command-in-that-pod, not a bounded read - RBAC has no
finer-grained way to scope it to just the `vault status` invocation. The
operator decided this one false negative is an acceptable trade against
widening the credential's capability class. `make d0 check vault` from
an operator shell (cluster-admin) remains the source of truth for vault's
real state; `zuno-day0-check`'s report should be read with that one
known gap in mind.

## What's unverified against a live cluster

Everything above the API layer was confirmed live on 2026-08-25 (CRD
schemas via `oc explain`/openAPIV3Schema, plugin configuration_schema,
org/inventory/authenticator state, Controller service). Still unverified
until the first real `make d0 install aap-config`:

- The `connection_secret`'s expected key pair (`token`+`host`) and the
  credential `type` name string ("OpenShift or Kubernetes API Bearer
  Token") - read the resource-operator logs if a CR sits unreconciled.
- The authenticator_map trigger shapes (`{"always": {}}`,
  `{"groups": {"has_or": [...]}}`) against the 2.7 gateway.
- Whether the default execution environment carries `kubernetes.core` -
  the first Job Template launch is a deliberate diagnostic; a custom EE
  is out of scope for WP-073 (stop and report if needed).
