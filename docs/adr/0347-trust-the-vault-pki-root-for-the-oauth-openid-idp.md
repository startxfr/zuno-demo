# ADR-0347: Trust the Vault PKI root for the OAuth OpenID IDP

- **Status:** Implemented
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0346 wired the cluster OAuth OpenID IDP's `openID.ca` to a copy of the **default ingress router CA**, on the assumption that `https://keycloak.<domain>` was served by the router's default wildcard certificate. After that change was applied on the demo cluster (`demo222.startx.fr`), the `authentication` clusteroperator remained Degraded with the exact same message:

> `OAuthServerConfigObservationDegraded: failed to apply IDP openshift config: tls: failed to verify certificate: x509: certificate signed by unknown authority`

Live diagnosis found the assumption was wrong. Since [ADR-0316](0316-keycloak-route-tls-via-cert-manager.md), the keycloak chart renders Ingress `zuno` (`zuno-auth`) annotated `cert-manager.io/cluster-issuer: vault-issuer`; the resulting Route embeds a cert-manager-issued certificate (Secret `keycloak-tls`) signed by `CN=zuno-demo.internal` - the root of Vault's `pki/` secrets engine mount, generated once in `ansible/roles/vault/kustomize/unseal-configure/configmap.yaml` and never otherwise persisted to a Secret or ConfigMap. Confirmed with `openssl s_client` against the live host: verification fails against the router CA, succeeds (return code 0) against `keycloak-tls`'s `ca.crt`.

`oc explain oauth.spec.identityProviders.openID` has no `insecureSkipVerify`-style escape hatch - there is no way to bypass this check, only to supply the correct trust anchor.

Two alternatives were considered and rejected before settling on the fix below:

1. **Route the OpenID issuer through a second, default-router-cert-backed hostname**, avoiding the Vault-signed chain entirely. Blocked: the live Keycloak CR has `spec.hostname.strict: true`, pinned to `keycloak.apps.demo222.startx.fr`. In strict mode, Keycloak's OIDC discovery document always reports that exact hostname as `issuer`, regardless of which route actually served the request. OpenShift's OAuth server requires the discovery document's `issuer` to exactly match the configured `openID.issuer`, so pointing OAuth at a second hostname would fetch a discovery document claiming a *different* issuer and fail with a hard mismatch. Making this work would require relaxing Keycloak's own hostname configuration, which affects all five agent frontend OIDC clients, not just OAuth - a materially bigger and riskier change than the one below.
2. **Fix only the scoped `openID.ca` reference**, leaving cluster-wide trust untouched. Rejected as insufficiently defensive: it's a single, easy-to-repeat mistake (this ADR exists because the wrong CA was assumed once already) with no redundancy if the assumption is wrong again or the referenced ConfigMap is accidentally deleted.

## Decision

