# grafana

Referenced by `gitops/apps/grafana/application-d0.yaml` (operator.enabled:
`Namespace` + `OperatorGroup` + `Subscription` for the Grafana Labs
Community operator) and `application-d1.yaml` (grafana.enabled: the
`Grafana` CR, its oauth-proxy Route/ServiceAccount, the Prometheus/Tempo
`GrafanaDatasource`s and the "Model consumption" `GrafanaDashboard`, all in
`zuno-monitoring`) - same operator/operand `-d0`/`-d1` split as
`observability`/`tempo`/`mesh-monitoring`/`kiali` (ADR-0312).

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
