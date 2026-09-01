# grafana

Referenced by `gitops/apps/grafana/application-d0.yaml` (operator.enabled:
`Namespace` + `OperatorGroup` + `Subscription` for the Grafana Labs
Community operator) and `application-d1.yaml` (grafana.enabled: the
`Grafana` CR, its oauth-proxy Route/ServiceAccount, the Prometheus/Tempo
`GrafanaDatasource`s and eight `GrafanaDashboard`s, all in
`zuno-monitoring`) - same operator/operand `-d0`/`-d1` split as
`observability`/`tempo`/`mesh-monitoring`/`kiali` (ADR-0312).

## Dashboards (ADR-0413, folder "Zuno Platform")

Eight dashboards, each with template-variable filters wired into its
queries and a `dashlist`/dashboard-links panel back to the others.
Consolidated 2026-08-19 from an earlier set of five (model-consumption,
user-consumption, infra, network-mesh, api-gateway - all retired, their
panels redistributed below) that had no template variables and never used
the Tempo datasource. `dashboard-infra-data.yaml` was itself split
2026-09-01 into `dashboard-infra-data.yaml` (infra only), `dashboard-
data.yaml` (the database exporter panels) and `dashboard-gitops.yaml`
(the ArgoCD panels, plus two new panels scoped to the openshift-gitops
namespace):

| File | uid | Filters | Covers |
|---|---|---|---|
| `dashboard-overview.yaml` | `zuno-overview` | none (landing page) | ADR-0102 SLO/error budget, component health, headline KPIs, links to the others |
| `dashboard-ai-models.yaml` | `zuno-ai-models` | provider, model, outcome, served_model | ADR-0029 gateway model traffic, semantic cache, vLLM serving internals, GPU/DCGM |
| `dashboard-usage-cost.yaml` | `zuno-usage-cost` | user, group, agent, model, provider | ADR-0029 usage/cost by user and Keycloak group |
| `dashboard-agents-tools-rag.yaml` | `zuno-agents-tools-rag` | agent, tool, mcp_server, domain | Per-agent SLO, MCP tool authorization outcomes, RAG search/freshness |
| `dashboard-infra-data.yaml` | `zuno-infra-data` | namespace, node, pod | Node/pod/deployment health, resource consumption |
| `dashboard-data.yaml` | `zuno-data` | none (one exporter per service) | PostgreSQL/MariaDB/Redis exporter health, throughput, cache efficiency |
| `dashboard-gitops.yaml` | `zuno-gitops` | none (openshift-gitops only) | ArgoCD sync/health status, apps out of sync, control-plane deployment availability and CPU usage |
| `dashboard-mesh-gateway.yaml` | `zuno-mesh-gateway` | dest_service, source_workload, mesh_namespace | Istio/Envoy mesh traffic, Kuadrant Authorino/Limitador |

Several panels (AI models, Agents/tools/RAG, Mesh & gateway) query the
`tempo` datasource directly via TraceQL, or carry a `fieldConfig` data link
into Tempo Explore from a related metric panel - the first use of that
datasource on this dashboard set.

No redhat-operators/certified-operators Grafana package exists on this
cluster - `grafana-operator` (Grafana Labs, channel `v5`) is Community
Operators only, a deliberate documented exception to this repo's usual
certified-operator preference (see `values.yaml`).

Unlike Kiali's `auth.strategy: anonymous` demo shortcut, Grafana sits
behind an `oauth-proxy` sidecar authenticating against OpenShift's own
OAuth server - already Keycloak-federated (ADR-0320), so this reuses the
same SSO as the OpenShift Console itself without a new Keycloak client.
Access is gated by SAR against the RBAC `gitops/charts/openshift-rbac-groups`
already grants `zuno-admin`/`aiops`/`admin` on `zuno-monitoring`.

The Prometheus datasource points at `thanos-querier`
(`openshift-monitoring`), authenticated with a Bearer token from a
`ServiceAccount` bound to the built-in `cluster-monitoring-view`
`ClusterRole` - the same Prometheus (`prometheus-k8s`) that
`gitops/charts/observability`'s `ServiceMonitor` confirmed-live scrapes
ADR-0029's `zuno.model_calls`/`zuno.model_tokens`/`zuno.model_cost_usd`.
The Tempo datasource points at `gitops/charts/tempo`'s Tempo, same
in-cluster URL Kiali already uses.