Two complementary fixes, both applied by `ansible/roles/openshift_oauth/tasks/install.yml` (cluster-specific certificate data, can't be rendered by Helm) and referenced by name from `gitops/charts/openshift-oauth`:

1. **Scoped fix, corrected**: ConfigMap **`keycloak-serving-ca`** (`openshift-config`, key `ca.crt`) bundles `keycloak-tls`'s `ca.crt` (`zuno-auth` - the actual trust anchor) with the router CA (kept as a fallback covering the keycloak chart's `ingress.operatorManaged` toggle). Referenced by `oauth.openidCaConfigMap` in `gitops/charts/openshift-oauth/templates/oauth.yaml` (structure unchanged from ADR-0346, only the source data is corrected). The superseded ADR-0346 artifact, ConfigMap `default-ingress-cert` in `openshift-config`, is removed.
2. **New, cluster-wide complement**: ConfigMap **`user-ca-bundle`** (`openshift-config`, key `ca-bundle.crt` - the key name OpenShift's `proxy.spec.trustedCA` convention requires) holds just the Vault PKI root. A new template, `gitops/charts/openshift-oauth/templates/cluster-trusted-ca.yaml` (gated `clusterTrustedCA.enabled`, off by default), patches `Proxy/cluster.spec.trustedCA.name` to reference it. Unlike the `OAuth`/`cluster` template, this is a **partial patch, not wholesale ownership** - `Proxy`/`cluster` carries other operator-managed fields (`httpProxy`, etc.) this chart must never touch; `kubernetes.core.k8s`/ArgoCD's default apply merge only the fields a manifest declares. `proxy/cluster.spec.trustedCA.name` was confirmed empty/unclaimed on the demo cluster before this landed, so there is no existing owner to conflict with.

Cluster-wide trust is not conceptually OAuth-specific - `proxy/cluster.spec.trustedCA` is consumed by every operator whose own `trusted-ca-bundle` ConfigMap carries the CNO injection label `config.openshift.io/inject-trusted-cabundle: "true"` (confirmed live: `openshift-authentication-operator`'s already does, which is how this reaches the oauth-server pod). OAuth's OpenID IDP is simply the only current consumer, so both fixes live in this one chart/role rather than splitting into a new component for one ConfigMap and one field patch.

Both `gitops/apps/openshift-oauth/application-d1.yaml` values (`oauth.openidCaConfigMap: keycloak-serving-ca`, `clusterTrustedCA.enabled: true`) are cluster-specific and set only there; chart defaults keep both off so `helm template` output with all gates disabled is unchanged.

## Consequences

The authentication operator's TLS degradation is fixed at its actual root cause. OAuth's OpenID IDP now trusts the Vault PKI root two independent ways (scoped `openID.ca` and cluster-wide `proxy.trustedCA`) - a ConfigMap deletion or a future misconfiguration of one path doesn't immediately re-degrade the operator. The cluster-wide trust addition has a real, if low, blast radius on a demo cluster: every future component that reads the CNO-merged trust bundle will trust `zuno-demo.internal` as a CA, not just OAuth - acceptable here since it's an internal-only root with no other current consumer, but worth remembering before repurposing `user-ca-bundle` for anything unrelated.

## Security considerations

No secret material is created or exposed - `keycloak-tls`'s `ca.crt` and the router CA are both public certificate data (CA certificates, not private keys). `proxy/cluster.spec.trustedCA` is a standard, documented OpenShift mechanism for exactly this class of problem (an internal/private CA an operator needs to trust); it is not a security bypass, and it does not weaken TLS verification anywhere it's consumed - it only adds one internal root to what's already trusted.

## Operational considerations

- If the Vault PKI root is ever regenerated (not expected in the lifetime of this demo - `pki/root/generate/internal` runs once, at Vault bootstrap), both ConfigMaps go stale until the next `make d0 reconcile openshift-oauth`, which re-copies from the live `keycloak-tls` Secret.
- `templates/cluster-trusted-ca.yaml`'s partial-patch approach means `uninstall.yml` deleting `user-ca-bundle` un-claims the reference but does not itself clear `proxy/cluster.spec.trustedCA.name` - low risk, since an empty/default `Proxy` spec is the operator's own normal state (unlike `OAuth`/`cluster`'s prune risk, documented in ADR-0346, where an empty spec breaks all non-kubeadmin login).
- A cluster installed under ADR-0346 (pre-ADR-0347) reports NOT installed by `precheck.yml` until the next install/reconcile run - which is exactly the remediation that creates `keycloak-serving-ca` and `user-ca-bundle` and removes the superseded `default-ingress-cert`.

## Acceptance criteria

- `oc get co authentication` shows `Available=True Degraded=False` with the `OAuthServerConfigObservationDegraded` x509 message gone after the `oauth-openshift` pods roll.
- `oc get cm keycloak-serving-ca user-ca-bundle -n openshift-config` both exist with the expected keys/content; `default-ingress-cert` no longer exists in `openshift-config`.
- `oc get proxy cluster -o jsonpath='{.spec.trustedCA}'` shows `{"name":"user-ca-bundle"}`, and other pre-existing `spec` fields (e.g. `httpProxy`) are unchanged.
- Both a startx htpasswd user (`oc login`) and a Keycloak browser login succeed.
- `helm template` of the chart with all new/changed gates off is byte-identical to the pre-ADR-0346 `OAuth`/`cluster` output (the `Proxy` template renders nothing when `clusterTrustedCA.enabled` is false).

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0316](0316-keycloak-route-tls-via-cert-manager.md)
- [ADR-0344](0344-track-blocked-resources-and-add-a-day-0-reconcile-verb.md)
- [ADR-0346](0346-trust-the-ingress-router-ca-and-absorb-the-startx-cluster-auth-oauth-settings.md)

## Implementation note (2026-08-25) — the `make d0 reconcile openshift-oauth` command in this ADR was never runnable

This ADR names `make d0 reconcile openshift-oauth` as the remedy for a router-cert rotation. That command has never worked: `openshift-oauth` is a Day 1 component (`DAY1_RUN_COMPONENTS`), and `reconcile` was a Day 0 verb, so the Day 0 dispatcher rejected the pair. The same string was recorded as an `auto_fix` hint in `ansible/roles/openshift_oauth/tasks/install.yml`, where nothing validated or executed it.

`reconcile` now exists on Day 1 as well, so **read every occurrence here as `make d1 reconcile openshift-oauth`**. See ADR-0344's 2026-08-25 note for the verb change and for the `check_docs.py` lint that now fails CI on any `auto_fix` naming a command the Makefile would reject.

## Implementation note (2026-09-03) — the cluster-wide anchor is sourced from the Vault root, and "off" is an empty string

This ADR's decision is unchanged. Its implementation was half-conditional, and that
cost a cluster-wide outage.

**What happened.** `3fd54da7` (2026-08-16) made ConfigMap `user-ca-bundle` conditional
on the Secret the Keycloak Ingress serves carrying a `ca.crt`, but left
`clusterTrustedCA.enabled: true` hardcoded in
`gitops/apps/openshift-oauth/application-d1.yaml`. Two layers then decided the same
question differently. When ADR-0211's ACME wildcard was re-issued on 2026-09-02
(`keycloak-wildcard-tls`, `letsencrypt-route53`, no `ca.crt`), the next run of this role
deleted the ConfigMap and `Proxy/cluster` kept referencing it:
`ClusterOperator/network` `Degraded=True` from `2026-09-03T08:31:26Z`, cluster-wide.

**The design error, corrected.** Reading the Ingress's current Secret conflates two
questions: *"what CA signs the cert Keycloak serves?"* (correct for
`keycloak-serving-ca`/`openID.ca`, and still read that way) and *"does this cluster have
a private PKI root worth trusting cluster-wide?"* (what `user-ca-bundle` is for). ACME
changes the first answer and nothing about the second — `CN=zuno-demo.internal` still
signs `zuno-data/mariadb-server-cert` and `zuno-mesh/istiod`, and was still present in
all 41 CNO-injected bundles while the reference dangled. The cluster-wide anchor is now
read from the Vault-issued Secret **by name**, so the ACME flip cannot strand it.

**Corrections to this ADR's own text:**

- **Acceptance criterion 3** — `oc get proxy cluster -o jsonpath='{.spec.trustedCA}'`
  shows `{"name":"user-ca-bundle"}` **only when this cluster has a private PKI root**.
  Where it has none, the correct value is `{"name":""}`, not an absent field.
- **Operational considerations** — the partial patch does now clear
  `spec.trustedCA.name`, by writing an explicit empty string. It has to: a
  `{{- if }}`-gated template plus `Prune=false` can never clear anything, which is
  precisely how the stale reference survived for 18 days. `clusterTrustedCA.enabled`
  therefore now means *"this chart owns the field"*, not *"a private CA is in use"*;
  `configMapName: ""` is the off state.
- **Acceptance criterion 5 still holds** — chart defaults render no `Proxy` at all.

**Latent risk closed at the same time.** `openshift-config/user-ca-bundle` is
OpenShift's own reserved name for the installer's `additionalTrustBundle`. The 2026-08-16
removal task deleted it unconditionally, which on a cluster installed behind an egress
proxy would be a cluster-wide egress outage caused by this role. Creation now labels it
`zuno.io/managed-by: zuno-ansible` and removal refuses anything without that label.
demo222 was unaffected (`httpProxy`/`httpsProxy`/`noProxy` all empty), which is why this
went unnoticed.

**Live evidence (2026-09-03).** ConfigMap restored with `CN=zuno-demo.internal`
(valid to 2036); `network` `Degraded=False`; all 34 ClusterOperators
`Available=True Progressing=False Degraded=False`; the injected bundle holds 147
certificates before and after, still including the Vault root — **a zero trust delta**,
because `keycloak-tls` and `mariadb-server-cert` carry a byte-identical `ca.crt`;
`OAuth/cluster` intact (both IDPs, all three templates, `tokenMaxAge`); Keycloak's OIDC
discovery returns 200 **without** `-k`.
