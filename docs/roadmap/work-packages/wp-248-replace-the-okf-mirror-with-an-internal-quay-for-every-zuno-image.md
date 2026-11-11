# WP-248: Replace the OKF mirror with an internal Red Hat Quay that holds every zuno image

- **State:** Not started (the owner's decisions of 2026-11-11 are recorded below; step 1 can start with his go)
- **ADRs:** [ADR-0612](../../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md) (the decision, Accepted 2026-11-11), [ADR-0611](../../adr/0611-mirror-the-admitted-okf-release-into-the-internal-registry.md) (its registry choice is
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
2. **Decision record** ([ADR-0612](../../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md), written 2026-11-11). A new ADR (Proposed, then Accepted after step 1) that replaces the registry choice of ADR-0611
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

## Result of step 1 (2026-11-11, canary `zuno-canary-wp-248`, the owner's go)

`quay-operator` v3.18.2 (channel `stable-3.18`, OwnNamespace in the canary), a `QuayRegistry` with PostgreSQL, object storage,
autoscaler, mirror and monitoring unmanaged, and Clair, its database, Redis, route and TLS (cluster wildcard certificate)
managed. The database is a separate PGO `PostgresCluster` (PostgreSQL 15, one instance). Storage is `LocalStorage` on the
pod's volume: the S3 bucket of step 3 does not exist yet.

**What passed**

- **The OKF release and its signatures.** `admit_okf_bundle.py mirror --to <quay>/zuno` copied the corp artifact and the 8
  agent artifacts (release 0.14.3, same digest `2918e463…`) and verified them again from Quay with offline `cosign` and
  `oras`. The `release-*`, `.sig` and `.att` tags survived. Quay answers the OCI Referrers API (HTTP 200 with the manifest
  list). Where the OpenShift internal registry failed this gate (WP-246 step 1), Quay passes.
- **The database.** Quay runs and migrates on a PGO instance with `sslmode=require`, once `databaseInitSQL` has created
  `pg_trgm` in the `quay` database (the repository's `\connect` pattern). The `DB_URI` password must be URL-encoded: PGO
  passwords carry `;`, `>`, `(` and `*`, and the unencoded form crashed the first start (`invalid userinfo`).

**What the measurement changed**

- **Deleting needs Quay's API.** `oras manifest delete` is refused (Quay's registry token does not accept the `delete`
  scope: "Unable to decode repository and actions"). Tags are deleted through `DELETE /api/v1/repository/<org>/<repo>/tag/<tag>`
  (HTTP 204, the API then lists no active tag; the `/v2` tag list still showed them a few seconds later) and Quay's garbage
  collector removes the untagged manifests. The retention of ADR-0611 therefore needs a Quay variant of `prune` that holds an
  API token, not `oras`.
- **Size.** Defaults per pod: Quay application 2 CPU and 8 Gi (request equals limit), Clair 2 CPU / 2 Gi request / 16 Gi
  limit, Clair database 500m / 2 Gi, Redis 500m / 1 Gi / 16 Gi limit; about 5 CPU and 13 Gi requested for one replica of each,
  before the database. The Quay application used 4.2 Gi after pushing nine artifacts, and a 4 Gi limit made it fail its
  liveness probe and restart: do not shrink it. Clair, its database, Redis and the operator were each under 120 Mi at rest.
  For comparison the zot mirror is one small pod.
- **Storage must be object storage.** With `LocalStorage` on the pod's volume, a pod restart lost the blobs while the
  database kept the metadata: pushes then failed with `Unknown blob` and reads with 502. The S3 bucket of step 3 is a
  prerequisite for a stable registry; `FEATURE_PROXY_STORAGE` is set but not exercised (it only matters with S3).
- **The shared PostgreSQL does not fit as is.** The platform's `zuno-data/zuno-postgresql` runs PostgreSQL 18 with three
  replicas; Quay documents PostgreSQL 15. Use a small dedicated `PostgresCluster` (PGO, as decided) unless Quay's support for
  18 is confirmed.
- **Clair needs the internet.** Its updaters tried `linux.oracle.com`, `security.access.redhat.com`, `secdb.alpinelinux.org`,
  `packages.vmware.com`, `ftp.suse.com`, `cdn.amazonlinux.com`, `repo.us-west-2.amazonaws.com`, `nvd.nist.gov`, `deb.debian.org`,
  `api.launchpad.net` and `pkg.go.dev`, all blocked by the canary's default-deny. Under the platform's EgressFirewall each is a
  `dnsName` rule, with the CDN stall risk measured on 2026-11-09. The new ADR decides whether Clair runs only the Red Hat
  matchers (one host) or all of them.
- **The operator brings no NetworkPolicy** (the `QuayRegistry` of 3.18.2 has no such component): the registry's ingress and
  egress policies stay in the repository.
- **Canary friction, for the next canary.** The canary's ResourceQuota requires limits on every pod, and the operator's own pod
  sets none: a `LimitRange` with a default limit is needed. The default sizes above exceed the 4 CPU / 8 Gi default quota
  (raised to 10 CPU / 20 Gi requested for this run). A default-deny policy also blocks the operators' calls to the API server:
  an egress rule to the API service and its 6443 endpoints, and an ingress rule from the router, were added.

**Not rehearsed**: S3 storage and proxy mode, a robot-account pull from a pod through the mesh, a Clair scan of an image,
the public-image copy of step 6, and the first-party and UnifAI families. The canary is kept until the owner decides to remove it.

**Inventory of image references running on demo333 (containers by registry, 2026-11-11).** In scope: the in-cluster registry
(163, first-party builds), `quay.io/zuno` (18: UnifAI, OKF, signer), and the third-party images of the zuno charts:
`docker.io` (library 18, hashicorp 15, langgenius 6), `public.ecr.aws/aws-cli` (10), `ghcr.io/openclaw` (8), `nvcr.io/nvidia`
(41), plus a few public `quay.io` images (fedora, docling). Out of scope: the OpenShift release images
(`quay.io/openshift-release-dev`, 855) and the Red Hat operator and product images (`registry.redhat.io`,
`registry.connect.redhat.com`), which the cluster pulls with its own pull secret.

## Decisions of the owner (2026-11-11) and open questions

Decided:

- **Entitlement:** a Quay subscription is available for demo333, so the WP does not stop at step 1.
- **Database:** the existing PGO operator hosts Quay's PostgreSQL (declared as an unmanaged component of the
  `QuayRegistry`), so its backups and the CA trust rules of the PGO instances apply; the operator-managed database is not used.
- **Object storage:** the AWS bucket of step 3 (not ODF).
- **Vulnerability scanning:** Clair is on from the start; its database also runs on PGO unless step 1 shows it cannot.
- **Availability:** no high availability, a single replica of each component (the platform's single-replica rule, ADR-0101).
  The consequence is accepted on purpose: the registry is on the pod-start path, so a registry outage blocks pod
  starts that need an image not yet on the node. The `quay.io` second source and the zot mirror (until retired) soften it.

Open, to be decided in the new ADR:

- Tag expiration and garbage collection, so that the bucket does not grow without bound: **to be defined after** the first
  seeding, when the real volume is known.
- Which public `quay.io` images are mirrored (the first list comes out of the step 1 inventory).
- Whether the in-cluster ImageStream registry is kept for builds or retired once builds push to Quay.
- Clair's resource cost on demo333 and whether its updater needs an egress rule (it fetches vulnerability data from the
  internet; the EgressFirewall must allow only what step 1 measures).

## Acceptance

With `quay.io` blocked, a gateway pod, the UnifAI operator pod and a first-party component reach Ready from the internal
Quay; a forged digest is refused; every image the charts reference is on the internal registry or on the declared exception
list; the bucket was created by Ansible, scoped to its own IAM user; the zot mirror is removed; the golden path passes 14
of 14; no CDN or S3 range wider than the measured need was added to an EgressFirewall.

## Result of step 3 (2026-11-11, the owner's go for the AWS write)

`ansible-playbook ansible/playbooks/registry_bucket.yml -e registry_bucket_apply=true` (role `registry_bucket`, workstation
only; without the flag it prints the plan and writes nothing). It created, in `eu-central-1` of the account's default
profile: the bucket `zuno-demo333-registry` (all four public-access blocks on, default encryption AES256, no versioning),
the IAM user `zuno-demo333-registry` with one inline policy limited to that bucket (list, get, put, delete, multipart),
and one access key. A second run changes nothing. Deviations from the step text: the role calls the `aws` CLI instead of
`amazon.aws` (the module needs `boto3` on the controller, absent here; four idempotent calls did not justify a new Python
dependency), and the key is written once to `~/.config/zuno/zuno-demo333-registry-key.json` (0600, outside the
repository) because AWS never shows the secret again; the `quay_registry` role (step 4) moves it to Vault. The firewall
CIDRs for S3 and the canary S3 test come with that role. The step-1 canary was deleted on the owner's order; the S3 test
will run in a later canary together with other changes.

## Prepared in the repository (2026-11-11, steps 4 and the namespace part of 3; nothing applied to the cluster)

Done on the owner's order, to be rehearsed with the S3 test in the next canary ([ADR-0609](../../adr/0609-rehearse-on-canary-namespaces-of-demo333.md)):

- **Chart `gitops/charts/quay-registry`** and Applications `zuno-quay-registry-d0` (operator: OperatorGroup + Subscription through
  the vendored `operator` chart) and `-d1` (dedicated PGO `PostgresCluster` on PostgreSQL 15 with the `pg_trgm` init script,
  `QuayRegistry` with postgres, objectstorage, autoscaler, mirror and monitoring unmanaged, a NetworkPolicy for the consumers).
  The `QuayRegistry` carries `SkipDryRunOnMissingResource`, its CRD coming with the operator.
- **Role `quay_registry`** (`make d2 install|check|uninstall quay-registry`, placed before `okf-mirror` in the Day 2 order, the
  AAP install and check graphs, and the survey lists): resolves the operator package, applies d0 then d1, waits for PGO's
  `quay-db-pguser-quay` Secret, builds the `quay-config-bundle` Secret (URL-encoded `DB_URI`, S3 storage on the bucket with
  proxy storage on, the key read from the 0600 key file) and waits for `Available`. Uninstall deletes the `QuayRegistry` before
  the operator (the canary namespace stuck otherwise) and never touches the bucket.
- **Namespace `zuno-registry`** in the namespaces chart, not meshed, with an EgressFirewall: the API server,
  `security.access.redhat.com`, the S3 names and the 21 published `eu-central-1` S3 ranges (syncToken 1794413225).
- Checks run: `helm template` of both charts, `ansible-playbook --syntax-check`, `ansible-lint` (only the repository's usual
  casing and prefix findings), the config-bundle expression rendered with a fake password, `check_mesh_mtls.py` 545/0,
  `check_docs.py`.

**To verify in the canary** (written from documentation, never run): the pod label `quay-component: quay-app` used by the
NetworkPolicy; that the operator merges a `clair-config.yaml` holding only `updaters.sets: [rhel-vex]` from the config
bundle (if it requires a complete file, the Clair restriction moves to the egress side alone); proxy storage with S3; whether
`FEATURE_USER_INITIALIZE` plus the first `quayadmin` call can be scripted for the organisation and robot accounts (step 4,
second half, not written yet); the known-good entry for `quay-operator` (the version is only known after the first install).
Also still to do: the Quay variant of `prune`, the Vault copy of the bucket key, and the PGO backup of `quay-db` into the
Day 3 schedule.

### Added the same day, for the canary

- **Quay variant of `prune`** (`admit_okf_bundle.py prune --quay`, `OKF_MIRROR_QUAY=1 make d3 admit agents`): same kept set
  (last three locked releases, read through the registry protocol), but tags are listed and deleted through the Quay API
  with the OAuth token in `QUAY_API_TOKEN`; Quay's garbage collector removes the untagged manifests. Dry run by default;
  4 new tests (42 pass). Not rehearsed: whether the untagged referrer manifests of a deleted `.sig` / `.att` tag are
  collected, and that the API's `manifest_digest` equals the digest the kept set holds (to be measured against the canary).
- **Bootstrap** (`roles/quay_registry/tasks/bootstrap.yml`, run at the end of install): `POST /api/v1/user/initialize` once
  (first admin `quayadmin`, a generated password, an OAuth token), the organisation `zuno`, the robots `zuno+pull` and
  `zuno+push`, and default permissions (read and write) so the robots reach every repository created later. The admin
  record goes to Vault `zuno/registry/quay-admin` and the robot tokens to `zuno/registry/quay-robots`, written only when missing.
- Still open before the canary: the Vault copy of the bucket key (the config bundle reads the 0600 key file for now), the
  PGO backup of `quay-db` in the Day 3 schedule, the `quay-operator` known-good entry (version known after the first
  install), and whether the canary uses a separate namespace (the Applications and the egress rules name `zuno-registry`)
  or `zuno-registry` itself, which nothing else uses yet.
