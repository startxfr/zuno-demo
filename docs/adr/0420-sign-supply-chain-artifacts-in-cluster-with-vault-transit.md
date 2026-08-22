# ADR-0420: Sign supply-chain artifacts in-cluster with Vault Transit

- **Status:** Implemented - WP-068 (backend), WP-069 (OKF bundle signing,
  `ZUNO_REQUIRE_SIGNED_BUNDLES=true` live on the real Deployment), and
  WP-070 (image signing, all 14 first-party images signed and an
  automated `make d2 check supply-chain` gate live) are all Done - see the
  2026-08-22 implementation notes below.
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

## Implementation note (2026-08-22, WP-069/WP-070)

Both cutovers landed and were live-verified on api.demo222.startx.fr in the
same pass as this ADR. One correction to the Decision text above: the
`--tlog-upload=false`/`--insecure-ignore-tlog=true` flags are specific to
`cosign sign-blob`/`verify-blob` (used for OKF bundles). Plain
`cosign sign`/`verify` (used for OCI images, WP-070) has no such flags at
all - it gates transparency-log use behind an opt-in `COSIGN_EXPERIMENTAL`
environment variable instead, which this repo never sets anywhere. Same
outcome (no Rekor contact), different mechanism per artifact kind.

Real, non-obvious problems only live testing surfaced, each fixed in
follow-up commits: the `platform-signer` Vault policy needed both the bare
`transit/sign/<key>` path and a `/*` glob (cosign's hashivault client calls
the hash-algorithm-suffixed path); the audit-device "already enabled" guard
needed a second error-string match (`sys/audit` words it differently than
`sys/mounts`); `zuno-vault`'s NetworkPolicy needed `zuno-ai-build` added to
its allowlist; the image-signing path needed the internal registry's
service-serving CA trusted (`SSL_CERT_FILE`), a Docker-config-based
registry credential built from the pod's own ServiceAccount token (cosign
has no ambient Kubernetes-token registry auth), a `system:image-builder`
RoleBinding for `zuno-signer` (pull-only isn't enough - signing pushes a
new manifest), and the `platform-signer` policy needed
`zuno/data/okf-signatures` write access alongside its Transit paths. The
Job-completion wait logic in both signing tasks also needed fixing:
checking raw `succeeded`/`failed` pod counters races with
`backoffLimit` retries and can report a false failure mid-retry, before the
Job's real, eventual success - both now wait for a terminal
`status.conditions` entry instead.

Confirmed live: all 8 agent bundles signed, written to Vault KV, synced by
`externalsecret-okf-signatures.yaml` into a real Secret, and independently
re-verified using the actual deployed `app/_sign_okf_bundle.py`/
`app/registry.py` code path with `ZUNO_REQUIRE_SIGNED_BUNDLES=true` in a
debug pod - `AgentRegistry` loaded all 8 with zero errors, and a tampered
bundle copy was correctly rejected. Five real images signed
(`supply-chain-signer`, `ai-gateway`, `agent-runtime`, `agent-bff`,
`agent-frontend`) and independently re-verified with
`cosign verify --key` from a separate pod.

Also found, out of scope to fix here: `ansible/playbooks/day2_build.yml`
sets `day2_verb: build`, but `apply_openshift_build.yml`'s "force a fresh
Build" task only checks `day1_verb` - `make d2 build <component>` silently
never forces a genuinely fresh Build for a component that already has one
(falls back to the same "ensure this image exists" re-verify path a plain
install would take). Worked around here with a direct `oc start-build
--wait` for testing; the underlying Day 2 build-verb gap is a separate,
pre-existing issue this ADR didn't introduce.

## Implementation note (2026-08-22, WP-069 enforcement + WP-070 completion)

**WP-069 enforcement flip**: `gitops/charts/agent-runtime/values.yaml`'s
`requireSignedBundles` is now `true` on the real chart, synced to the
running Deployment (`oc rollout status` confirmed a successful rollout,
zero restarts, and the pod's own logs show all 8 agents verified at
startup - the exact production cutover the earlier note's live-verified
debug-pod proof was gating).

**WP-070 completion**: every one of the 14 first-party images now carries
a real signature, confirmed with `cosign verify --key` against
`platform/supply-chain/keys/zuno-platform-signer.pub` from a separate pod:
`agent-runtime`, `agent-bff`, `agent-frontend`, `ai-gateway`,
`aiagent-operator`, `mcp-gateway`, `mcp-confluence`, `mcp-git-forge`,
`mcp-sales-db`, `mcp-salesforce`, `mlops`, `rag-ingestion`, `rag-service`,
`supply-chain-signer`.

One near-miss worth recording: `ai-gateway`'s first signing attempt
(during the original 5-image pass above) actually failed silently -
`supply-chain-signer:latest` hadn't yet been rebuilt with the `sign-image`
subcommand at that point in the session, so the Job errored with "invalid
choice: 'sign-image'" and was never retried. It wasn't caught until this
final all-14-images verification sweep, which is exactly the value of
checking every image explicitly rather than trusting an earlier "it
worked" from a different image's Job log - Ansible's own per-Job log
display picked an arbitrary (sometimes stale) pod when multiple attempts
share the `job-name` label, so a green playbook run is not sufficient
proof; a live `cosign verify` against the real Image is. Re-signed and
confirmed.

