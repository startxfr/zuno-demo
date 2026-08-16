# ADR-0211: Publicly-trusted wildcard TLS via cert-manager, Let's Encrypt and Route53 DNS-01

- **Status:** Implemented - see `gitops/charts/cert-manager/`, `gitops/apps/cert-manager/application-d1.yaml`

## Implementation note (2026-08-16)

Live rollout on demo222 completed end to end: staging rehearsal issued
all three Certificates, production cutover (`letsencrypt-route53`)
re-issued them with real Let's Encrypt chains, and the consumer flags
(router default cert, API server named cert, Keycloak ingress) all
flipped. Verified with plain `curl`/`openssl` (no `-k`, no custom CA) -
Console, Keycloak and `api.demo222.startx.fr:6443` all serve trusted
chains (`C=US, O=Let's Encrypt`). Two real defects found and fixed along
the way: the values rewrite that introduced `certificatesIssuer`
accidentally dropped `vaultServiceName`, letting a pruning sync delete
the live `vault-issuer` (every internal certificate's issuer) -
restored; and cert-manager's DNS-01 self-check walked to the AWS IPI
installer's private-zone NS records (unreachable `awsdns` names) and
never validated even though the public TXT was already visible -
`controllerConfig.overrideArgs` now forces the self-check through public
recursive resolvers, the documented split-horizon-DNS fix.
- **Target:** v0.2
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team
- **Renumbered:** formerly ADR-0348 (2026-08-15 move to the v0.2 stream)

## Context

Every TLS-serving endpoint in this repo today is either OpenShift's own self-signed default wildcard certificate or a certificate issued by Vault's self-signed internal PKI root (`pki/` mount, `CN=zuno-demo.internal`, bootstrapped once in `ansible/roles/vault/kustomize/unseal-configure/configmap.yaml`). [ADR-0316](0316-keycloak-route-tls-via-cert-manager.md) accepted this explicitly: "browsers won't trust the chain out of the box... not a regression versus the OpenShift default wildcard cert on a demo cluster (also typically self-signed)." [ADR-0346](0346-trust-the-ingress-router-ca-and-absorb-the-startx-cluster-auth-oauth-settings.md) and [ADR-0347](0347-trust-the-vault-pki-root-for-the-oauth-openid-idp.md) then had to build a real, live-tested workaround - bundling that self-signed root into ConfigMaps (`keycloak-serving-ca`, `user-ca-bundle`) so the cluster's *own* `oauth-server` pod would trust it - purely because nothing in this chain is publicly trusted. This is a symptom of the underlying gap, not a fix for it.

The user asked for the underlying gap to be closed: Vault/cert-manager issuing certificates from a publicly trusted authority, the OpenShift Console served with genuinely valid TLS, no self-signed certificates anywhere in that path, cost-efficient, using this project's AWS infrastructure, as a wildcard certificate.

### What was verified live before writing this ADR (all read-only)

- **This repo has no AWS provisioning automation at all** - no Terraform, no CloudFormation, no `amazon.aws`/`community.aws` Ansible collections. Every existing AWS touchpoint is S3-as-object-storage (the rag-ingestion corpus, optional PostgreSQL/MariaDB backups) - not infrastructure-as-code.
- **`startx.fr` is a public Route53 hosted zone** (`Z3HY376RT1N9S1`, "zone publique de STARTX", 88 records) in AWS account `791728029433`, the same account this session's already-authenticated credentials (`arn:aws:iam::791728029433:user/sx-eu-iam-user-cl`, `AdministratorAccess`) belong to. It already carries the exact records an OpenShift IPI installation needs: `api.demo222.startx.fr` (A) and `*.apps.demo222.startx.fr` (A, wildcard) - i.e. this project already controls the DNS zone a DNS-01 solver would need to write to.
- **ACM public certificates cannot be exported.** Confirmed directly against this account's own certificate history: an (expired) `*.drancy.startx.fr` cert, `Type: AMAZON_ISSUED`, `ExportOption: DISABLED`. An ACM public certificate's private key never leaves AWS - it can only be attached to AWS-integrated services (ALB, NLB, CloudFront), not installed into an arbitrary OpenShift/Kubernetes Secret. Using it here would require inserting an AWS load balancer in front of the existing router to terminate TLS - a materially larger architecture change than the goal warrants.
- **No AWS Private CA (ACM-PCA) exists in the account** (confirmed empty `list-certificate-authorities`). Provisioning one costs roughly $400/month plus per-certificate fees, and - the decisive point - **an ACM Private CA is not publicly trusted by browsers by default**. It would solve neither the cost requirement nor the trust requirement.
- **No public CA, including Let's Encrypt, will sign a subordinate/intermediate CA certificate for a third party for free.** This is a hard constraint: Vault's `pki/` engine cannot itself become "an authority chained to a public root" without a paid commercial CA contract (e.g. DigiCert/Sectigo private PKI programs), which is out of scope for a cost-efficient demo. The mechanism that actually satisfies "free, publicly trusted, wildcard, using our AWS infrastructure" is **cert-manager obtaining leaf certificates directly from Let's Encrypt via the ACME protocol, using Route53 to automate the DNS-01 domain-ownership challenge**. AWS's role here is proving domain ownership, not being the trust root - Let's Encrypt's root, already present in every OS and browser trust store, is. Vault's own PKI is unaffected by this decision and continues issuing self-signed, internal-only certificates (the istio service-mesh `pki/roles/istio`) exactly as today.
- No ACME/Let's Encrypt/DNS-01/HTTP-01 integration exists anywhere in this repo today (confirmed by repo-wide grep) - this is a net-new mechanism, not an extension of something partially built.

## Decision

1. **New ACME `ClusterIssuer`s** in `gitops/charts/cert-manager/templates/` (sibling to the existing `vault-issuer` template - the chart already installs the cert-manager operator via OLM, so this is additive):
   - `letsencrypt-route53` - production ACME directory (`https://acme-v02.api.letsencrypt.org/directory`), `solvers: [{dns01: {route53: {region: eu-west-3, hostedZoneID: Z3HY376RT1N9S1, accessKeyIDSecretRef/secretAccessKeySecretRef: ...}}}]`.
   - `letsencrypt-route53-staging` - the ACME **staging** directory, for rehearsing the full DNS-01 + issuance flow end-to-end without consuming Let's Encrypt's production rate-limit budget. Staging certs are not publicly trusted; this issuer is a validation tool, not a long-term consumer-facing one.
2. **A new, least-privilege IAM identity**, not the broad `AdministratorAccess` credentials used to research this ADR: a dedicated IAM user with a policy scoped to `route53:ChangeResourceRecordSets` and `route53:GetChange` on the `startx.fr` hosted zone's ARN only, plus `route53:ListHostedZonesByName` (`Resource: "*"`, required by the API). Created once, out of band, by the operator - this repo has no AWS-provisioning automation and shouldn't gain a new category of it for a single credential. The access key is placed in `ansible/confidential.yml`, the existing gitignored entry point already used for other operator-supplied secrets (Google OAuth client, S3 backup credentials).
3. `ansible/roles/vault/tasks/install.yml` gains one new guarded seed, using the idempotent check-then-write pattern [ADR-0345](0345-make-self-generated-vault-credentials-idempotent.md) established (`vault_seed_if_missing.yml`), writing the access key into a new Vault KV path (e.g. `keycloak/aws-route53-dns01`, mirroring the existing path-naming convention). A new `ExternalSecret` syncs it into the cert-manager operand namespace for the `ClusterIssuer`'s `solvers[].dns01.route53.secretAccessKeySecretRef`.
4. **Three separate `Certificate` resources** against `letsencrypt-route53` - not one - because cert-manager can only write a `Certificate`'s Secret into the `Certificate`'s own namespace, and the three consumers below live in three different namespaces (the same "ExternalSecret can't cross namespaces" constraint this repo already routes around elsewhere, e.g. [ADR-0320](0320-pre-provision-openshift-users-rbac-and-console-favorites-via-keycloak.md)'s two ExternalSecrets for one Vault path):
   - `openshift-ingress/router-wildcard-tls` - DNS name `*.apps.demo222.startx.fr`.
   - `zuno-auth/keycloak-wildcard-tls` - same DNS name (duplicate-certificate count: 2/week, comfortably under Let's Encrypt's 5/week duplicate-certificate limit, distinct from its 50/week per-registered-domain limit).
   - `openshift-config/api-server-tls` - DNS name `api.demo222.startx.fr` (a distinct SAN, its own rate-limit bucket).
5. **`IngressController/default`** (`operator.openshift.io/v1`, `openshift-ingress-operator`) patched - a partial merge, the same pattern [ADR-0347](0347-trust-the-vault-pki-root-for-the-oauth-openid-idp.md) used for `Proxy/cluster`, not wholesale ownership - setting `spec.defaultCertificate.name: router-wildcard-tls`. This is what actually serves the Console and every Route that doesn't set its own certificate override; it directly satisfies "the Console served with a certified TLS connection."
6. **Keycloak's `Ingress`** (`gitops/charts/keycloak/templates/ingress.yaml`) switches `spec.tls[].secretName` to `keycloak-wildcard-tls` and drops the `cert-manager.io/cluster-issuer: vault-issuer` annotation - it consumes the already-issued wildcard Secret directly rather than requesting its own per-route ACME certificate.
7. **`APIServer/cluster`** (`config.openshift.io/v1`) patched: `spec.servingCerts.namedCertificates` gains `{names: ["api.demo222.startx.fr"], servingCertificate: {name: api-server-tls}}`, giving `oc login`/kubeconfig clients a trusted API endpoint with no CA flags needed.

## Consequences

The Console, Keycloak, and the API server all present certificates chained to a public root already trusted by every browser, OS, and standard TLS client - no custom CA distribution is required for any of these three paths going forward. This removes the specific need that motivated ADR-0346/ADR-0347: once Keycloak's certificate is publicly trusted, the `oauth-server` pod's default system trust already covers it. **A follow-up ADR (not executed here) should evaluate retiring `keycloak-serving-ca`, `user-ca-bundle`, `Proxy/cluster.spec.trustedCA`, and `oauth.openidCaConfigMap`** once this lands and is verified stable - they become redundant, though removing them is a separate, deliberate decision, not a side effect of this one. Vault's own PKI (`pki/roles/istio`, internal service-mesh trust) is untouched and keeps its current self-signed root - this decision does not change how internal, non-browser-facing TLS works.

## Cost analysis

| Item | Cost |
|---|---|
| Let's Encrypt certificates | $0 (free, subject to published rate limits) |
| Route53 hosted zone | Already exists and already paid for - zero incremental cost |
| Route53 DNS-01 API calls (a handful per ~60-day renewal cycle, per certificate) | Negligible (well within AWS free-tier-equivalent pricing) |
| New IAM user/policy | $0 |
| **Total incremental cost** | **~$0/month** |
| *Rejected alternative: ACM Private CA* | *~$400/month minimum plus per-certificate fees - and still not publicly trusted* |

## Security considerations

The new IAM identity is scoped to exactly the two Route53 actions DNS-01 needs, on exactly one hosted zone - a large reduction versus the `AdministratorAccess` credentials used to research this ADR, which must not be reused for cluster automation. Private keys for every issued certificate are generated inside the cluster by cert-manager and never leave it; Let's Encrypt only ever receives a CSR. DNS-01 challenge TXT records are transient (created and removed automatically per validation) and disclose nothing beyond domain names that are already public. Both new secrets this decision introduces - the AWS access key and cert-manager's ACME account key - flow through Vault, consistent with every other credential in this repo.

## Operational considerations

Renewal is fully automatic: cert-manager renews roughly 30 days before each certificate's ~90-day Let's Encrypt expiry, with no operator action required in steady state. The rate-limit budget in this design (two duplicate-SAN requests plus one distinct-SAN request) sits comfortably under Let's Encrypt's published 5/week duplicate-certificate and 50/week per-registered-domain limits. If the AWS credential is ever revoked or the IAM policy narrowed incorrectly, renewals fail silently and certificates keep working until the existing ones expire (~60 days of warning in practice, since renewal starts 30 days early and Let's Encrypt certs last 90) - this repo has no monitoring/alerting hook for cert-manager `Certificate` readiness yet, which is flagged as future work rather than solved here.

## Implementation state

This ADR records a proposed architectural decision, verified against live AWS-account and DNS state but **not yet implemented**. No code, chart, Ansible role, IAM resource, or DNS record has been created or changed as part of writing this ADR. It remains `Proposed` until the user approves it and a follow-up implementation pass lands the `ClusterIssuer`s, Vault seed, `Certificate` resources, and the `IngressController`/`APIServer`/Keycloak patches described above, verified end-to-end first against the Let's Encrypt **staging** issuer before cutting over to production.

### Implementation note (2026-08-15)

The user approved implementation; the repo side is merged, everything shipped **disabled** behind flags mirroring the phased rollout above:

- `gitops/charts/cert-manager` gained an `acme:` values block (`enabled: false`) gating both `ClusterIssuer`s (`templates/acme-clusterissuers.yaml`), the `aws-route53-dns01` `ExternalSecret` into the cert-manager operand namespace (`templates/acme-externalsecret.yaml`), the three `Certificate` resources (`templates/acme-certificates.yaml` — referencing `acme.certificatesIssuer`, shipped as the **staging** issuer per acceptance criterion 1), and the two consumer partial-patches (`templates/acme-cluster-patches.yaml`, each behind its own `acme.consumers.*` flag since pointing the router at a not-yet-issued Secret would break serving).
- The Keycloak switch is `gitops/charts/keycloak` `ingress.acmeWildcardTLS: false` — when flipped, the Ingress consumes `keycloak-wildcard-tls` and drops the `vault-issuer` annotation, exactly as Decision point 6 describes.
- `ansible/roles/vault` seeds `aws/route53-dns01` from two new `ansible/confidential.yml` fields (guarded, skipped while placeholders — same pattern as the Google OAuth seed); `ansible/confidential.example.yml` documents the exact least-privilege IAM policy inline.

Remaining to close (live, in order): create the IAM user/key + fill `confidential.yml` + re-run the Vault seed; flip `acme.enabled: true`; verify a staging wildcard issues (acceptance criterion 1); flip `acme.certificatesIssuer` to production; after all three `Certificate`s are `Ready: True`, flip `acme.consumers.*` and `ingress.acmeWildcardTLS`; verify Console/Keycloak/`oc login` present publicly trusted chains (criteria 2–4) and confirm the follow-up ADR evaluation named in Consequences.

## Acceptance criteria

- `letsencrypt-route53-staging` successfully issues a staging (untrusted) wildcard certificate via Route53 DNS-01, proving the IAM policy, hosted-zone ID, and solver configuration are correct, before the production issuer is used.
- `oc get co ingress` (and the browser) show the Console served by a certificate chained to a publicly trusted root, with no custom CA import required.
- Keycloak's route and the API server (`oc login` without `--insecure-skip-tls-verify` or a custom CA bundle) both present publicly trusted certificates.
- `cert-manager` reports all three `Certificate` resources `Ready: True`, and a renewal (or a forced reissue) succeeds without manual intervention.
- The new IAM policy is confirmed scoped to only the `startx.fr` hosted zone and the two required Route53 actions - not broader.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered and Migration/evolution.

## Related ADRs

- [ADR-0316](0316-keycloak-route-tls-via-cert-manager.md)
- [ADR-0346](0346-trust-the-ingress-router-ca-and-absorb-the-startx-cluster-auth-oauth-settings.md)
- [ADR-0347](0347-trust-the-vault-pki-root-for-the-oauth-openid-idp.md)
