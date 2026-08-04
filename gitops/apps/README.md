# GitOps applications

One subdirectory per platform component, each holding a single ArgoCD
`Application` manifest at `<component>/application.yaml`. The root
App-of-Apps (`gitops/root-app-of-apps.yaml`) recurses over this directory and
manages every `application.yaml` it finds as a child Application; the
matching Ansible role also applies its own manifest directly during
`make configure <scope>` (see `ansible/tasks/apply_gitops_app.yml`) so a
single scope can be configured without a full sync.

Each `Application.spec.source` points either at an upstream Helm chart
(`repoURL` + `chart` + `targetRevision`) for well-known third-party software
(Keycloak Operator, CloudNativePG, vLLM/KServe runtimes, External Secrets
Operator config), or at `gitops/charts/<component>` in this repository for
Zuno-authored manifests (Tekos FE/BFF, Agent Runtime, MCP Gateway, MCP tool
servers, namespace/quota scaffolding).

Not every component has an Application here — operators with no standalone
workload of their own (`argocd`, `external_secrets`, `nvidia_gpu`,
`openshift_ai`, `datascience`) are installed by direct `kubernetes.core.k8s`
Subscription/CR tasks in their own Ansible role instead (mirroring
`ansible/roles/argocd`), since an OLM `Subscription` + operator-managed CR
has no meaningful "chart" to template. `sql_schema` and `smtp` apply a
one-shot Job and an `ExternalSecret` directly for the same reason. `mlops`
is out of scope for v0 (ADR-0301/0302 are v3).

Directories present:

| Component | Source |
|---|---|
| `vault` | Helm chart `hashicorp/vault` |
| `keycloak` | local chart, `gitops/charts/keycloak` |
| `postgresql` | local chart, `gitops/charts/postgresql` |
| `models` | local chart, `gitops/charts/models` (KServe ServingRuntime + InferenceService) |
| `mcp` | local chart, `gitops/charts/mcp-gateway` |
| `rag` | local chart, `gitops/charts/rag-service` |
| `agent-runtime` | local chart, `gitops/charts/agent-runtime` (applied by the `llm` role, see its README) |
| `agents` | local chart, `gitops/charts/namespaces` |
| `api` | local chart, `gitops/charts/tekos` |
| `llm` | native Kustomize app, `platform/ai-gateway/` (provider routing ConfigMap + provider `ExternalSecret`s) |
| `mcp-sales-db` | local chart, `gitops/charts/mcp-sales-db` (applied by the `sql_schema` role, after its schema/fixtures Job) |

**Known follow-up:** `keycloak` and `api`'s `Application.spec.source.helm.values`
embed `clusterBaseDomain: apps.example.com` directly in the manifest rather
than templating it from the cluster's real apps wildcard domain — edit both
files (and `cluster_base_domain` in `ansible/inventories/demo/group_vars/all/main.yml`,
used only by the `agents` role's smoke check) before a real deployment.
Auto-discovering this from `ingresses.config/cluster` and threading it
through consistently is future work, not done here.
