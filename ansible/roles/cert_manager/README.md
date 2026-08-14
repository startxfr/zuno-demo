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
configmap.yaml`). This role never writes to Vault directly - it only
discovers the Vault client Service (same `app.kubernetes.io/name=vault`
label-selector lookup `vault`/`external_secrets` already use) and applies
a declarative `ClusterIssuer` pointing at the already-configured backend.

**First real consumer: `ansible/roles/keycloak`.** `vault` and `tekos`
still rely on OpenShift's default ingress wildcard certificate for their
edge-terminated Routes, unchanged. Keycloak's Route, by contrast, is no
longer left to the RHBK operator's own Route/Ingress management -
`gitops/charts/keycloak/templates/ingress.yaml` hand-authors a Kubernetes
`Ingress` (not a Route directly - a Route's `spec.tls` has no
`secretName`-style reference) annotated for `vault-issuer`;
cert-manager's ingress-shim issues the `Certificate` and OpenShift's own
Ingress-to-Route controller generates the actual Route from it, still
`edge`-terminated (Keycloak's backend stays plain HTTP; only the
certificate's origin changes). See `ansible/roles/keycloak/README.md`'s
"External TLS via cert-manager" section for the full mechanism and the
TLS-sync fallback.

`vault`/`tekos` remaining on the default wildcard cert is a documented,
opt-in follow-up. See `gitops/charts/cert-manager/README.md` for the
caveats on the operator's package/channel/catalog and its singleton
`CertManager` config CR shape.
