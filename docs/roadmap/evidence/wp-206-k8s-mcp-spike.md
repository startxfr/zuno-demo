# WP-206: Kubernetes MCP server spike on demo333 (2026-11-05)

Scratch namespace `zuno-k8smcp-scratch` (removed at the end, with the RoleBinding `k8smcp-view-spike` in
`zuno-ai-run` and the ClusterRoleBinding `k8smcp-spike-monview`). OpenShift 4.22.20, `restricted-v2`, no SCC granted.

## 1. Server

`containers/kubernetes-mcp-server` **v0.0.69** (2026-10-23, Apache-2.0), image
`ghcr.io/containers/kubernetes-mcp-server@sha256:1da9d62ad0c008a6cadcf2718c86c2e2d18753ca1d9f1f3313068980794b24f2`.
No `v0.0.68` image tag exists; v0.1.0 (`sha256:eb8eb884…`) is under two weeks old. Configuration is a **TOML file only**
(`--config`; CLI flags `--port`, `--read-only` no longer exist). UBI minimal image, runs as an arbitrary UID with
`allowPrivilegeEscalation: false`, drop ALL, `readOnlyRootFilesystem`, under `restricted-v2`. HTTP endpoints:
`/mcp`, `/healthz`, `/stats`, `/metrics`. The server has **no authentication and no gateway-token check**: the
NetworkPolicy is its only door (the ADR-0037 second layer is not available for an unmodified upstream).

## 2. What the configuration achieved

| Check | Result |
|---|---|
| `read_only = true`, `enabled_tools` allowlist | only the listed tools are exposed; `pods_exec` answers `unknown tool` |
| `denied_resources` Secret and ConfigMap | `resources_get` and `resources_list` answer `resource not allowed: /v1, Kind=Secret` even where RBAC would allow |
| RoleBinding `view` in `zuno-ai-run` only | pods, events, deployments, logs of `zuno-ai-run` readable; `zuno-vault` answers `Permission denied` |
| `pods_list` | cluster-wide call, **fails** with per-namespace RBAC; use `resources_list` (kind Pod) or `pods_list_in_namespace` |
| `namespaces_list` | cluster-scoped, not needed, left out |
| `cluster_auth_mode = "kubeconfig"` | the server's own ServiceAccount is the identity (no token forwarding) |

## 3. Metrics

The toolset is named **`observability/metrics`** (`metrics` is refused at start-up). Keys
(`pkg/toolsets/metrics/config.go` at v0.0.69), under `[toolset_configs."observability/metrics"]`: `prometheus_url`,
`auth_mode = "kubeconfig"` (server ServiceAccount token). The CA of the service CA is picked up automatically; there is no
CA key and `insecure` is rejected. Results:

- Thanos Querier **9092** (namespaced): the metric validation call answers `400` (no `namespace` parameter). Unusable.
- Thanos Querier **9091** with `cluster-monitoring-view` on the ServiceAccount: works. A query without label matcher is
  refused by the server's own guardrail (`query for metric "up" does not have any label matchers`); with
  `kube_pod_status_phase{namespace="zuno-ai-run",phase="Running"}` it returns the vector.
- **Consequence:** `metrics.query` needs a cluster-wide read of all metrics (the user accepted that on 2026-11-05).
  The gateway cannot narrow a PromQL query to the `zuno-*` namespaces.

## 4. Decisions for the chart (`gitops/charts/mcp-k8s`)

Five capabilities, one binding each (a binding maps one capability to one `provider_tool`): `k8s.resource.read` ->
`resources_get`, `k8s.resource.list` -> `resources_list`, `k8s.events.read` -> `events_list`, `k8s.logs.read` ->
`pods_log`, `metrics.query` -> `execute_instant_query`. ADR-0600 clause 1 named `k8s.resource.read` as "get and list";
the split is recorded in the ADR. Entitled groups: `ocp-ai-ops` and `aap_ops`. RBAC: `view` RoleBinding per `zuno-*`
namespace (list in the chart values), `cluster-monitoring-view` ClusterRoleBinding for metrics.

## 5. Not covered by the spike

The five-factor call through the mcp-gateway `/mcp` (operations persona listing pods, business persona refused,
Secret refused) is the live acceptance of the roll-out and is recorded in WP-206 once the chart is deployed.
