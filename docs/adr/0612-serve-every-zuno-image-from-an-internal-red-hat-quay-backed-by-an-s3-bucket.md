# ADR-0612: Serve every zuno image from an internal Red Hat Quay backed by an S3 bucket

- **Status:** Partially implemented (accepted 2026-11-11, the owner: Clair limited to the Red Hat sources; live on demo333 2026-11-12: families (a) OKF release, (c) UnifAI images and (d) public images, zot retired; family (b) first-party images and the retirement of the ImageStream registry, clause 9, are not started and wait for the owner)
- **Target:** v0.17
- **Date:** 2026-11-11
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0611](0611-mirror-the-admitted-okf-release-into-the-internal-registry.md) (its registry choice, clause 1, and its scope, clause 7, are replaced), [ADR-0353](0353-source-runtime-images-by-family-internal-registry-or-quay-io-zuno.md) (images sourced by family), [ADR-0546](0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md) (bucket convention), [ADR-0547](0547-parameterize-every-cluster-specific-value-in-ansible.md), [ADR-0607](0607-pin-gate-and-schedule-pre-ga-dependencies.md), [ADR-0609](0609-rehearse-on-canary-namespaces-of-demo333.md), [ADR-0101](0101-provide-ha-for-shared-agent-platform-services.md)

## Context

ADR-0611 put a small zot registry in `zuno-ai-run` so that a gateway pod start does not depend on `quay.io`. It covers one
family of artifacts. The platform runs images from five sources (in-cluster builds, `quay.io/zuno`, public registries,
NVIDIA, Red Hat), and the 2026-11-09 stall (F3 of ADR-0611) can hit any of those that are not on the cluster. The owner
asked on 2026-11-11 to use a Red Hat product, to hold every zuno image internally, and to mirror a declared selection of
public images. WP-248 measured Red Hat Quay in a canary.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | Quay keeps the OKF release with its `.sig` / `.att` tags and answers the OCI referrers API; `cosign` and `oras` read it back by the same digests. The OpenShift internal registry fails this test. | WP-248, result of step 1 |
| F2 | `oras manifest delete` is refused. Tags are deleted through the Quay API; untagged manifests are removed by Quay's garbage collector. | Same |
| F3 | Defaults ask about 5 CPU and 13 Gi for one replica of each component, before the database. A 4 Gi limit on the application restarts it. | Same |
| F4 | Without object storage, a pod restart loses blobs while the database keeps the metadata. | Same |
| F5 | Quay documents PostgreSQL 15; `zuno-data` runs 18 with 3 replicas. A small dedicated PGO cluster on 15 worked. | Same |
| F6 | Clair's updaters reach about ten internet hosts; every one is blocked by the namespace EgressFirewall. | Same |
| F7 | 163 containers use the in-cluster registry, 18 use `quay.io/zuno`, about 100 use public third-party images. | WP-248 inventory |

## Decision

**One internal Red Hat Quay, with its blobs in a dedicated AWS S3 bucket created by Ansible, replaces the zot mirror and
serves the OKF release, the first-party images, the UnifAI release images and a declared list of public images.**

1. **Registry.** Red Hat Quay through `quay-operator` (channel pinned, class `ga`, entry in the known-good file,
   ADR-0607), a single `QuayRegistry` in its own namespace, one replica of each component (ADR-0101). The accepted cost is
   that the registry is on the pod-start path for images not yet on a node; the `quay.io` second source and the
   fallback of ADR-0611 clause 3 stay until the drill passes.
2. **Storage.** Object storage is the bucket `zuno-<cluster>-registry` (variable `zuno_quay_s3_bucket`, ADR-0547), created
   by an Ansible role in the cluster's region, public access blocked, default encryption on, with a dedicated IAM user
   scoped to that bucket. **Proxy storage is on**, so clients never follow a presigned S3 URL (the F3 mechanism of ADR-0611).
   The namespace EgressFirewall gets the region's published S3 CIDRs beside the name rules. Any AWS write needs the
   owner's go. The access key goes to Vault.
3. **Database.** A dedicated PGO `PostgresCluster` on PostgreSQL 15 (F5), unmanaged component of the `QuayRegistry`,
   covered by the PGO backup and CA-trust rules. `zuno-data` is not reused.
4. **Scanning.** Clair is on. **Decision proposed: its updaters are limited to the Red Hat sources**, so the egress rule
   is a single host (`security.access.redhat.com`), and the other updaters (F6) stay disabled. Consequence, accepted: a
   Red Hat-based image gets vulnerability data, third-party and distroless images get none. Opening the other hosts is a
   later decision with its own measurement. Clair, its database and Redis take their default sizes only if the
   measured need exceeds them (F3 shows them under 120 Mi at rest).
