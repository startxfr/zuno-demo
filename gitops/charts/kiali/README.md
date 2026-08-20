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
`zuno-agent-gateway`). `deployment.discovery_selectors` had to be set
explicitly to make `openshift-ingress` visible to Kiali: unlike
`accessible_namespaces` (an RBAC-adjacent wildcard, already `['**']`),
`discovery_selectors` is a separate namespace-visibility gate that - when
left unset, as it was by default - silently falls back to hiding every
`openshift-*`/`kube-*` namespace, the modern (undocumented-as-such,
no-longer-configurable-via-`api.namespaces.exclude`) equivalent of that
deprecated field's old default regex. Without it, Kiali could never resolve
HTTPRoutes' cross-namespace `parentRef` into `openshift-ingress`'s Gateways
and flagged them red (`KIA1401`, "Route is pointing to a non-existent or
inaccessible K8s gateway") even though their real Gateway API status was
healthy throughout. Because `discoverySelectors` semantics (Kiali mirrors
Istio's `meshConfig.discoverySelectors` here) *replace* rather than augment
the implicit default once set, every previously-visible namespace has to be
matched by one of the selector's rules too, not just `openshift-ingress` -
see the inline comment in `templates/kiali.yaml` for exactly how each of the
22 pre-existing namespaces is covered.
`kiali_feature_flags.validations.ignore` additionally suppresses the
`KIA1401`/`KIA1301` check messages mesh-wide; kept mostly for tidiness now
that `discovery_selectors` fixes the underlying resolution (ignoring a check
code alone only hides its message, not the red/invalid status itself, which
Kiali computes from a separate, unfiltered reference-resolution step).
