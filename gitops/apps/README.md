# GitOps applications

One subdirectory per platform component, each holding a single ArgoCD
`Application` manifest at `<component>/application.yaml`. The matching
Ansible role applies its own manifest directly during
`make day0|d0 configure <component>` / `make day1|d1 configure|run
<component>` (ADR-0056; see `ansible/tasks/apply_gitops_app.yml`) - this is
the only mechanism `make day0|d0`/`day1|d1` uses to reconcile these
Applications, so a single component can always be configured without a full
sync.

Every `Application.spec.project` here is `zuno`, not ArgoCD's built-in
`default` project - a dedicated `AppProject` (`ansible/roles/admin_context/
kustomize/appproject/appproject.yaml`) applied by the `admin_context` role's
`configure.yml` during `make day0|d0 configure` (after the `argocd` role's
`install.yml` has installed the operator that owns the `AppProject` CRD).
Keeping every zuno-* Application on a named, scoped project - rather than
whatever else on the cluster shares `default` - makes its RBAC/permissions
an explicit, auditable grant instead of an implicit one.

The root App-of-Apps (`gitops/root-app-of-apps.yaml`), which recurses over
this directory and manages every `application.yaml` it finds as a child
Application, is no longer applied by Ansible (ADR-0311, superseding the
"Bootstrap architecture" addendum in
docs/adr/0022-use-gitops-managed-declarative-agent-tasks-and-policies.md).
It is kept in the repository only as a documented example of a
pure-GitOps, Ansible-free bootstrap - see `docs/platform/installation.md`.

Each `Application.spec.source` points either at an upstream Helm chart
(`repoURL` + `chart` + `targetRevision`) for well-known third-party software
(Keycloak Operator, Crunchy Postgres Operator, vLLM/KServe runtimes, External Secrets
Operator config), or at `gitops/charts/<component>` in this repository for
Zuno-authored manifests (Tekos FE/BFF, Agent Runtime, MCP Gateway, MCP tool
servers, namespace/quota scaffolding).

Not every component has an Application here. `argocd` is the one remaining
exception - it installs ArgoCD itself, and `admin_context` creates the
`AppProject` (`zuno`) every `Application.spec.project` here references;
both are a bootstrap chicken-and-egg no `Application` can resolve, so they
still apply raw manifests directly via `ansible/tasks/apply_kustomize.yml`
(ADR-0310). `sql_schema` and `rag`'s one-shot SQL `Job`s, `vault`'s
imperative unseal, `smtp`'s static `ExternalSecret`, and the `*_build`
roles' `BuildConfig`s are likewise one-shot/imperative actions rather than
standing installed components, and stay outside this directory for the
same reason. `mlops` is out of scope for v0 (ADR-0301/0302 are v3).

`nfd`, `nvidia_gpu`, `openshift_ai` and `external_secrets` used to be in
this same exception bucket - an OLM `Subscription` + operator-managed CR
was judged to have no meaningful "chart" to template. ADR-0312 reversed
that: each now has its own `Application`/chart, with the `Subscription`
itself inside the chart (sync-wave `"10"`, gated ahead of the operand CR's
sync-wave `"20"` by a custom ArgoCD health check for
`operators.coreos.com/Subscription` -
`ansible/roles/argocd/tasks/apply_resource_health_checks.yml`). `zuno-ai-run`'s
`Namespace`, its RHOAI dashboard label and its GPU `ResourceQuota` (formerly
duplicated across `openshift_ai`'s and `external_secrets`' own kustomize)
are owned by `gitops/charts/namespaces` instead, closing that
double-ownership.

Directories present:

| Component | Source |
|---|---|
| `vault` | local chart, `gitops/charts/vault` (wraps Helm chart `hashicorp/vault` as a dependency) |
| `keycloak` | local chart, `gitops/charts/keycloak` |
| `postgresql` | local chart, `gitops/charts/postgresql` |
| `models` | local chart, `gitops/charts/models` (KServe ServingRuntime + InferenceService) |
| `mcp` | local chart, `gitops/charts/mcp-gateway` |
| `rag` | local chart, `gitops/charts/rag-service` |
| `ai-gateway` | local chart, `gitops/charts/ai-gateway` (applied by the `llm` role, see its README; ADR-0009) |
| `agent-runtime` | local chart, `gitops/charts/agent-runtime` (applied by the `llm` role, see its README) |
| `agents` | local chart, `gitops/charts/namespaces` |
| `api` | local chart, `gitops/charts/tekos` |
| `llm` | native Kustomize app, `platform/ai-gateway/` (provider routing ConfigMap + provider `ExternalSecret`s) |
| `mcp-sales-db` | local chart, `gitops/charts/mcp-sales-db` (applied by the `sql_schema` role, after its schema/fixtures Job) |
| `nfd` | local chart, `gitops/charts/nfd` (ADR-0312) |
| `nvidia-gpu` | local chart, `gitops/charts/nvidia-gpu` (ADR-0312; `ClusterPolicy` spec injected in a second apply once discovered - see that chart's README) |
| `openshift-ai` | local chart, `gitops/charts/openshift-ai` (ADR-0312) |
| `external-secrets` | local chart, `gitops/charts/external-secrets` (ADR-0312; `ClusterSecretStore`/cluster-domain `ExternalSecret` rendered only once `configure.yml` supplies the discovered Vault Service name - see the `external_secrets` role's README) |

`keycloak`, `api` and `vault`'s `Application.spec.source.helm.values`
reference `clusterBaseDomain: apps.mycluster.example.com` - a token, not a
literal domain. `ansible/tasks/apply_gitops_app.yml` substitutes it with
the real cluster's apps wildcard domain, auto-discovered from
`Ingress.config.openshift.io/cluster` and persisted to Vault at
`secret/zuno/platform/cluster-domain` (see
`ansible/tasks/resolve_cluster_base_domain.yml` and
`ansible/roles/vault/tasks/configure.yml`) - no manual edit needed before a
real deployment. `ansible/roles/external_secrets` also exposes that Vault
value as a `zuno-cluster-domain` Secret in `zuno-ai-run` for any service
that wants it as a live runtime value rather than a Helm-render-time one
(not yet consumed by any service - the value only reaches K8s manifest
spec fields like a Route's `spec.host` or the Keycloak CR's
`spec.hostname.hostname` through the Ansible/Helm path, since those fields
have no `secretKeyRef`-style mechanism to source from a Secret).
