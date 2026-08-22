# ADR-0420: Sign supply-chain artifacts in-cluster with Vault Transit

- **Status:** Partially implemented - Vault Transit signing backend live
  (WP-068); OKF bundle and image signing still run the ADR-0106/ADR-0115
  GitHub-OIDC/Fulcio/Rekor mechanism this ADR supersedes, pending WP-069/070.
- **Target:** v0.4
- **Date:** 2026-08-22
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0115 (container image signing) and ADR-0106 (OKF agent-bundle signing)
both sign with keyless Cosign: GitHub Actions issues an OIDC token, Sigstore's
public-good Fulcio issues an ephemeral signing certificate from it, and
Sigstore's public-good Rekor records the signature in a public transparency
log. Images publish to `quay.io`. All three - GitHub Actions, Fulcio/Rekor,
quay.io - are external SaaS dependencies.

In practice this pipeline is already disabled. ADR-0115 recorded on
2026-08-22 that `.github/workflows/build-publish.yml`'s automatic triggers
were removed (now `workflow_dispatch` only), because deployment never
depended on it: every component actually builds via an in-cluster OpenShift
`BuildConfig` -> `ImageStream` at
`image-registry.openshift-image-registry.svc:5000/zuno-ai-build/<component>:latest`,
and no `gitops/charts/*/values.yaml` references `quay.io` for a first-party
image. ADR-0106/WP-05 hit the same wall from the other direction: CI produced
real signatures for all 8 agent bundles, but nothing ever copied them from
the ephemeral GitHub Actions artifact into the runtime pod, so
`ZUNO_REQUIRE_SIGNED_BUNDLES` stayed off.

Running entirely inside the cluster - no external identity provider, no
external registry, no external transparency log - is a stated goal of this
demo. This ADR replaces the *mechanism* both prior ADRs used (not what they
decided to sign or why) with one built from what is already deployed
in-cluster.

### What's already available in-cluster

- **Internal registry**: `image-registry.openshift-image-registry.svc:5000`,
  namespace `zuno-ai-build`, is the real, live, only deploy path today.
- **Vault** (`zuno-vault` namespace): KV v2 at `zuno/`, PKI at `pki/` with a
  self-signed root (`CN=zuno-demo.internal`), Kubernetes auth already
  enabled with an established, three-times-repeated pattern - a scoped Vault
  policy plus an `auth/kubernetes/role/<name>` bound to one
  ServiceAccount+namespace - used by cert-manager, MariaDB, and Istio
  issuers (`ansible/roles/vault/kustomize/unseal-configure/configmap.yaml`).
- **Keycloak**: human SSO only. ADR-0032 already considered and rejected a
  Keycloak service-identity/client-credentials flow for internal
  service-to-service calls, calling it "unused infrastructure"; every realm
  client has `serviceAccountsEnabled: false`. Not a fit for workload
  identity here.
- **No Tekton / OpenShift Pipelines** installed. The only in-cluster
  automation hook is Ansible-triggered `oc start-build --wait`
  (`ansible/tasks/apply_openshift_build.yml`) plus ordinary `Job` objects
  (precedent: the `vault-unseal-configure` Job).

## Decision

Sign in-cluster with **Vault Transit**, using cosign's native
`hashivault://` KMS mode, authenticated via Vault's existing Kubernetes-auth
pattern - not Vault PKI, and not a self-hosted Fulcio/Rekor.

A single non-exportable Transit key, `zuno-platform-signer`
(`ecdsa-p256`), signs server-side inside Vault; the private key material
never leaves Vault and cannot be exported
(`transit/keys/zuno-platform-signer/config` sets
`exportable=false`/`allow_plaintext_backup=false`). Verification needs only
the exported public key
(`platform/supply-chain/keys/zuno-platform-signer.pub`, committed to Git as
the trust anchor) - a verifier never needs Vault access, a token, or
network egress. This is a smaller trust surface than the GitHub-OIDC model
it replaces, where any verifier needed network access to Sigstore's public
Rekor to check the transparency log.

A dedicated ServiceAccount, `zuno-signer` in namespace `zuno-ai-build`
(`ansible/roles/supply_chain_signer_build`), is the only identity Vault's
new `platform-signer` Kubernetes-auth role trusts - mirroring the exact
`bound_service_account_names`/`bound_service_account_namespaces` shape
`eso-reader`/`cert-manager-issuer`/`mariadb-issuer`/`istio-issuer` already
use. No GitHub Actions runner, no OIDC token exchange with an external IdP.

