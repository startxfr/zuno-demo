# WP-248: Replace the OKF mirror with an internal Red Hat Quay that holds every zuno image

- **State:** Not started
- **ADRs:** [ADR-0611](../../adr/0611-mirror-the-admitted-okf-release-into-the-internal-registry.md) (its registry choice is
  replaced by the ADR this WP writes), [ADR-0353](../../adr/0353-source-runtime-images-by-family-internal-registry-or-quay-io-zuno.md)
  (images sourced by family), [ADR-0546](../../adr/0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md)
  (per-cluster S3 buckets)
- **Depends on:** [WP-246](wp-246-mirror-the-okf-release-into-the-internal-registry.md) (the zot mirror this replaces, kept until
  the drill passes), [WP-131](wp-131-per-cluster-s3-bucket-convention.md) (bucket naming and per-consumer identities),
  [WP-242](wp-242-canary-namespace-pattern.md) (the canary the measurement runs in)
- **Related:** [ADR-0547](../../adr/0547-parameterize-every-cluster-specific-value-in-ansible.md),
  [ADR-0607](../../adr/0607-pin-gate-and-schedule-pre-ga-dependencies.md) (the operator is a pinned, gated dependency),
  [ADR-0608](../../adr/0608-keep-the-repository-the-only-source-of-cluster-state.md) (the drift check reads image registries),
  [WP-247](wp-247-sign-gateway-assertions-with-vault-transit.md) (Vault holds the registry credentials)
- **Target:** v0.17
- **Estimated files touched:** ~25: a new `quay_registry` role and an AWS bucket role under `ansible/roles/`, the cluster
  variables, `platform/supply-chain/admit_okf_bundle.py` and its tests, a declared list of mirrored public images, the
  charts' `image.repository` values, the pull-secret and NetworkPolicy templates, the drift and known-good files, the
  `okf-mirror` role and chart (removed at the end), ADR-0611, ADR-0353, the new ADR

> Why: the owner wants to stay on Red Hat products and to stop depending on a public registry at pod start. On 2026-11-09 a
> pod hung on a `quay.io` blob (ADR-0611); the zot mirror fixed that for one artifact only. One internal Red Hat Quay that
> holds every zuno image, and a selection of public `quay.io` images, makes the whole platform rebuildable and rolled
> without leaving the cluster, with a supported registry instead of a community one.

## Goal

An internal Red Hat Quay (operator `quay-operator`, channel to be pinned) replaces the zot `okf-mirror` and serves:

1. the OKF release and its signatures (what the mirror serves today);
2. every first-party zuno image (the components built in the cluster, the supply-chain signer, the gateways);
3. the UnifAI release images, mirrored from `quay.io/zuno` by digest after verification;
4. a declared selection of public `quay.io` images, mirrored on demand.

A pod of any of these starts with `quay.io` unreachable, from the internal registry, with the same digests and the same
offline signature verification as today. Its blobs live in a dedicated AWS S3 bucket provisioned by Ansible.

## Steps

1. **Inventory and measurement gate, in a canary** ([ADR-0609](../../adr/0609-rehearse-on-canary-namespaces-of-demo333.md)).
   - Inventory every image reference the platform runs, by family: in-cluster builds (`zuno-ai-build`), `quay.io/zuno`,
     third-party public images (quay.io, docker.io, ECR public, registry.redhat.io), with sizes. Output: a table in this
     WP and the first version of the mirrored-images list (step 6).
   - Install `quay-operator` and a `QuayRegistry` in `zuno-canary-wp-248` with the object storage on the S3 bucket of
     step 3, **proxy storage enabled** so that clients are never redirected to a presigned S3 URL (the EgressFirewall does
     not allow every S3 address, the same mechanism as the 2026-11-09 `quay.io` CDN stall).
   - Prove, as WP-246 step 1 did for the internal registry: `oras cp -r` of the corp artifact keeps its signatures and
     attestations (referrers API and legacy `.sig` / `.att` tags), `cosign verify` reads them back by digest, the digest is
     identical; delete by digest works (the retention of ADR-0611); a pod reads the artifact through the mesh with a
     robot account. Record the resources the operator's components take (application, database, cache, scanner optional).
2. **Decision record.** A new ADR (Proposed, then Accepted after step 1) that replaces the registry choice of ADR-0611
   clause 1, widens its scope (clause 7) to every zuno image, and amends ADR-0353 so that one internal registry serves all
   families. It states the open questions below as decisions.
