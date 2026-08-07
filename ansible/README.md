# Ansible Automation

Ansible is a thin bootstrapper behind the public `make` interface, not the
configuration engine - see ADR-0022, ADR-0024 and ADR-0056. It exists to
get from "a bare cluster-admin token" to "ArgoCD is reconciling everything
else", structured as Day 0 (cluster prerequisites) and Day 1 (build +
run the platform):

1. `make day0 check` / `install` / `uninstall` (or the `d0` alias) walk
   `DAY0_COMPONENTS` in order (`admin-context`, `argocd`,
   `namespaces`, `vault`, `cert-manager`, `external-secrets`, `keycloak`,
   `postgresql`, `smtp`, `nfd`, `nvidia-gpu`, `observability`,
   `openshift-ai`) - `uninstall` walks it in reverse. `admin_context`
   checks the cluster API and applies PriorityClasses/verifies a
   StorageClass exists; `argocd` installs the OpenShift GitOps operator
   and the zuno `AppProject`; `namespaces` applies the namespace/quota/
   NetworkPolicy baseline (needs `argocd`'s `Application` CRD); `vault`
   installs itself as a GitOps Application, then imperatively
   initializes/unseals it (the one component that can't depend on Vault
   for its own bootstrap secret); `cert_manager` installs cert-manager and
   a Vault-backed `ClusterIssuer` (infrastructure only for now - no
   existing Route/service consumes it yet); `external-secrets` installs
   the operator and the Vault-backed `ClusterSecretStore`. `make day0 all
   [component]` runs check → install in sequence.
2. `make day1 check` / `build` / `install` / `uninstall` (or the `d1`
   alias) walk `DAY1_COMPONENTS` (`llm`, `models`, `sql_schema`, `rag`,
   `mcp`, `agents`, `mlops`) - `uninstall` walks the same list in
   reverse. Every scope applies its own child ArgoCD `Application` under
   `gitops/apps/<scope>/` via the shared task
   `ansible/tasks/apply_gitops_app.yml`, rather than configuring anything
   inline - ArgoCD reconciles the referenced Helm chart or local manifest.
   `make day1 check agents` runs the ADR-0053 acceptance/security gate
   (what `make check` used to run) instead of a lightweight state check -
   see `ansible/playbooks/day1_check.yml`'s header comment. `make day1
   build [mcp|rag|agent]` builds the platform's own component images via
   OpenShift `BuildConfig`/`ImageStream` in `zuno-ai-build`.

No secret is ever written to a Git-tracked file. Anything a role needs at
run time comes from Vault via the `community.hashi_vault` lookup plugin;
anything a workload needs comes from an `ExternalSecret`.

Before the first `make day0|d0 install` (specifically before installing
`vault`), copy `ansible/confidential.example.yml` to `ansible/confidential.yml`
and fill in the values (Google OAuth client, SMTP technical credentials,
Atlassian Confluence token) - the `vault` role fails fast if this file is
missing, and reads it on every run to (re-)seed Vault, so it can be deleted
again afterwards unless Vault needs to be reinstalled. `ansible/confidential.yml`
is gitignored; never commit it.

Install the required collections once: `ansible-galaxy collection install -r requirements.yml`.

Every role keeps the same `precheck` / `install` / `uninstall` task file
names (`day0`/`day1 check`/`install`/`uninstall` map onto them) so a
single component remains independently runnable. `precheck.yml` never
fails - it detects state (a GitOps Application's Synced+Healthy status
where one exists, otherwise the concrete objects the role's own
`install.yml` creates) and sets a `<role>_state_installed` fact plus a
line in a shared `/tmp/zuno-statereport-*` file, displayed at the end of
the check run (see `ansible/tasks/{init_state_report,
check_gitops_app_state,record_state}.yml`). `uninstall.yml` reverses
`install.yml` - mostly by deleting the component's ArgoCD `Application`;
shared platform Namespaces are left in place and are the `namespaces`
role's own responsibility.