5. **Trust is unchanged.** Digests and the keyless signatures of ADR-0578 decide what a pod accepts, not the registry.
   Images copied from elsewhere keep their digest; the copy fails if it differs.
6. **Retention.** The three-release rule of ADR-0611 carries over. `prune` gets a Quay variant that deletes tags through
   the API (F2). Tag expiration for the other repositories is defined after the first seeding, when the real volume is known.
7. **Scope, family by family.** (a) the OKF release; (b) first-party images, pushed by the builds or promoted by digest;
   (c) the UnifAI release images, copied from `quay.io/zuno` after the pin script's verification; (d) public images named in
   `platform/supply-chain/mirrored-images.yaml` (source, digest or tag policy, signature identity, reason), copied from
   where `quay.io` is reachable. Nothing is mirrored that the list does not name. The OpenShift release images and the
   Red Hat product images stay on the cluster pull secret and are out of scope.
8. **Cut-over and retirement.** Each family moves after a golden path, with a golden path after, and never in a freeze
   ([ADR-0605](0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md)). zot is removed after the drill
   (`quay.io` and `docker.io` blocked, a gateway, the UnifAI operator and a first-party component start, a forged digest is
   refused) and a week of normal use. ADR-0611 is then marked replaced and ADR-0353 amended.
9. **Open.** Whether the in-cluster ImageStream registry is kept for builds or retired once builds push to Quay is decided
   after clause 7(b), on a measured build time.

## Alternatives considered

- **Keep zot and extend it.** Smallest, but it is not a Red Hat product, has no scanning, no access model for robot
  accounts and no S3 proxy mode we measured. Kept only until the drill.
- **The OpenShift internal registry.** Fails the signature test (F1 of ADR-0611, WP-246).
- **Quay with the operator-managed database or ODF storage.** The owner chose PGO and AWS S3 (WP-248, decisions of 2026-11-11).
- **Quay as a pull-through mirror of `quay.io`.** Would pull from the same CDN on a miss and runs behind the EgressFirewall.
- **Open every Clair updater host.** Ten egress rules, each subject to the `dnsName` pool problem; rejected for now.

## Consequences

- One registry, one access model and one retention rule for every image; a pod start no longer depends on third-party CDNs.
- A heavier component (F3): about 13 Gi requested on demo333, a PGO cluster, an operator to pin and an S3 bucket to own.
- First AWS infrastructure as code in the repository (the `amazon.aws` collection).
- A registry outage blocks pod starts that need an image not on the node.

## Security considerations

Trust stays with digests and signatures (clause 5), so a modified registry yields a refused pod. The S3 key is scoped to
one bucket and kept in Vault; robot accounts have pull-only and push-only roles; ingress NetworkPolicies admit only the
consumers. Clair data for third-party images is absent by clause 4, stated rather than implied.

## Operational considerations

Backups of the PGO cluster follow the platform schedule; the bucket is rebuildable from the sources and is not backed up
separately. Re-measure the S3 and `quay.io` reachability after any firewall change. Every cluster change here needs the
owner's go.

## Work packages

[WP-248](../roadmap/work-packages/wp-248-replace-the-okf-mirror-with-an-internal-quay-for-every-zuno-image.md).

## Addendum 2026-11-12: consumer access, tag expiration and cut-over order

Decided by the owner after the canary and the first week of the live registry.

- **Access.** Pods reach the registry through its route, `quay-quay-zuno-registry.apps.demo333.startx.fr`. The Service
  address is not usable: its certificate carries the route name only (measured). The route certificate is the wildcard
  issued by Let's Encrypt, so no CA has to be distributed. Each consumer namespace needs the route host in its
  EgressFirewall and the router in its NetworkPolicy egress; the pull credential is the `zuno+pull` robot, read from
  Vault `zuno/registry/quay-robots`.
- **Tag expiration.** First-party images and UnifAI release images keep the five latest tags per repository; a tag
  referenced by digest in the repository is never removed. The OKF repositories keep three releases (clause 6). The
  mirrored public images (clause 7d) never expire: the list is closed and every entry is deliberate. Quay's own
  time-machine delay (about two weeks for untagged manifests) is left as it is, so a tag removed by mistake can be
  recovered.
- **Clair.** No vulnerability data on this cluster (owner decision, WP-248): the `rhel-vex` update never completes
  because the Akamai addresses of `security.access.redhat.com` alternate between reachable and blocked under the
  `dnsName` rule. Clause 4 is delivered in part: the scanner runs, its data does not load. Reopen with the two observed
  Akamai /24 ranges in the zuno-registry EgressFirewall if scanning becomes a requirement.
- **Cut-over order** (clause 8, a golden path before and after each step, never in a freeze): (a) the OKF release read by
  the two gateways, (c) the UnifAI release images, (b) first-party images, (d) public images, each from a list that
  `platform/supply-chain/mirrored-images.yaml` names. The zot drill closes the sequence.
