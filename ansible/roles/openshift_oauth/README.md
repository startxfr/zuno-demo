# openshift_oauth

Applies the `gitops/apps/openshift-oauth` ArgoCD Application pair
(ADR-0320, ADR-0346), whose chart (`gitops/charts/openshift-oauth`)
renders the cluster `OAuth`/`cluster` singleton (`config.openshift.io/v1`)
plus the `ExternalSecret` that syncs its Vault-seeded OIDC client secret
into `openshift-config`. A Day 0 component (ADR-0056), ordered after
`keycloak` (the "openshift" client and its secret must exist first): `-d0`
applies the `ExternalSecret`; the role then copies the ingress router CA
into `openshift-config` (see below); `-d1` applies the `OAuth` singleton
itself, which references both the Secret `-d0` creates and that CA
ConfigMap.

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

## The router-CA copy (ADR-0346)

The OpenID IDP's issuer `https://keycloak.<domain>/realms/zuno` is served
by the cluster's default ingress router certificate, which the
oauth-server pod does not trust - without a trust anchor the
authentication operator degrades with
`OAuthServerConfigObservationDegraded: ... x509: certificate signed by
unknown authority` (observed live, 2026-08-14). The fix is
`openID.ca`, which must reference a ConfigMap in `openshift-config` with
key `ca.crt`. That data is cluster-specific, so Helm can't render it:
`tasks/install.yml` copies it from
`openshift-config-managed/default-ingress-cert` (key `ca-bundle.crt`,
maintained by the ingress operator) into
`openshift-config/default-ingress-cert`, re-keyed to `ca.crt` - same
pattern as `openshift_ai`'s `istio-ca-root-cert` copy. The copy runs
unconditionally on every install/reconcile (idempotent `state: present`),
so a rotated router cert is healed by `make d0 reconcile
openshift-oauth`; `uninstall.yml` deletes it and `precheck.yml` requires
it for the component to count as installed.

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
