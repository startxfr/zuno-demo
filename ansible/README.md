# Ansible Automation

Ansible is a thin bootstrapper behind the public `make` interface, not the
configuration engine. It exists to get from "a bare cluster-admin token" to
"ArgoCD is reconciling everything else", structured as four sequential
tiers (ADR-0056/ADR-0060): Day 0 (cluster prerequisites), Day 1 (the
AI-platform-operator stack), Day 2 (AI infrastructure + content
ingestion), and Day 3 (agent test/stresstest operations):

1. `make day0 check` / `install` / `uninstall` (or the `d0` alias) walk
   `DAY0_COMPONENTS` in order (`admin-context`, `argocd`,
   `namespaces`, `openshift-rbac-groups`, `vault`, `cert-manager`,
   `external-secrets`, `openshift-oauth`, `smtp`, `machines`, `nfd`,
   `nvidia-gpu`, `custom-metrics-autoscaler`) - `uninstall` walks it in
   reverse. `admin_context` checks the cluster API and applies
   PriorityClasses/verifies a StorageClass exists; `argocd` installs the
   OpenShift GitOps operator and the zuno `AppProject`; `namespaces`
   applies the bare Namespace objects (its ResourceQuota/NetworkPolicy
   overlay is Day 2, see below); `vault` installs itself as a GitOps
   Application, then imperatively initializes/unseals it; `cert_manager`
   installs cert-manager and a Vault-backed `ClusterIssuer`;
   `external-secrets` installs the operator and the Vault-backed
   `ClusterSecretStore`. `make day0 all [component]` runs check → install
   in sequence.
2. `make day1 check` / `build` / `install` / `uninstall` (or the `d1`
   alias) walk `DAY1_RUN_COMPONENTS` - the AI-platform-operator stack
   (`redis`, `observability`, `service-mesh`, `mesh-monitoring`, `kiali`,
   `grafana`, `postgresql`, `mariadb`, `tempo`, `keycloak`,
   `openshift-oauth`, `aap`, `connectivity-link`, `lws`, `jobset`, `kueue`,
   `openshift-ai`, `aiagent-operator`) - `uninstall` walks the same list in
   reverse. `aap` (ADR-0354) installs Ansible Automation Platform
   (Gateway/Controller/Hub/EDA), non-HA, right after `openshift-oauth` -
   its own dedicated PostgreSQL databases and Keycloak OIDC client both
   need `postgresql`/`keycloak` already live.
   `aiagent-operator` runs last (operator-before-CR: Day 2's `agents`
   creates the CRs it reconciles). `make day1 build` only builds
   `ai-gateway`.
3. `make day2 check` / `build` / `install` / `uninstall` (or the `d2`
   alias) walk `DAY2_RUN_COMPONENTS` - `namespaces`' ResourceQuota/
   NetworkPolicy overlay, then AI infrastructure and content ingestion
   (`llm`, `models`, `sql-schema`, `rag`, `rag-ingestion`, `mcp`,
   `agents`, `mlops`). Every scope applies its own child ArgoCD
   `Application` under `gitops/apps/<scope>/` via the shared task
   `ansible/tasks/apply_gitops_app.yml`, rather than configuring anything
   inline - ArgoCD reconciles the referenced Helm chart or local manifest.
   `make day2 check agents` runs the acceptance/security gate instead of a
   lightweight state check - see `ansible/playbooks/day2_check.yml`'s
   header comment. `make day2 build [mcp|rag|rag-ingestion|agent|mlops]`
   builds the platform's own component images via OpenShift
   `BuildConfig`/`ImageStream` in `zuno-ai-build`.
4. `make day3 test` / `stresstest` (or the `d3` alias) - agent
   availability and stresstest operations (ADR-0057/ADR-0058), not an
   install tier: neither verb changes cluster state.

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
names (`day0`/`day1`/`day2 check`/`install`/`uninstall` map onto them).
`precheck.yml`
never fails - it detects state (a GitOps Application's Synced+Healthy status
where one exists, otherwise the concrete objects the role's own
`install.yml` creates) and sets a `<role>_state_installed` fact plus a
line in a shared `/tmp/zuno-statereport-*` file, displayed at the end of
the check run (see `ansible/tasks/{init_state_report,
check_gitops_app_state,record_state}.yml`). `uninstall.yml` reverses
`install.yml` - mostly by deleting the component's ArgoCD `Application`;
shared platform Namespaces are left in place and are the `namespaces`
role's own responsibility.
