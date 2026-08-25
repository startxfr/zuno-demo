# Ansible role: aap_config

Registers this repository in the running AAP instance (ADR-0354 clause 4,
WP-073, Path A): the `zuno` organization, a Controller API token, then the
`zuno-demo` Project / `zuno` inventory / `zuno-cluster-reader` credential /
`zuno-day0-check` Job Template as AAP resource-operator CRs
(`tower.ansible.com/v1alpha1`), and the Keycloak SSO authenticator on the
Gateway (closing ADR-0354 clause 6). Runs in `day1_components` immediately
after `aap` - it configures a running instance, never installs one.

## What is a CR vs an API call

The `tower.ansible.com` CRDs are shipped by `gitops/charts/aap`'s own
operator Subscription (confirmed live, WP-072's CRD inventory - no second
Subscription; `application-d0.yaml` is a no-op). Everything that *has* a
CRD is rendered declaratively by `gitops/charts/aap-config`; the rest is
driven through the Gateway/Controller API by `tasks/install.yml`, all
idempotent GET-then-POST (same `ansible.builtin.uri` Basic-auth pattern
`ansible/roles/aap`'s subscription step proved live):

| Object | Mechanism | Why |
|---|---|---|
| Project, Inventory, Credential, Job Template | CRs (chart) | CRDs exist |
| Organization `zuno` | API | no CRD; `AnsibleProject.spec.organization` is required and only "Default" exists on a fresh install |
| Controller API token | API + Vault | tokens are shown once; Vault `zuno/aap/controller-token` is the durable source, the chart's ExternalSecret re-materializes it as the `connection_secret` (keys `token`+`host`) every CR references |
| Inventory host `localhost` | API | the `AnsibleInventory` CRD has no host field |
| Credential→JT attachment | API | the `JobTemplate` CRD has no credentials field |
| Keycloak SSO authenticator + maps | API | authenticators are gateway API objects, no CRD |

## Least-privilege machine credential

`zuno-day0-check` authenticates to the cluster as the `aap-day0-check`
ServiceAccount (zuno-aap) bound to `cluster-reader`, its long-lived token
Secret consumed through `AnsibleCredential`'s native
`kubernetes_api`/`kubernetes_bearer_token_secret` fields - never the
bootstrap cluster-admin kubeconfig (ADR-0354 Security considerations,
narrowed per WP-073). `day0_check.yml` is read-mostly by construction; if
a precheck ever fails on permissions, widen with a targeted extra Role in
`gitops/charts/aap-config/templates/serviceaccount.yaml`, never a broader
built-in. `ansible/tasks/load_k8s_auth_env.yml` detects the credential's
injected `K8S_AUTH_HOST` and skips its kubeconfig resolution, so the same
playbooks run unmodified from an operator shell and from AAP.

## Keycloak SSO

The 2.7 gateway ships a native `keycloak` authenticator plugin (confirmed
live via `/api/gateway/v1/authenticator_plugins/`). `tasks/install.yml`
creates an authenticator "Keycloak zuno" against the `aap` realm client
WP-072 registered (secret read from zuno-auth's `aap-client-secret`, the
realm's RSA public key fetched live from the realm's public endpoint, both
OAuth URLs set explicitly - the plugin's defaults carry the legacy
`/auth/` prefix RHBK dropped, `GROUPS_CLAIM=groups`), plus two maps:
`ocp-paas-ops` → superuser (revoking - membership tracked both ways) and
allow-all-authenticated (viewer-level until Controller RBAC grants more -
launch-RBAC hardening is ADR-0418's scope). The local admin login stays as
fallback. If `aap-client-secret` isn't materialized yet, the SSO wiring is
skipped with a message and picked up on the next install run.

An existing authenticator is never PATCHed - config drift (e.g. a rotated
client secret) is fixed by deleting the authenticator in the Gateway UI
and re-running `make d1 install aap-config`.

## Known limitation: `aap-day0-check` cannot confirm vault's seal state

Confirmed live 2026-08-25, first real `zuno-day0-check` run: `vault`'s
`precheck.yml` calls `vault status` via `pods/exec` to determine whether
the server is unsealed - `cluster-reader` does not grant `pods/exec`
(unlike `secrets`, it's not merely excluded, it's entirely absent from
the built-in role), so that step never runs and `vault` always reports
"NOT installed" through this credential, even when it's healthy. **This
was left unfixed on purpose**: unlike the Secrets read
(`rolebinding-vault-secrets.yaml`, existence/metadata only), `pods/exec`
is execute-any-command-in-that-pod, not a bounded read - RBAC has no
finer-grained way to scope it to just the `vault status` invocation. The
operator decided this one false negative is an acceptable trade against
widening the credential's capability class. `make d0 check vault` from
an operator shell (cluster-admin) remains the source of truth for vault's
real state; `zuno-day0-check`'s report should be read with that one
known gap in mind.

## What's unverified against a live cluster

Everything above the API layer was confirmed live on 2026-08-25 (CRD
schemas via `oc explain`/openAPIV3Schema, plugin configuration_schema,
org/inventory/authenticator state, Controller service). Still unverified
until the first real `make d1 install aap-config`:

- The `connection_secret`'s expected key pair (`token`+`host`) and the
  credential `type` name string ("OpenShift or Kubernetes API Bearer
  Token") - read the resource-operator logs if a CR sits unreconciled.
- The authenticator_map trigger shapes (`{"always": {}}`,
  `{"groups": {"has_or": [...]}}`) against the 2.7 gateway.
- Whether the default execution environment carries `kubernetes.core` -
  the first Job Template launch is a deliberate diagnostic; a custom EE
  is out of scope for WP-073 (stop and report if needed).
