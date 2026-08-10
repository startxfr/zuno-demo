# service-mesh

Referenced by `gitops/apps/service-mesh/application-d0.yaml`
(subscription.enabled: the `servicemeshoperator3` `Subscription` in
`openshift-operators`) and `application-d1.yaml` (clusterIssuer.enabled +
cert-manager-istio-csr.enabled + istiocni.enabled + istio.enabled: the
Vault-backed mesh CA, `IstioCNI`, and the `Istio` control plane itself in
`zuno-mesh`) - same `-d0`/`-d1` operator/operand split as `cert-manager`
(ADR-0312).

Deployed **after `postgresql`, before `keycloak`** in `day0_components`
(`ansible/playbooks/day0_install.yml`): `zuno-data`/`zuno-auth`/
`zuno-ai-run`/`zuno-ai-build` are pre-labeled `istio-injection: enabled` by
`gitops/charts/namespaces` from the very start of Day 0, but the injection
webhook doesn't exist until this component installs -  so postgresql's pods
(created before this component) need an explicit rollout-restart to pick up
their sidecar (done at the end of `ansible/roles/service_mesh/tasks/install.yml`),
while keycloak and every Day 1 AI/agent workload (deployed after this
component) auto-inject on first create with no restart needed.

`zuno-vault` is deliberately **not** meshed - it's the mTLS/PKI trust root
for cert-manager's `vault-issuer` and this chart's own `vault-issuer-istio`,
so adding it to the mesh risks a bootstrap circularity between Vault and the
CA that would sign its own sidecar's certificate.

## Why the CSV, istio-csr chart version, and CA-delegation mechanism are flagged as assumptions

Like `cert-manager` before it, `servicemeshoperator3` was never installed
anywhere in this repository before Subscription channel/CSV
(`stable` / `servicemeshoperator3.v3.4.1`) are taken as given rather than
discovered from the cluster's `PackageManifest`. `ansible/roles/service_mesh/tasks/precheck.yml`
validates the CSV is actually published before applying - if it isn't,
switch to the dynamic-discovery pattern `external_secrets`/`postgresql`
already use instead of hardcoding.

The `cert-manager-istio-csr` chart version pin (`0.14.0`,
`https://charts.jetstack.io`) and the `pilot.env.ENABLE_CA_SERVER` /
`global.caAddress` mechanism for delegating CA duties away from istiod's
built-in self-signed CA are asserted from general knowledge of upstream
Istio/cert-manager-istio-csr, not verified against this operator's exact
CSV. Confirm both against the operator's supported-versions
docs/ConfigMap and the chart's published `values.schema.json` before
relying on them in a real rollout.
