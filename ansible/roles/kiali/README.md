# kiali

Installs the Red Hat Kiali Operator and a `Kiali` CR (`kiali`, `zuno-mesh`
namespace) via `gitops/apps/kiali/application-d0.yaml` (operator) and
`application-d1.yaml` (instance) - see `gitops/apps/README.md` and
`gitops/charts/kiali/README.md`.

The web UI for the service mesh - istiod status/config, mesh topology and
traffic graph (from `mesh_monitoring`'s Prometheus), and distributed traces
(from `tempo`'s Tempo). The operator auto-creates and owns its own Route
(passthrough TLS, since Kiali serves HTTPS natively). `auth.strategy:
openshift` gates login behind the cluster's own OAuth; `spec.server.web_fqdn`
is pinned explicitly since passthrough TLS gives Kiali no `X-Forwarded-*`
headers to guess its external URL from otherwise. Depends on `service_mesh`,
`mesh_monitoring` and `tempo`.
