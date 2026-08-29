# openshift_oauth

Applies the `gitops/apps/openshift-oauth` ArgoCD Application pair, whose
chart (`gitops/charts/openshift-oauth`) renders the cluster `OAuth`/`cluster`
singleton (`config.openshift.io/v1`), a `Proxy`/`cluster` trust patch, plus
the `ExternalSecret` that syncs its Vault-seeded OIDC client secret into
`openshift-config`. A Day 1 component (its dependency, `keycloak`, moved
to Day 0 by ADR-0421, so this role now runs after all of Day 0 rather
than immediately after a Day-1 `keycloak`): the "openshift" client and its
secret, plus its cert-manager-issued TLS cert, must exist first. `-d0`
applies the `ExternalSecret`; the role then
copies two CA ConfigMaps into `openshift-config` (see below); `-d1`
applies the `OAuth` singleton and the `Proxy` trust patch, which
reference the Secret `-d0` creates and those CA ConfigMaps respectively.

## Why this chart owns the whole `OAuth` spec

This is the only `OAuth` manifest in `gitops/`/`ansible/`, but the demo
cluster also runs the external startx `cluster-auth` chart, which
manages the same singleton - this chart is the single intended owner: it
absorbs the startx settings (htpasswd IDP, login templates,
`tokenConfig`) and owns the full spec wholesale, so the startx ArgoCD
app must stop managing `OAuth`/`cluster` or the two apps self-heal-fight
over it. See `gitops/charts/openshift-oauth/templates/oauth.yaml`'s
inline comment.

`mappingMethod: add` (not the OpenShift default `claim`) is required so a
user's first Keycloak login attaches to an already-existing OpenShift
`User` object instead of creating a duplicate.

## The Keycloak serving-CA copy

The OpenID IDP's issuer `https://keycloak.<domain>/realms/zuno` is served
by the `zuno` Ingress in `zuno-auth`, whose TLS cert (`keycloak-tls`) is
signed by Vault's `pki/` mount (root `CN=zuno-demo.internal`) - **not**
the cluster's default ingress router certificate. `openID.ca` must point
at `keycloak-tls`'s `ca.crt`: the router CA fails to verify the live
chain. `tasks/install.yml` writes two ConfigMaps into `openshift-config`
from cluster-specific data (Helm can't render them):

- **`keycloak-serving-ca`** (key `ca.crt`): `keycloak-tls`'s `ca.crt`
  (`zuno-auth` - the actual trust anchor) bundled with the router CA
  (covers the `ingress.operatorManaged` fallback in
  `gitops/charts/keycloak`). Wired into `openID.ca` on the OpenID IDP only.
- **`user-ca-bundle`** (key `ca-bundle.crt` - the key name OpenShift's
  `proxy.spec.trustedCA` convention requires): just the Vault PKI root,
  referenced by `Proxy/cluster.spec.trustedCA`
  (`templates/cluster-trusted-ca.yaml`, a **partial patch** touching only
  `spec.trustedCA` - `Proxy`/`cluster` carries other operator-managed
  fields this chart must never touch).

Both copies run unconditionally on every install, so a rotated Keycloak
cert or regenerated Vault root is healed by re-running `make day1 install
openshift-oauth` (no `day1_reconcile.yml` exists in this repo -
`install.yml` is idempotent); `uninstall.yml` deletes both and
`precheck.yml` requires both for the component to count as installed.

## Referenced startx Secrets (never created here)

The chart's `oauth.htpasswd` and `oauth.templates` gates (both off by
default, enabled only in
`gitops/apps/openshift-oauth/application-d1.yaml`) reference Secrets
owned by the external startx `cluster-auth` chart in `openshift-config`:
`startx-htpasswd-htpasswd-auth` and
`startx-{login,errors,providers}-template`. They are prerequisites, not
resources of this repo - if missing, the htpasswd IDP/templates are
silently not honored (per `oc explain oauth.spec`), so verify they exist
before enabling the gates on a new cluster.

## Two ExternalSecrets, one Vault path

`gitops/charts/keycloak`'s `templates/externalsecret-openshift-client.yaml`
and this chart's `templates/externalsecret.yaml` both read Vault key
`zuno/keycloak/openshift-client` (seeded once by
`ansible/roles/vault/tasks/install.yml`) into two different namespaces:
`zuno-auth` (Keycloak's `KC_VAULT` file-SPI injects
`${vault.openshift_client_secret}` into the realm's `openshift` client)
and `openshift-config` (the cluster `OAuth` resource's
`identityProviders[].openID.clientSecret`). `ExternalSecret` can't cross
namespaces, so each consuming namespace gets its own copy - same pattern
used for the Postgres secret crossing `zuno-data` -> `zuno-auth` (see
`ansible/roles/keycloak/README.md`).

## Not yet verified against a live cluster

The realm-zuno.json `openshift` client's `rootUrl`/`redirectUris` use the
same static `mycluster.example.com` placeholder domain every other
frontend client in that file uses - this chart's own `issuer` field is
templated against the real, discovered `clusterBaseDomain`, but the
client's own redirect URI inside Keycloak is not. On a real cluster,
either accept the demo placeholder (if DNS is arranged to alias it) or
hand-adjust `gitops/charts/keycloak/files/realm-zuno.json`'s `openshift`
client entry to the real OAuth callback host
(`oauth-openshift.apps.<real-domain>`) - the same operator action every
other frontend client in that file already requires.
