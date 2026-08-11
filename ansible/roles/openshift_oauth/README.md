# openshift_oauth

Applies the `gitops/apps/openshift-oauth` ArgoCD Application pair
(ADR-0320), whose chart (`gitops/charts/openshift-oauth`) renders the
cluster `OAuth`/`cluster` singleton (`config.openshift.io/v1`) plus the
`ExternalSecret` that syncs its Vault-seeded OIDC client secret into
`openshift-config`. A Day 0 component (ADR-0056), ordered after
`keycloak` (the "openshift" client and its secret must exist first): `-d0`
applies the `ExternalSecret`; `-d1` applies the `OAuth` singleton itself,
which references the Secret `-d0` creates.

## Why this is the first `OAuth` resource in the repository

Nothing before ADR-0320 configured cluster/Console authentication -
Keycloak (ADR-0012) authenticates the five agent frontends only, through
their own OIDC clients, never the OpenShift API/Console itself. This role
adds the first `config.openshift.io/v1 OAuth` identity provider anywhere
in `gitops/`/`ansible/`, and since it's the first, it owns the full
`spec.identityProviders` list wholesale rather than merging into an
existing one - see `gitops/charts/openshift-oauth/templates/oauth.yaml`'s
inline comment.

`mappingMethod: add` (not the OpenShift default `claim`) is required so a
user's first Keycloak login attaches to an OpenShift `User` object the
`console_favorites_provisioning` CronJob (`ansible/roles/
console_favorites_provisioning`) may have already pre-created, instead of
creating a duplicate - see that role's README for why favorites can't be
seeded without pre-creating the `User`.

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
