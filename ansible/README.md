# Ansible Automation

Ansible is a thin bootstrapper behind the public `make` interface, not the
configuration engine - see ADR-0022, ADR-0024 and ADR-0056. It exists to
get from "a bare cluster-admin token" to "ArgoCD is reconciling everything
else", structured as Day 0 (cluster prerequisites) and Day 1 (build +
run the platform):

1. `make day0 check` / `install-check` / `configure-check` / `install` /
   `configure` / `uninstall` (or the `d0` alias) walk `DAY0_COMPONENTS` in
   order (`admin-context`, `argocd`,
   `namespaces`, `vault`, `keycloak`, `postgresql`, `smtp`,
   `external-secrets`, `nfd`, `nvidia-gpu`, `observability`,
   `openshift-ai`) - `uninstall` walks it in reverse. `admin_context`
   checks the cluster API and applies PriorityClasses/verifies a
   StorageClass exists; `argocd` installs the OpenShift GitOps operator;
   `namespaces` applies the namespace/quota/NetworkPolicy baseline (needs
   `argocd`'s `Application` CRD); `vault` installs itself as a GitOps
   Application, then imperatively initializes/unseals (the one component
   that can't depend on Vault for its own bootstrap secret);
   `external-secrets` installs the operator. `make day0 all [component]`
   runs check → install → configure in sequence.
2. `make day1 check` / `install-check` / `configure-check` / `configure` /
   `run` / `uninstall` (or the `d1` alias) walk `DAY1_COMPONENTS` (`llm`,
   `models`, `sql_schema`, `rag`, `mcp`, `agents`, `mlops`) - `configure`
   and `run` are the same operation, `uninstall` walks the same list in
   reverse. Every scope applies its own child ArgoCD `Application` under
   `gitops/apps/<scope>/` via the shared task
   `ansible/tasks/apply_gitops_app.yml`, rather than configuring anything
   inline - ArgoCD reconciles the referenced Helm chart or local manifest.
   `make day1 check|configure-check agents` runs the ADR-0053
   acceptance/security gate (what `make check` used to run) instead of a
   lightweight configure-state check - see
   `ansible/playbooks/day1_check.yml`'s header comment. `make day1 build
   [mcp|rag|agent]` builds the platform's own component images via
   OpenShift `BuildConfig`/`ImageStream` in `zuno-ai-build`.

No secret is ever written to a Git-tracked file. Anything a role needs at
run time comes from Vault via the `community.hashi_vault` lookup plugin;
anything a workload needs comes from an `ExternalSecret`.

Install the required collections once: `ansible-galaxy collection install -r requirements.yml`.

Every role keeps the same `install-precheck` / `configure-precheck` /
`install` / `configure` / `uninstall` task file names (`day0 install-check`/
`configure-check`/`install`/`configure`/`uninstall` and `day1
install-check`/`configure-check`/`configure`/`run`/`uninstall` map onto
them; `day0|d0 check`/`day1|d1 check` run both `*-precheck` files in one
pass) so a single component remains independently runnable.
`install-precheck.yml`/`configure-precheck.yml` never fail - they detect
state (a GitOps Application's Synced+Healthy status where one exists,
otherwise the concrete objects the role's own `install.yml`/`configure.yml`
create) and set `<role>_state_installed`/`_state_configured` facts plus a
line in a shared `/tmp/zuno-statereport-*` file, displayed at the end of
the check run (see `ansible/tasks/{init_state_report,
check_gitops_app_state,record_install_state,record_configure_state}.yml`).
`uninstall.yml` reverses `install.yml` (and, for GitOps-managed
components, `configure.yml`'s own `Application`) - mostly by deleting the
component's ArgoCD `Application`; shared platform Namespaces are left in
place and are the `namespaces` role's own responsibility.
