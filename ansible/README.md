# Ansible Automation

Ansible is a thin bootstrapper behind the public `make` interface, not the
configuration engine - see ADR-0022, ADR-0024 and ADR-0056. It exists to
get from "a bare cluster-admin token" to "ArgoCD is reconciling everything
else", structured as Day 0 (cluster prerequisites) and Day 1 (build +
run the platform):

1. `make day0 check` / `install` / `configure` (or the `d0` alias) walk
   `DAY0_COMPONENTS` in order (`admin-context`, `argocd`, `namespaces`,
   `vault`, `keycloak`, `postgresql`, `smtp`, `external-secrets`, `nfd`,
   `nvidia-gpu`, `observability`, `openshift-ai`). `admin_context` checks
   the cluster API and applies PriorityClasses/verifies a StorageClass
   exists; `argocd` installs the OpenShift GitOps operator; `namespaces`
   applies the namespace/quota/NetworkPolicy baseline (needs `argocd`'s
   `Application` CRD); `vault` installs itself as a GitOps Application,
   then imperatively initializes/unseals (the one component that can't
   depend on Vault for its own bootstrap secret); `external-secrets`
   installs the operator. `make day0 all [component]` runs
   check → install → configure in sequence.
2. `make day1 check` / `configure` / `run` (or the `d1` alias) walk
   `DAY1_COMPONENTS` (`llm`, `models`, `sql_schema`, `rag`, `mcp`,
   `agents`, `mlops`) - `configure` and `run` are the same operation.
   Every scope applies its own child ArgoCD `Application` under
   `gitops/apps/<scope>/` via the shared task
   `ansible/tasks/apply_gitops_app.yml`, rather than configuring anything
   inline - ArgoCD reconciles the referenced Helm chart or local manifest.
   `make day1 check agents` runs the ADR-0053 acceptance/security gate
   (what `make check` used to run) rather than a dependency precheck - see
   `ansible/playbooks/day1_check.yml`'s header comment. `make day1 build
   [mcp|rag|agent]` builds the platform's own component images via
   OpenShift `BuildConfig`/`ImageStream` in `zuno-ai-build`.

No secret is ever written to a Git-tracked file. Anything a role needs at
run time comes from Vault via the `community.hashi_vault` lookup plugin;
anything a workload needs comes from an `ExternalSecret`.

Install the required collections once: `ansible-galaxy collection install -r requirements.yml`.

Every role keeps the existing `precheck` / `prepare` / `configure` task
file names (`day0 check`/`install`/`configure` and `day1 check`/
`configure`/`run` map onto them - ADR-0056 renamed the `make`-level verbs,
not the underlying Ansible task files) so a single component remains
independently runnable.
