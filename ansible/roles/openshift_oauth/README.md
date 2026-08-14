# openshift_oauth

Applies the `gitops/apps/openshift-oauth` ArgoCD Application pair
(ADR-0320, ADR-0346, ADR-0347), whose chart (`gitops/charts/openshift-oauth`)
renders the cluster `OAuth`/`cluster` singleton (`config.openshift.io/v1`),
a `Proxy`/`cluster` trust patch, plus the `ExternalSecret` that syncs its
Vault-seeded OIDC client secret into `openshift-config`. A Day 0 component
(ADR-0056), ordered after `keycloak` (the "openshift" client and its
secret, plus its cert-manager-issued TLS cert, must exist first): `-d0`
applies the `ExternalSecret`; the role then copies two CA ConfigMaps into
`openshift-config` (see below); `-d1` applies the `OAuth` singleton and
the `Proxy` trust patch, which reference the Secret `-d0` creates and
those CA ConfigMaps respectively.

## Why this chart owns the whole `OAuth` spec

Nothing before ADR-0320 configured cluster/Console authentication -
Keycloak (ADR-0012) authenticates the five agent frontends only, through
their own OIDC clients, never the OpenShift API/Console itself. This is
still the only `OAuth` manifest in `gitops/`/`ansible/`, but the demo
cluster *also* runs the external startx `cluster-auth` chart, which
manages the same singleton. ADR-0346 makes this chart the single intended
owner: it absorbs the startx settings (htpasswd IDP, login templates,
`tokenConfig`) and owns the full spec wholesale - the startx ArgoCD app
must stop managing `OAuth`/`cluster`, or the two apps self-heal-fight
over it. See `gitops/charts/openshift-oauth/templates/oauth.yaml`'s
inline comment.

`mappingMethod: add` (not the OpenShift default `claim`) is required so a
user's first Keycloak login attaches to an already-existing OpenShift
`User` object instead of creating a duplicate.

## The Keycloak serving-CA copy (ADR-0346, corrected by ADR-0347)

The OpenID IDP's issuer `https://keycloak.<domain>/realms/zuno` is served
by the `zuno` Ingress in `zuno-auth` (ADR-0316: cert-manager, cluster-issuer
`vault-issuer`, TLS Secret `keycloak-tls`), whose certificate is signed by
Vault's `pki/` mount, root `CN=zuno-demo.internal` - **not** the cluster's
default ingress router certificate. ADR-0346 originally assumed the latter
and wired `openID.ca` to a copy of the router CA; the authentication
operator stayed degraded with `OAuthServerConfigObservationDegraded: ...
x509: certificate signed by unknown authority` even after that landed.
ADR-0347 corrected the source (verified live with `openssl s_client`: the
router CA fails to verify the live chain, `keycloak-tls`'s `ca.crt`
succeeds) and added a cluster-wide complement:

- **`keycloak-serving-ca`** (`openshift-config`, key `ca.crt`): bundles
  `keycloak-tls`'s `ca.crt` (`zuno-auth` - the actual trust anchor) with the
  router CA (covers the `ingress.operatorManaged` fallback in
  `gitops/charts/keycloak`). Wired into `openID.ca` on the OpenID IDP only.
- **`user-ca-bundle`** (`openshift-config`, key `ca-bundle.crt` - the key
  name OpenShift's `proxy.spec.trustedCA` convention requires, different
  from `openID.ca`'s `ca.crt`): just the Vault PKI root, referenced by
  `Proxy/cluster.spec.trustedCA` (`templates/cluster-trusted-ca.yaml`).
  Defense in depth, not conceptually OAuth-specific - it's consumed by
  every operator whose `trusted-ca-bundle` ConfigMap carries the CNO
  injection label `config.openshift.io/inject-trusted-cabundle: "true"`
  (confirmed live: `openshift-authentication-operator`'s already does) -
  but OAuth's OpenID IDP is the only current consumer, so it lives here
  rather than in a dedicated component. Unlike the `OAuth`/`cluster`
  template, `templates/cluster-trusted-ca.yaml` is a **partial patch**
  (only `spec.trustedCA`), not wholesale ownership - `Proxy`/`cluster`
  carries other operator-managed fields this chart must never touch.

Both ConfigMaps hold cluster-specific data, so Helm can't render them:
`tasks/install.yml` looks up `keycloak-tls` and the router CA once and
writes both ConfigMaps from it (same look-up/blocked-finding(ADR-0344)/
copy pattern as `openshift_ai`'s `istio-ca-root-cert` copy), then removes
the superseded `default-ingress-cert` ConfigMap ADR-0346 left behind. Both
copies run unconditionally on every install/reconcile, so a rotated
Keycloak cert or regenerated Vault root is healed by `make d0 reconcile
openshift-oauth`; `uninstall.yml` deletes both and `precheck.yml` requires
both for the component to count as installed.

## Referenced startx Secrets (never created here)

The chart's `oauth.htpasswd` and `oauth.templates` gates (both off by
default, enabled only in `gitops/apps/openshift-oauth/
application-d1.yaml`) reference Secrets owned by the external startx
`cluster-auth` chart in `openshift-config`:
`startx-htpasswd-htpasswd-auth` and
`startx-{login,errors,providers}-template`. They are prerequisites, not
resources of this repo. If they are missing, the htpasswd IDP/templates
are silently not honored (per `oc explain oauth.spec`), so verify they
exist before enabling the gates on a new cluster.

## Two ExternalSecrets, one Vault path

`gitops/charts/keycloak`'s own `templates/externalsecret-openshift-
client.yaml` and this chart's `templates/externalsecret.yaml` both read
Vault key `zuno/keycloak/openshift-client` (seeded once by
`ansible/roles/vault/tasks/install.yml`), into two different namespaces
(`zuno-auth`, where Keycloak itself needs the secret via its `KC_VAULT`
file-SPI mechanism to inject `${vault.openshift_client_secret}` into the
realm's `openshift` client; `openshift-config`, where the cluster `OAuth`
resource's `identityProviders[].openID.clientSecret` needs it) -
`ExternalSecret` can't cross namespaces, so each consuming namespace gets
its own copy, same pattern already used for the Postgres secret crossing
`zuno-data` -> `zuno-auth` (see `ansible/roles/keycloak/README.md`).

## Not yet verified against a live cluster

The realm-zuno.json `openshift` client's `rootUrl`/`redirectUris` use the
same static `mycluster.example.com` placeholder domain every other
frontend client in that file already uses (no dynamic override exists for
any of them - confirmed by repo-wide search) - this chart's own
`issuer` field is properly templated against the real, discovered
`clusterBaseDomain` (same "apps.mycluster.example.com" literal-placeholder
text-substitution mechanism `ansible/tasks/apply_gitops_app.yml` already
uses for `gitops/apps/keycloak/application-d1.yaml`), but the client's own
redirect URI inside Keycloak is not. On a real cluster, either accept the demo
placeholder (if DNS is arranged to alias it) or hand-adjust
`gitops/charts/keycloak/files/realm-zuno.json`'s `openshift` client entry
to the real OAuth callback host (`oauth-openshift.apps.<real-domain>`) -
the same operator action every other frontend client in that file already
requires, not a new gap this ADR introduces.
