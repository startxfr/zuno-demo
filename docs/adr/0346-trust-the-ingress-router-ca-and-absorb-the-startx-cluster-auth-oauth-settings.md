# ADR-0346: Trust the ingress router CA and absorb the startx cluster-auth OAuth settings

- **Status:** Implemented (CA source corrected by [ADR-0347](0347-trust-the-vault-pki-root-for-the-oauth-openid-idp.md) - the assumed trust anchor was wrong; the htpasswd/templates/tokenConfig absorption below is unaffected)
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Context

The demo cluster's `authentication` clusteroperator went Degraded live (2026-08-14):

> `OAuthServerConfigObservationDegraded: failed to apply IDP openshift config: tls: failed to verify certificate: x509: certificate signed by unknown authority`

The failing IDP is the OpenID one this repo renders (`gitops/charts/openshift-oauth/templates/oauth.yaml`, ADR-0320): its issuer `https://keycloak.<clusterBaseDomain>/realms/zuno` is served by the cluster's **default ingress router certificate**, which is not in the oauth-server pod's system trust store, and the chart set no `openID.ca` trust anchor.

Separately, the demo cluster also runs the external startx `cluster-auth` Helm chart (via a `startx-cluster-auth` ArgoCD Application in `openshift-gitops`), which manages the same `OAuth`/`cluster` singleton with its own settings: an htpasswd IDP (`startx-htpasswd_auth`, Secret `startx-htpasswd-htpasswd-auth`), branded login/error/provider-selection templates (`startx-{login,errors,providers}-template` Secrets), and `tokenConfig.accessTokenMaxAgeSeconds: 86400`. Two ArgoCD apps cannot both own a cluster-scoped singleton — each self-heal rewrites the other's tracking annotation and metadata, flapping forever.

## Decision

`gitops/charts/openshift-oauth` becomes the single intended owner of the full `OAuth`/`cluster` spec, absorbing the startx settings, and the OpenID IDP gets a proper CA trust anchor:

- **`openID.ca`** (new value `oauth.openidCaConfigMap`, default `""` = omitted): references a ConfigMap in `openshift-config` holding the router CA under key `ca.crt`. The ConfigMap is cluster-specific, so Helm can't render it: `ansible/roles/openshift_oauth/tasks/install.yml` copies it from `openshift-config-managed/default-ingress-cert` (key `ca-bundle.crt`, maintained by the ingress operator) into `openshift-config/default-ingress-cert` (re-keyed to `ca.crt`) before applying the d1 Application — same look-up/blocked-finding(ADR-0344)/copy pattern as `openshift_ai`'s `istio-ca-root-cert` copy. The copy runs unconditionally each install/reconcile, so a router cert rotation is healed by `make d0 reconcile openshift-oauth`. `uninstall.yml` deletes the copy; `precheck.yml` counts it toward "installed".
- **htpasswd IDP** (values-gated, off by default): `startx-htpasswd_auth`, `mappingMethod: claim` (preserved from startx), `fileData` Secret `startx-htpasswd-htpasswd-auth`. This repo only **references** the startx-managed Secret, never creates it.
- **Login templates** (values-gated, off by default): `startx-login-template` / `startx-errors-template` / `startx-providers-template`, again referenced, not created.
- **`tokenConfig.accessTokenMaxAgeSeconds`** (default `null` = omitted): 86400 on the demo cluster.
- **Metadata stays repo-conventional** (`zuno.io/managed-by: argocd` only) — the startx labels, `argocd.argoproj.io/tracking-id`, and `helm.sh/resource-policy` annotations are chart-generated startx artifacts and are deliberately not copied.
- All four features are enabled only in `gitops/apps/openshift-oauth/application-d1.yaml`'s inline values (cluster-specific by design); chart defaults keep them off so `helm template` output is unchanged from pre-ADR-0346 when disabled.
- The OpenID IDP stays **first** in `identityProviders` (list order is the login-page provider order), htpasswd second.

## Consequences

The authentication operator's TLS degradation is fixed at the root (trust anchor) rather than by removing the Keycloak IDP; console login works via Keycloak *and* the startx htpasswd fallback. **Exactly one ArgoCD Application may manage `OAuth`/`cluster`**: the operator must remove/disable the startx `cluster-auth` app's management of the singleton (or exclude the resource from it) when rolling this out, otherwise the two apps self-heal-fight (OutOfSync flapping, `SharedResourceWarning`). Login-page provider ordering may visibly change versus the startx-rendered resource (Keycloak first — deliberate). Mixed mapping methods are intentional: `add` for OpenID (ADR-0320/0332 rationale) and `claim` for htpasswd (startx behavior preserved).

## Security considerations

The router CA is public certificate material — copying it between namespaces exposes nothing. No secret is created or moved: the htpasswd file and template Secrets remain owned by the startx chart; this repo stores only their names. `tokenConfig.accessTokenMaxAgeSeconds: 86400` (24h) matches the absorbed startx setting and replaces the API default of 86400 anyway (explicit rather than implicit).

## Operational considerations

- Enabling `oauth.htpasswd`/`oauth.templates` on a cluster without the startx Secrets does not degrade the operator, but the IDP/templates are silently not honored (per `oc explain`); verify the four Secrets exist in `openshift-config` first.
- The d1 Application has `prune: true`: deleting/disabling it deletes `OAuth`/`cluster`, which the operator recreates with an empty spec — wiping the absorbed startx configuration too and breaking all non-kubeadmin login. Pre-existing risk (ADR-0320), larger blast radius now.
- If the default ingress cert is replaced (e.g. a custom wildcard cert), re-run `make d0 reconcile openshift-oauth` to refresh the CA copy; `default-ingress-cert` in `openshift-config-managed` always tracks the current default router cert's CA. If the Keycloak route is ever given a cert not signed by that CA, the copy source must change — out of scope here.
- A cluster installed pre-ADR-0346 reports NOT installed by `precheck.yml` until the next install/reconcile run — which is exactly the remediation that creates the missing CA ConfigMap.

## Acceptance criteria

- `oc get co authentication` shows `Available=True Degraded=False` with the `OAuthServerConfigObservationDegraded` x509 message gone after the `oauth-openshift` pods roll.
- `oc get oauth cluster -o yaml` shows both IDPs (OpenID first), `openID.ca.name`, the templates block, `tokenConfig.accessTokenMaxAgeSeconds: 86400`, and only zuno-managed metadata.
- Both a startx htpasswd user (`oc login`) and a Keycloak browser login succeed.
- `zuno-openshift-oauth-d0/-d1` stay Synced/Healthy with no OutOfSync flapping (i.e. the startx app no longer co-manages the singleton).
- `helm template` of the chart with all new gates off is byte-identical to the pre-ADR-0346 output.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0320](0320-pre-provision-openshift-users-rbac-and-console-favorites-via-keycloak.md)
- [ADR-0332](0332-remove-console-favorites-provisioning.md)
- [ADR-0344](0344-track-blocked-resources-and-add-a-day-0-reconcile-verb.md)
