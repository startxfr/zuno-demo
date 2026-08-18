# grafana

Installs the Grafana Operator (Grafana Labs, Community Operators - no
redhat-operators package exists on this cluster) and a `Grafana` CR
(`grafana`, `zuno-monitoring` namespace) via
`gitops/apps/grafana/application-d0.yaml` (operator) and
`application-d1.yaml` (instance) - see `gitops/apps/README.md` and
`gitops/charts/grafana/README.md`.

The visualization layer for ADR-0029's model-usage metrics/traces: a
`Prometheus` datasource (`thanos-querier`, `cluster-monitoring-view`
Bearer token) for `zuno.model_calls`/`zuno.model_tokens`/
`zuno.model_cost_usd`/`zuno_bff_requests_total`, a `Tempo` datasource
(`tempo`'s Tempo) for distributed traces, and a pre-provisioned "Model
consumption" `GrafanaDashboard`. Unlike Kiali's `anonymous` demo shortcut,
Grafana sits behind an `oauth-proxy` sidecar authenticating against
OpenShift's own OAuth server (already Keycloak-federated per ADR-0320) -
no new Keycloak client needed, access gated by the existing
`zuno-admin`/`aiops`/`admin` RBAC on `zuno-monitoring`
(`gitops/charts/openshift-rbac-groups`, ADR-0320). Depends on
`observability` and `tempo`.