Signing runs via a new minimal image, `supply-chain-signer`
(`components/supply-chain-signer/`, built the same
BuildConfig/ImageStream way as every other component), wrapping cosign and
`platform/supply-chain/sign_in_cluster.py`. Two cosign flags are load-bearing
and must never be dropped: `--tlog-upload=false` on sign, and
`--insecure-ignore-tlog=true` on verify. Omitting either makes cosign
silently reach out to the public `rekor.sigstore.dev` - the exact external
dependency this ADR exists to remove. There is no self-hosted transparency
log to consult instead; Vault's own audit device (`vault audit enable file
file_path=stdout`) is the honest in-cluster substitute - every `transit/sign`
call is an audited event, attributable to the authenticating ServiceAccount.

This ADR covers the signing backend only (WP-068). Cutting OKF bundle
signing (ADR-0106) and image signing (ADR-0115) over to it are separate,
sequenced work packages (WP-069, WP-070) - see Future work.

## Alternatives considered

**Vault PKI** (reuse the engine already live for cert-manager/Istio,
instead of adding Transit). Rejected: `vault write pki/issue/...` returns
the private key in the HTTP response body, so it would have to be persisted
in a Secret somewhere - reintroducing exactly the long-lived-key-file risk
keyless signing was designed to avoid. PKI's role profiles are also
TLS-shaped (`serverAuth`/`clientAuth` EKUs, bounded `max_ttl`), not a
code-signing profile, and a signature must stay verifiable for the
artifact's whole life, not just until a leaf cert's TTL expires.

**Self-hosted Fulcio/Rekor** (stand up an actual private Sigstore stack to
keep the exact ephemeral-cert/transparency-log model, just privately
hosted). Rejected as disproportionate: this means operating a CA service, a
transparency log service, and their own storage/availability, for a demo
platform - a much larger and more fragile build than one Vault Transit key,
for no capability this demo needs beyond what Transit already gives it.

**Keycloak-based workload identity** (issue OIDC tokens to the signing
Job/pod the way GitHub Actions did). Rejected on precedent: ADR-0032 already
evaluated and rejected exactly this shape for internal service-to-service
calls as "unused infrastructure," and no realm client has
`serviceAccountsEnabled: true` today. Vault's Kubernetes auth is the
in-cluster workload-identity mechanism this platform actually uses
(cert-manager, istio-csr, External Secrets Operator all authenticate to
Vault this way already).

## Accepted risks (and their remediations)

- **Vault becomes a signing single point of failure** (it was already a
  secrets single point of failure for the whole platform - this doesn't
  change its blast radius, just adds one more consumer). Remediation: same
  as every other Vault-dependent workload here - `vault-unseal-configure`
  re-runs after a reseal.
- **No public transparency log.** A compromised `zuno-signer` ServiceAccount
  could sign without an independent, tamper-evident public record.
  Remediation: Vault's audit device logs every `transit/sign` call
  in-cluster, attributable to the calling identity - not public, but real
  and queryable (`oc logs -n zuno-vault <vault-pod> | grep transit/sign`).
- **One shared signing key for all artifact kinds** (OKF bundles and,
  eventually, images use the same `zuno-platform-signer` key). Splitting
  into per-kind keys later (e.g. `zuno-okf-signer`/`zuno-image-signer`) is a
  two-line change to the configure script plus a second policy/role if a
  narrower rotation blast radius is ever needed - deliberately not built
  ahead of an actual requirement.

## Future work

- **WP-069**: cut `platform/supply-chain/sign_okf_bundle.py` and
  `components/agent-runtime/app/registry.py`'s `_verify_signature()` from
  the GitHub-OIDC/`.pem`-certificate model to `cosign.pub`-key mode,
  distribute signatures via Vault KV -> ExternalSecret instead of committed
  `.sig`/`.pem` files, keep `ZUNO_REQUIRE_SIGNED_BUNDLES=false` until all 8
  agent bundles verify live.
- **WP-070**: sign built images by digest against the internal registry,
  rewrite `platform/supply-chain/verify_signatures.py`'s registry prefix and
  identity check, retire or gut `.github/workflows/build-publish.yml` (its
  image-signing and `sign-okf-bundles` jobs), redirect
  `check_build_matrix.py`/`verify_signatures.py`'s own parsing of that
  workflow file first.

## Related ADRs

- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0032](0032-propagate-trusted-identity-end-to-end.md)
- [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
