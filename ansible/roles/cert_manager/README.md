# cert_manager

A Day 0 component (`make d0 install cert-manager`). Applies
`gitops/apps/cert-manager/application-d0.yaml` (the Red Hat build of
cert-manager, "openshift-cert-manager-operator") then
`application-d1.yaml` (a `ClusterIssuer` backed by Vault's `pki/` secrets
engine) - `gitops/charts/cert-manager` - see `gitops/apps/README.md` and
`gitops/charts/cert-manager/README.md`.

Positioned right after `vault` in `day0_components` (`ansible/playbooks/
day0_{install,check}.yml`, reversed in `day0_uninstall.yml`): the `pki/`
secrets engine and the `cert-manager-issuer` Kubernetes-auth role/policy
this role's `ClusterIssuer` depends on are prepared by `vault`'s own
bootstrap script (`ansible/roles/vault/kustomize/unseal-configure/
configmap.yaml`), the same way `external_secrets`' `ClusterSecretStore`
depends on `vault`'s pre-existing `eso-reader` role/policy. This role
never writes to Vault directly with the root token - it only discovers
the Vault client Service (same `app.kubernetes.io/name=vault`
label-selector lookup `vault`/`external_secrets` already use) and applies
a declarative `ClusterIssuer` pointing at the already-configured backend.

**Infrastructure only for now.** No existing Route or service (`vault`,
`tekos`, `keycloak`) is modified to consume `vault-issuer` - all three
still rely on OpenShift's default ingress wildcard certificate for their
edge-terminated Routes. Wiring a specific Route/service to actually
request a `Certificate` from this issuer (which for an OpenShift `Route`
requires switching from `edge` to `reencrypt` termination, since a Route's
`spec.tls` has no `secretName`-style reference the way an `Ingress` does)
is a documented, opt-in follow-up, not part of this component.

See `gitops/charts/cert-manager/README.md` for why the operator's exact
package/channel/catalog and its singleton `CertManager` config CR shape
are flagged as an unverified assumption rather than a discovered/confirmed
value.
