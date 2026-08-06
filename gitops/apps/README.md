# GitOps applications

One subdirectory per platform component, each holding a single ArgoCD
`Application` manifest at `<component>/application.yaml`. The root
App-of-Apps (`gitops/root-app-of-apps.yaml`) recurses over this directory and
manages every `application.yaml` it finds as a child Application; the
matching Ansible role also applies its own manifest directly during
`make day0|d0 configure <component>` / `make day1|d1 configure|run
<component>` (ADR-0056; see `ansible/tasks/apply_gitops_app.yml`) so a
single component can be configured without a full sync.

Each `Application.spec.source` points either at an upstream Helm chart
(`repoURL` + `chart` + `targetRevision`) for well-known third-party software
(Keycloak Operator, Crunchy Postgres Operator, vLLM/KServe runtimes, External Secrets
Operator config), or at `gitops/charts/<component>` in this repository for
Zuno-authored manifests (Tekos FE/BFF, Agent Runtime, MCP Gateway, MCP tool
servers, namespace/quota scaffolding).

Not every component has an Application here - operators with no standalone
workload of their own (`argocd`, `external_secrets`, `nvidia_gpu`,
`openshift_ai`) are installed by direct `kubernetes.core.k8s`
Subscription/CR tasks in their own Ansible role instead (mirroring
`ansible/roles/argocd`), since an OLM `Subscription` + operator-managed CR
has no meaningful "chart" to template - `openshift_ai` also creates the
`zuno-ai-run` project namespace and its GPU `ResourceQuota` this way (merged
in from the former `datascience` role, ADR-0056). `sql_schema` and `smtp`
apply a one-shot Job and an `ExternalSecret` directly for the same reason.
`mlops` is out of scope for v0 (ADR-0301/0302 are v3).

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
