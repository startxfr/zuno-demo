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
configure script (`ansible/roles/vault/kustomize/configure/
configure.sh`). Since ADR-0602/WP-223 the issuer reaches Vault over https
with the service-ca bundle (`vaultCaBundle`, from
`ansible/tasks/resolve_vault_ca_bundle.yml`); re-run this role after a
service CA rotation. This role never writes to Vault directly - it only
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

## External mode (ADR-0352, WP-217)

`zuno_cert_manager_mode: external` in `ansible/confidential.yml` (absent = `internal`) declares that cert-manager is
installed and lifecycle-managed outside this installer. It is a Tier A-operator component: the mode key is the whole
contract, there is no endpoint and no `_external_*` payload.

| Verb | internal (default) | external |
|---|---|---|
| `install` | applies `zuno-cert-manager-d0` (OLM Subscription, CertManager CR), then `-d1` | skips `-d0`; asserts the CRDs (`certificates`, `certificaterequests`, `issuers`, `clusterissuers`), a `Succeeded` CSV `cert-manager-operator*` and the Ready controller `cert-manager/cert-manager`, failing fast otherwise; then applies `-d1` |
| `check` | `-d0` and `-d1` Applications plus ClusterIssuer `vault-issuer` Ready | the assertion above replaces the `-d0` Application check (record-only); `-d1` and `vault-issuer` as in internal |
| `uninstall` | removes `-d1`, the operator, then `-d0` | removes `-d1` only; the operator, its CSV and Subscription are never touched |

The `-d1` side, the Vault-backed ClusterIssuers, the ACME (ADR-0211) configuration and the Certificates, is ours in
both modes and always applied through ArgoCD. The seams the external operator must honour are unchanged: the Vault root
CA reaches the issuers through `resolve_vault_ca_bundle.yml`, and the ACME DNS identity through `confidential.yml`.

**Installing the operator outside this installer.** Subscribe the Red Hat `openshift-cert-manager-operator` (namespace
`cert-manager-operator`) and let it deploy cert-manager into `cert-manager`; wait for the CSV `Succeeded` and
`cert-manager/cert-manager` Ready. If your ACME track needs Route 53 recursive nameservers or other controller flags,
set them on your own `CertManager` CR: in external mode this installer does not apply one. Then set the mode and run
`make d0 install cert-manager`.

**Flipping the mode** is a migration event, not a reconcile (clause 4). Internal to external: delete the
`zuno-cert-manager-d0` Application without cascade (the Subscription, CSV and CertManager CR stay), then set `external`.
External to internal: set `internal` and run `make d0 install cert-manager`.