3. **The S3 bucket, provisioned by Ansible.** A role creates one additional bucket for the demo cluster, named by the
   WP-131 convention (`zuno-<cluster>-registry`, variable `zuno_quay_s3_bucket` in `ansible/clusters/<cluster>.yml`,
   ADR-0547), in the cluster's region (`eu-central-1` for demo333, passed explicitly: the AWS profile's declared region is
   wrong). Idempotent; public access blocked, default encryption on, versioning off (Quay deduplicates and garbage
   collects). A dedicated IAM user and policy scoped to this bucket only, never shared with the backup or model
   buckets. This is the repository's first AWS infrastructure as code: the role uses the `amazon.aws` collection, added to
   the collections requirements, and runs from the workstation with the AWS credentials of the operator; the access key
   goes to Vault and reaches the Quay config through the namespace secret store (no secret in git). Any AWS write needs
   the owner's go. The EgressFirewall of the registry namespace gets the region's published S3 CIDRs next to the name
   rules (the `dnsName` pool alone stalls large copies).
4. **The registry as a role.** `quay_registry`: Subscription (pinned channel, class `ga`, an entry in the known-good file),
   `QuayRegistry` with the unmanaged components chosen in step 1 (object storage on the bucket above, database decision
   below), route and TLS trusted by the pods (the cluster CA bundle sourced from the Vault root), an organization `zuno`,
   robot accounts (pull for the namespaces, push for builds and admission, secrets in Vault), ingress
   NetworkPolicies that admit only the consumers, the mesh decision. Day 0 and Day 1 split as ADR-0056.
5. **Seed and cut over, family by family.** (a) The OKF release: `admit_okf_bundle.py mirror` and `prune` target Quay
   (the retention of three releases, its Quay-side delete API, the check before rolling the gateways all carry over).
   (b) First-party images: builds push to Quay, or are promoted to it by digest, then each chart's `image.repository`
   moves. (c) UnifAI release images: mirrored from `quay.io/zuno` by digest after the pin script's verification
   (`pin_unifai_images.py`), then pinned from the internal registry. The admission policy controller (WP-178) and the
   drift check learn the new registry host. Each family is cut over with a golden path before and after.
6. **Public images from `quay.io`.** A declared list in the repository (`platform/supply-chain/mirrored-images.yaml`:
   source reference, policy by digest or by tag, signature identity where the image is signed, reason). A command copies
   each entry to Quay and verifies it; only digests are pinned in the charts. The copy runs where `quay.io` is reachable
   (the workstation, or a job with a measured egress), not as a Quay mirror worker behind the EgressFirewall, unless
   step 1 shows that path works. Nothing is mirrored that the list does not name.
7. **Retire zot.** After the drill passes and the golden path holds for a week of normal use, remove the `okf-mirror` chart,
   role, AAP nodes and PVC, and mark ADR-0611 as replaced.
8. **Drill.** In the canary and then on demo333: block `quay.io` and `docker.io`, roll a gateway, the UnifAI operator
   pod and one first-party component from the internal registry; show that a forged digest is refused; golden path 14/14.

Every cluster change in steps 1, 3, 4, 5 and 7 needs the owner's go and a golden path before and after; none runs during
a freeze ([ADR-0605](../../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md)). The zot mirror stays
until step 8 passes, and the gateways keep `quay.io` as their second source, so a failed cut-over is undone by moving the
references back.

## Open questions (decided in the new ADR from the step 1 measurement)

- Is a Quay entitlement available for demo333 (Quay is a subscription product)? If not, the WP stops at step 1.
- Database: the operator-managed PostgreSQL, or a database on the existing PGO operator (backups already exist there)?
- Object storage: the AWS bucket above (decided), or ODF if it is installed for another reason.
- Vulnerability scanning (Clair): on from the start, or later; its database and cost.
- Single replica or highly available: the platform runs single-replica workloads on purpose (ADR-0101); the registry is
  now on the pod-start path of everything, which changes the trade-off.
- Garbage collection and tag expiration so that the bucket does not grow without bound.
- Which public `quay.io` images are mirrored (the first list comes out of the step 1 inventory).
- Whether the in-cluster ImageStream registry is kept for builds or retired once builds push to Quay.

## Acceptance

With `quay.io` blocked, a gateway pod, the UnifAI operator pod and a first-party component reach Ready from the internal
Quay; a forged digest is refused; every image the charts reference is on the internal registry or on the declared exception
list; the bucket was created by Ansible, scoped to its own IAM user; the zot mirror is removed; the golden path passes 14
of 14; no CDN or S3 range wider than the measured need was added to an EgressFirewall.
