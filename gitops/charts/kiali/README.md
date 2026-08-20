# kiali

Referenced by `gitops/apps/kiali/application-d0.yaml` (operator.enabled:
`Namespace` + `OperatorGroup` + `Subscription` for the Red Hat Kiali
operator) and `application-d1.yaml` (kiali.enabled: the `Kiali` CR and the
`OSSMConsole` CR, both in `zuno-mesh`) - same operator/operand `-d0`/`-d1`
split as `observability`/`tempo`/`mesh-monitoring` (ADR-0312).

The `OSSMConsole` CR registers the Kiali OpenShift console plugin (mesh view
in the web console). It shares the `kiali.enabled` flag with the `Kiali` CR
since it has nothing to point at without a running Kiali instance.

The Kiali operator auto-creates and owns its own Route from the `Kiali` CR
(`deployment.ingress`) - this chart does **not** template a separate `Route`
resource, since that would fight the operator for ownership of the same
object. TLS termination is overridden to `passthrough` via
`deployment.ingress.override_yaml` because Kiali serves its UI over HTTPS by
default (the operator's own default Route is edge-terminated, which would
send unencrypted HTTP to a TLS-only port).

Metrics come from `gitops/charts/mesh-monitoring`'s Prometheus, traces from
`gitops/charts/tempo`'s Tempo. `auth.strategy: openshift` gates login behind
the cluster's own OAuth (htpasswd + Keycloak IdPs); Kiali authorizes each
namespace via a `SelfSubjectAccessReview` against the logged-in user's real
RBAC, so there's no Kiali-specific RBAC to maintain. `spec.server.web_fqdn`/
`web_schema`/`web_port` are pinned explicitly because the Route's TLS
`passthrough` termination means the router never sees plaintext HTTP and so
never injects the `X-Forwarded-*` headers Kiali would otherwise use to guess
its own external URL - without the pin, Kiali fell back to its internal
listen port (20001) when building the browser-side OAuth redirect, sending
the login button to an unroutable `host:20001`.

The cluster runs two fully independent Istio control planes: `zuno-mesh`'s
own (`external_services.istio.root_namespace`/`istiod_url` above), and a
second, separate one OpenShift provisions automatically for its built-in
Gateway API support (`openshift-gateway-istiod` in `openshift-ingress`,
backing the shared `maas-default-gateway`/`data-science-gateway`/
`zuno-agent-gateway`). Kiali only supports one control plane per cluster, so
it can read HTTPRoute/Gateway objects in `openshift-ingress` (RBAC and
`accessible_namespaces` are cluster-wide) but can't validate them against a
control plane it doesn't know about, and flags every route pointing there
with a false-positive `KIA1401` ("Route is pointing to a non-existent or
inaccessible K8s gateway") even though their real Gateway API status is
healthy. `kiali_feature_flags.validations.ignore` suppresses `KIA1401`
mesh-wide for this reason - it is not silencing a real bug.