`aiagent-operator` has no Makefile/Day1/Day2 build-component wiring at all
(confirmed: absent from every `DAY*_BUILD_COMPONENTS` list despite its own
`ansible/roles/aiagent_operator_build` role existing) - signed here via a
direct ansible invocation rather than `make d1/d2 build`. Not fixed as
part of this ADR; a genuine, pre-existing, unrelated gap.

## Implementation note (2026-08-22, WP-070 check gate + build-publish.yml decision)

The two items WP-070 left open closed out in the same pass:

**Automated check gate**: `make d2 check supply-chain`
(`ansible/roles/supply_chain`, no install/build counterpart - purely a
verification gate) resolves every first-party image's live digest locally
(`platform/supply-chain/verify_signatures.py --list-refs` - cluster API
access only, no registry network needed) and hands the resolved list to
an in-cluster Job that runs the real `cosign verify`
(`platform/supply-chain/sign_in_cluster.py`'s new `verify-images`
subcommand, against the public key baked into `supply-chain-signer` at
build time - no Vault access needed to verify, the same principle as
everywhere else in this ADR). Same "resolve outside, verify inside" split
as the signing Jobs. Live-verified both directions: a clean run reports
`RESULT: PASS - all 13 image(s) verified`, and a deliberately tampered
digest correctly fails the gate, naming the offending image. Folded into
`make d2 check all` with no regressions to the other 8 Day 2 components.

**`build-publish.yml`: kept, not retired.** Already fully stripped of
every signing step in the prior pass; still does build/SBOM/Trivy-scan/
optional-Quay-publish, gated behind `workflow_dispatch` only.
`RELEASING.md` already frames it as a deliberately preserved, dormant
path, and `check_build_matrix.py` still hard-depends on parsing its exact
job names - retiring it would mean rewriting that script's entire
validation strategy for no real benefit. Three stale doc references that
still described the removed keyless-GitHub-OIDC mechanism as live were
fixed instead: `.github/README.md`, `RELEASING.md` step 5, and
`docs/security/secnumcloud-controls.md`'s Supply chain table (two rows).

**Three more real bugs, found only by building the check gate against the
live cluster, not by reading the code:**

1. The first-party image filter matched on registry hostname prefix
   alone, which also caught *mirrored* third-party images (`vault`,
   `bitnami-kubectl` - pulled in by `ansible/roles/image_mirrors`, never
   built or signed by this pipeline) that happen to share the
   `zuno-ai-build` namespace. Fixed by requiring a matching `BuildConfig`
   to exist (`_has_build_config()`) - the real first-party/mirror
   distinguishing signal.
2. `agent-bff`/`agent-frontend` were completely invisible to the scan:
   every per-agent chart (tekos, comage, advantage, finage, arkos, naveo)
   declares them via a `registry`+`frontendRepository`/`bffRepository`+
   `tag` shape, not the `repository`+`tag` shape the walk only recognized
   before. Extended the shape-matching logic for the second form and
   deduplicated the resulting 6x-repeated refs (one per chart, same
   underlying image).
3. `cosign verify` (unlike `sign`) always initializes a local Sigstore TUF
   trust-root cache under `$HOME/.sigstore`, even in pure `--key` mode
   with no tlog contact at all - `HOME` is unset by default in the
   non-root `supply-chain-signer` image, so it tried and failed to write
   to `/`. Fixed at both layers: the verify Job sets `HOME=/tmp`
   explicitly, and `verify_image()` itself now defaults `HOME` to a
   writable tempdir if unset, so it works regardless of the caller's
   environment.

**A fourth, recurring finding, unrelated to any single Job**: ansible's
"fetch the signing/verify Job's pod" step used `.resources[0]` without
sorting - since `backoffLimit` lets multiple pods share one Job's
`job-name` label across retries, this repeatedly displayed an arbitrary
(often stale/failed) attempt's log instead of the one that actually
determined the Job's final outcome. This caused real, repeated confusion
this session - a Job that had genuinely succeeded kept showing an old FAIL
log, several times, across both the image-signing and the new verify Job.
Fixed once, across all three Jobs (`run_image_signing_job.yml`,
`run_okf_signing_job.yml`, `verify_image_signatures.yml`): sort by
`metadata.creationTimestamp` and always show the newest pod.

**Also found via the all-images verification sweep this gate makes
routine**: a concurrent session rebuilt `ai-gateway` (commit `b71d40a`,
unrelated mariadb work) without going through the in-cluster signing step,
leaving it unsigned again - exactly the kind of drift this check gate
exists to catch automatically going forward. Re-signed and reconfirmed.

## Related ADRs

- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0032](0032-propagate-trusted-identity-end-to-end.md)
- [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
