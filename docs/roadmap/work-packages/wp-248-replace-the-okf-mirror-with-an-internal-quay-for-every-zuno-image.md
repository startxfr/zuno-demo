# WP-248: Replace the OKF mirror with an internal Red Hat Quay that holds every zuno image

- **State:** Operator pending (2026-11-12): families (a) OKF release, (c) UnifAI images and (d) public images are live on demo333, the drill passed and the zot mirror is removed; left: family (b) first-party images and the retirement of the ImageStream registry (ADR-0612 clause 9, the owner's decision), and Clair vulnerability data (the owner chose to leave it without)
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

## Canary plan (decided 2026-11-11: rehearse in `zuno-registry` itself)

**Choice.** The canary is `zuno-registry`, the namespace the registry will really use. It is new, nothing depends on it, and the
Applications and egress rules already name it; a separate canary namespace would need the namespace made a parameter of both
Applications and of the firewall for one rehearsal. The rollback is `make d2 uninstall quay-registry` (the bucket stays).
Because nothing else lives there, this rehearsal is also the first install: if it passes, it stays.

**Before** (the owner's go for the window, and no other rehearsal window open): golden path 14/14 as the baseline; backup
point recorded; `git status` clean on the branch the Applications track; the namespaces Application synced so that
`zuno-registry` and its EgressFirewall exist (`make d2 install namespaces`, which also needs the go).

**Run**
1. `make d2 install quay-registry`: operator, `quay-db`, `QuayRegistry`, config bundle, bootstrap. Record the time to Available.
2. Check the open points of the prepared-in-repository section, in this order: pod label `quay-component: quay-app`;
   `clair-config.yaml` honoured (Clair indexes, no updater other than `rhel-vex` in its log); proxy storage (a pull returns blobs
   from Quay, never a 307 to S3); S3 objects appear under `registry/` in the bucket.
3. Seed: `OKF_MIRROR_TO=<route host>/zuno make d3 admit agents`, then `cosign` and `oras` re-verify by digest (as in step 1).
4. Pull as a pod: a throw-away pod in `zuno-ai-run` pulls with the `zuno+pull` robot; a `zuno-ai-build` push with `zuno+push`.
5. Retention: feed two more releases (or tags that mimic them), then `OKF_MIRROR_QUAY=1 make d3 admit agents` dry run, review,
   `OKF_MIRROR_PRUNE=1`; confirm the garbage collector removes the untagged manifests and that the kept releases still verify.
6. Restart test: delete the Quay application pod; the blobs and the pull must survive (the failure of the LocalStorage canary).
7. Clair: scan one Red Hat based image and one third-party image; record what each reports.
8. Public images: copy one entry of the future `mirrored-images.yaml` from where `quay.io` is reachable, digest unchanged.

**Pass** when steps 2 to 6 hold and the golden path is 14/14 after. **Record** the measured resources, the time to Available and
every deviation in this WP, add the `quay-operator` known-good entry from the installed CSV, then decide whether to keep the
registry running or `uninstall` it until step 5 of the WP starts.

**Not in this canary**: moving any consumer (gateways, builds, UnifAI) to the registry; the zot mirror stays untouched.

## Result of the canary (2026-11-11, `zuno-registry` itself, the owner's go)

Baseline golden path PASS before; `make d2 install quay-registry` installed `quay-operator` v3.18.3 (channel `stable-3.18`, the
version the catalog served today, 3.18.2 in the earlier canary), the PGO database, the `QuayRegistry` and the bootstrap. Twelve
minutes from the Application to `Available`, then about 20 minutes of fixes found by running it.

**Fixed in the repository during the run** (each one a commit): the role did not load the per-cluster variables; the
organisation email had to differ from the admin's, and "400 = exists" had hidden that, so the bootstrap now looks up before
creating (Quay answers 400 for a missing robot); the push robot needed a `creator` team to create repositories by pushing
(401 otherwise); the S3 `s3_region` was missing from the storage config (presigned URLs were signed for `us-east-1`, S3 answered
400 through the proxy); the operator ran two replicas of Quay and Clair, now one through `overrides.replicas`; the namespace
EgressFirewall lacked the registry's own route, which Clair uses to fetch layers; `prune` also had to drop the bare
referrers-index tag `sha256-<digest>` of a dropped artifact.

**Passed**
- `clair-config.yaml` from the config bundle is honoured: Clair logs `running updaters total=1` (`rhel-vex`) and no other host
  was contacted. The NetworkPolicy label `quay-component: quay-app` is right.
- Storage on the bucket with **proxy storage**: 57 objects under `datastorage/registry/`; every blob GET answers 302 to the
  registry's own `/_storage_proxy/...` path, never to S3.
- Seed: `make d3 admit agents` with the Quay prefix mirrored the nine artifacts and re-verified them from Quay with offline
  `cosign` and `oras`, same digest. The two older locked releases were fed too.
- A pod pulled `zuno/canary/fedora-minimal@sha256:f588...` from the route with the `zuno+pull` robot (6.7 s); the pull robot
  has read only, the push robot creates repositories.
- Restart: deleting the Quay application pod (and a rollout) lost nothing; the locked release verifies again afterwards.
- Retention with `OKF_MIRROR_QUAY=1`: `--keep 3` listed nothing, `--keep 2` listed exactly the oldest release's three tags, the
  apply removed them and the two kept releases still verify.

**Open or negative**
- **Untagged manifests are not collected at once.** After the tag deletion the oldest release's manifest was still fetchable by
  digest. Quay keeps deleted tags for its time-machine period (two weeks by default) before the garbage collector may drop the
  blobs, so the bucket does not shrink until then. If that matters, set the organisation's tag expiration (API
  `change-tag-expiration`); to be decided with the tag-expiration question.
- **Clair did not produce a report.** After the route rule was added, Clair fetched the layers, but Quay logged
  `Security scanner response failed OpenAPI validation` and the manifest status stayed 520 (and `unsupported` for the
  multi-arch index and for Fedora, as expected). It has to be told apart: our `rhel-vex`-only override against the default
  updaters. Not done: it needs the other updater hosts opened for a comparison run.
- **Pods cannot reach the registry by its Service.** The Service certificate is the cluster wildcard, so only the route host
  validates; a consumer namespace therefore needs the route host in its EgressFirewall (as `zuno-registry` now has) or a
  service-CA path. The kubelet pulls (node network) are not affected. To be decided before any consumer moves.
- The Quay application used 4.8 GiB at rest after the seed and is the only large pod; Clair 73 MiB, its database 131 MiB.
- `quay-operator` is in `platform/olm/known-good-demo333.yaml` (3.18.3). The admin and robot credentials are in Vault
  (`zuno/registry/quay-admin`, `zuno/registry/quay-robots`); the scratch copies used for this run are in the session scratchpad
  only (0600) and are deleted when the session ends.
- Still not done: Vault copy of the bucket key, PGO backup of `quay-db` in the Day 3 schedule, step 6 (public images) beyond the
  two test copies, and the cut-over of any consumer. The registry stays installed; the zot mirror is untouched.

## Prepared after the canary: Vault copy of the bucket key and quay-db backups

Repository only, nothing applied to the cluster yet.

- `roles/quay_registry/tasks/bootstrap.yml` seeds `zuno/registry/quay-bucket` (bucket, region, access key id and secret) on the first run. Until now the key lived only in `~/.config/zuno` on the workstation that ran `registry_bucket.yml`. The existing key is copied at the next `make d2 install quay-registry`, which needs the owner's go like every cluster write.
- The `quay-db` PostgresCluster now carries pgBackRest schedules on repo1 (full on Sunday, differential Monday to Saturday, 04:00 UTC, `database.backupSchedules`) and the `manual` block that PGO needs to honour the on-demand annotation.
- `make d3 backup quay-registry` (new `roles/quay_registry/tasks/backup.yml`, also in the `zuno-day3-backup` survey) runs an on-demand backup and waits for that exact run to succeed.
- Limits: repo1 is a PVC in the same cluster, so it covers a bad write or a lost database volume but not the loss of the cluster; the image blobs are in the S3 bucket and are not part of this backup; there is no restore drill yet.

## Clair without vulnerability data (owner decision, 2026-11-12)

Measured: the `rhel-vex` updater hits its 30 minute deadline on every run and the Clair `vuln` table stays empty, so Quay shows no vulnerability report. It is neither CPU nor database bound: the download of the 412 MB VEX archive stalls because the Akamai addresses of `security.access.redhat.com` alternate between reachable and blocked under the `dnsName` rule of the zuno-registry EgressFirewall (the same pool mismatch as the S3 copies). Reachable addresses download the archive in about 3.5 s.

Options put to the owner: add the two observed Akamai /24 ranges to the firewall; mirror the archive in the cluster and point `updaters.config.rhel-vex.url` at it; or leave Clair without data. **Decision: leave Clair without data.** The registry serves and signs images as intended, and scanning is not needed for the first consumer cut-over. Consequences to keep in mind:

- Quay's security column stays empty; do not read it as "no vulnerabilities".
- Clair keeps retrying every six hours and failing; it is harmless but noisy in its log.
- ADR-0612 clause 4 (Clair on, Red Hat sources only) is therefore only partly delivered. Reopen with the first option if scanning becomes a requirement.

## Plan for family (a): the gateways read the OKF release from Quay

Decisions are in the ADR-0612 addendum of 2026-11-12. Measured while planning: the route certificate is a public Let's Encrypt wildcard, so the `okf-fetch` image needs no extra CA; the init container has no registry credential today, so the robot pull secret is the new piece. Steps, each its own commit; the cluster steps need the owner's go and a window free of other agents:

1. Chart: `okf.fetch.mirror` in mcp-gateway and a2a-gateway gains an optional pull Secret mounted as `DOCKER_CONFIG`; the Secret is an ExternalSecret over Vault `zuno/registry/quay-robots` (`pull_username`, `pull_token`).
2. Network: route host in the `zuno-ai-run` EgressFirewall, router egress in its NetworkPolicy; checked by a pod-level pull, not by TCP probes.
3. Feeding: `make d3 admit agents` with `OKF_MIRROR_TO=<route>/zuno` using the `zuno+push` robot (already seeded), and `okf_mirror_holds_lock.yml` verifies through the route instead of the zot port-forward when the prefix is a Quay one.
4. Switch `zuno_okf_registry_mirror` to the Quay prefix with `plainHttp: false`, roll the gateways, golden path before and after, then pods started with quay.io blocked as the proof.
5. zot stays until the drill of clause 8.

## Result of family (a): the gateways read the OKF release from Quay (2026-11-12)

Live on demo333, owner's go, no other window open. Sequence: route egress for `zuno-ai-run` (pushed, synced by ArgoCD); `make d0 install vault` (configure Job applies the `registry/quay-pull` grant); `make d2 install quay-registry` (seeds `zuno/registry/quay-pull`, writes the workstation docker configs); the OKF release 0.14.3 mirrored to `quay-quay-zuno-registry.apps.demo333.startx.fr/zuno` and verified with the pull robot; golden path PASS; `make d2 install mcp` with `zuno_okf_registry_mirror` on Quay; golden path PASS (13 moments).

Proof: the `okf-fetch` init container of mcp-gateway and a2a-gateway both print `VERIFIED quay-quay-zuno-registry…/zuno/okf-corp@sha256:2918e463…: release 0.14.3, 8 agents` and neither log contains "falling back" or a failed attempt, so no pod went back to quay.io. Quay's access log shows the pulls.

Found on the way: the free-form shell string of `okf_mirror_holds_lock.yml` is split by Ansible, so an apostrophe in a comment broke the parse of `make d2 install mcp` for a few minutes (fixed in 4bda8185); and the readiness probe failed when one OLM list call returned no `resources` (now tolerated). Rollback to zot: restore the three previous values noted in `ansible/clusters/demo333.yml`. zot stays until the clause 8 drill; not tested yet: gateways starting with quay.io blocked.

## Family (c): the UnifAI images (owner decisions 2026-11-12)

Decisions: an `ImageDigestMirrorSet` sends the digest pulls of `quay.io/zuno/unifai-*` to the internal Quay (A); the repositories are publicly readable, so no credential reaches the nodes; `mirrorSourcePolicy: AllowContactingSource` (a node falls back to quay.io while Quay has one replica); the signature test stays partial until the question below is settled; the copy has the owner's go, the redirect needs a second go.

Done, live: `platform/supply-chain/mirror_unifai_images.py` verified the eight pinned digests at their source (signature, provenance, signed SBOM, ADR-0586 policy), copied them with their `.sig`, `.att`, `.sbom` tags and the SBOM's own signature, verified them again from the copy, and made the repositories public. The eight are the five application images, the operator, its bundle and its catalog (release 0.1.68). Anonymous `skopeo inspect` of three of them from the route answers. `pin_unifai_images.py --mirror-to <prefix>` runs the copy for the five images at pin time; the operator, bundle and catalog follow with `mirror_unifai_images.py --version X.Y.Z`.

Prepared, not applied: the IDMS template in the quay-registry chart (d0, platform project, committed `redirects.enabled: false`); the platform AppProject whitelist gains `config.openshift.io/ImageDigestMirrorSet` (applied with `make d0 install argocd`). The flip is one commit (`redirects.enabled: true` in `application-d0.yaml`) plus `make d2 install quay-registry`.

Measured on OpenShift 4.22.20: the Machine Config Operator's disruption policy for `/etc/containers/registries.conf` is `Special`, which is the no-drain, no-reboot path for mirror changes (CRI-O is reloaded). To be confirmed live on the first worker, with `oc get mcp` and node age unchanged.

Question 4 (the admission policy reads signatures on quay.io): the ClusterImagePolicy CRD has no mirror field, but each authority takes `source.oci`, a repository that holds the signatures. Signature tags are named by image digest, so one repository can hold the signatures of every image. Moving the policy there means copying the signatures of the eight digests into that repository and pointing the UnifAI authority at it; the policy-controller would then no longer need quay.io for UnifAI pods. Not done: it changes the admission policy, which is enforced for opted-in namespaces. Until then the quay.io-blocked test is partial for UnifAI pods (new pods in `zuno-unifai` and `unifai-operator` need quay.io for the signature check only).

## Result of family (c): the IDMS is live (2026-11-12, owner's second go)

Sequence: golden path PASS (13 moments); `make d0 install argocd` (platform AppProject admits `ImageDigestMirrorSet`); flip commit f700cab2; `make d2 install quay-registry`; ArgoCD created `zuno-unifai-via-registry` (eight repositories, `AllowContactingSource`); golden path PASS again.

The Machine Config Operator rolled the new rendered config through all seven nodes (3 masters, 4 workers) in a few minutes: a node check on every 6 s poll saw no node cordoned and none NotReady, node ages unchanged, so no drain and no reboot, as the `Special` disruption policy for `registries.conf` predicts. While it ran the pools showed Updating; both ended Updated (`rendered-master-032b713e…`, `rendered-worker-d737a4a2…`).

Proof of use: `kubectl rollout restart deploy/unifai-ui` pulled `quay.io/zuno/unifai-ui@sha256:f214c180…` (554 MB in 4.5 s, the pod references and the signature policy still say quay.io) and Quay's access log shows `GET /v2/zuno/unifai-ui/manifests/sha256:f214c180… 200`, anonymous.

Not proven: a pod start with quay.io blocked (the signature check still needs it, see question 4 above) and the fallback to quay.io when Quay is down. Rollback: set `redirects.enabled: false` in `gitops/apps/quay-registry/application-d0.yaml` and run `make d2 install quay-registry` (the nodes reload again).

## Result of family (d): the public third-party images (2026-11-12, owner's go for the copy and for the IDMS)

The closed list `platform/supply-chain/mirrored-images.yaml` (27 images read from live pods) is copied by `mirror_public_images.py`: the 20 digest-pinned entries (19 repositories, `mongo` carries two digests) are in Quay under `zuno/mirror/<path>`, all publicly readable, digests identical to the source. None of them carries a signature to copy. Docker Hub buildx indexes make Quay answer 404 on the referrers lookup (`temporalio/temporal`), so the tool passes `oras cp -r` only when a signature is expected, retries a failed copy up to three times (a ghcr.io blip stopped one run) and prints each image as it lands.

UnifAI 0.1.69 was copied the same way as 0.1.68 (8 digests, signatures verified at the source and from the copy).

`ImageDigestMirrorSet` `zuno-public-via-registry` (19 sources, `AllowContactingSource`) is live through `make d2 install quay-registry` (the d0 Application values live in the Application object, not in git; the role merges the manifest). The seven nodes reloaded without drain or reboot, golden path 13/13 before and after. A throwaway pod referencing `quay.io/oauth2-proxy/oauth2-proxy@sha256:8498b0d0…` pulled in 1.9 s and Quay's access log shows 16 requests on `mirror/oauth2-proxy`.

Not mirrored, by design: the seven tag-pinned images. `claw-operator`, `claw-proxy`, `nfs-provisioner-operator` and kagent's `golang-adk` are named by tag inside operator bundles or controller defaults that we cannot repin from our charts, and an IDMS only matches digests. `hashicorp/vault` is imported into an ImageStream (pods never pull it from Docker Hub). `istio-csr` and `python:3.12-slim` can be pinned in our own charts and tasks (next step). Rollback: `publicRedirects.enabled: false` in `gitops/apps/quay-registry/application-d0.yaml`, then `make d2 install quay-registry`.

## Result of the signature source and the second window (2026-11-12, owner's go)

The python and istio-csr entries of the closed list moved to digest pins and were copied; the IDMS `zuno-public-via-registry` now carries 21 sources (the nodes reloaded again, none cordoned, golden path 13/13 before and after). `istio-csr` is pinned by digest in `gitops/charts/service-mesh/values.yaml`; the service-mesh Application rolled its two pods once.

The UnifAI admission policy no longer reads signatures from quay.io. The policy-controller webhook accepts one `source` per authority (`only single source is supported`), so `gitops/charts/rhtas-config` renders one `ClusterImagePolicy` per repository, `zuno-unifai-images-<repository>`, with exact globs (`@*` and `:*`; `unifai-operator**` would also have caught the bundle and the catalog) and `source.oci` set to the repository in Quay. It is switched on by `zuno_unifai_signature_mirror_host` in `ansible/clusters/demo333.yml` and applied with `make d1 install rhtas-config`. Proof: a throwaway `warn` policy answered "no signatures found" with a wrong source (so the image's own repository is not consulted), the eight policies are `enforce` and Ready, the eight 0.1.69 digests and the five 0.1.68 digests are admitted by server dry-runs and a forged digest is refused.

**Consequence for every UnifAI pin:** the release must be copied into Quay (`mirror_unifai_images.py --version X`) before the pin is rolled, otherwise the signature check finds nothing and the pods are refused. Rollback: remove `zuno_unifai_signature_mirror_host` and run `make d1 install rhtas-config`.

Still open: the final drill (quay.io and docker.io blocked, a gateway, the UnifAI operator and a first-party component start, a forged digest refused), the fallback when Quay is down, and the retirement of zot.

## Drill and retirement of zot (2026-11-12, owner's go)

Proofs, in the order they were taken (window announced, golden path 13/13 before and after):

1. **Presence:** all 22 digest-pinned public images answer an anonymous `oras manifest fetch` on the Quay route with the expected digest.
2. **Served by Quay alone (nodes):** node image pulls cannot be filtered by a NetworkPolicy, an AdminNetworkPolicy or an EgressFirewall (CRI-O pulls on the host). The proof is a canary: the digest of `oauth2-proxy` copied into `zuno/mirror/library/nginx` (a digest that does not exist at `docker.io/library/nginx`), referenced as `docker.io/library/nginx@sha256:8498b0d0...`. A pod with `imagePullPolicy: Always` pulled and ran it in 0.4 s, so only Quay could have served it. The tag was deleted afterwards.
3. **quay.io blocked for the pods:** the `quay.io` and `cdn01..03.quay.io` rules were removed from the `zuno-ai-run` EgressFirewall (they existed only for okf-fetch, found live 2026-11-07). A pod of that namespace times out on quay.io and its CDN and reaches the Quay route. `mcp-gateway` and `a2a-gateway` were restarted: okf-fetch printed `VERIFIED .../zuno/okf-corp@sha256:2918e463... release 0.14.3, 8 agent(s)` from Quay.
4. **Fallback when Quay is down:** a temporary AdminNetworkPolicy (Deny ingress to the Quay app pods; the route answered 000 meanwhile) and a pod with `imagePullPolicy: Always` on `quay.io/oauth2-proxy/oauth2-proxy@sha256:8498b0d0...`: the node tried the mirror, then fell back to the source and pulled in 21 s. The policy and the pod were removed.
5. **Forged digest:** `docker.io/library/nginx@sha256:bbbb...` ends in `ErrImagePull`.
6. **UnifAI signatures:** the eight policies read Quay; a forged UnifAI digest is denied by the webhook (see the previous section).

Removal: `make d2 uninstall okf-mirror` (Application and PVC pruned), then the repository: chart `okf-mirror`, its Application, role `okf_mirror`, the Makefile, day2 playbook and AAP workflow entries, the hardening checker entry, the zot image in the mirrored list and in the IDMS, and the plain-HTTP port-forward branch of `okf_mirror_holds_lock.yml`. The owner asked for the removal as soon as these proofs existed, instead of after a week of use as ADR-0612 clause 8 first said.

## Incident of the zot removal: removing an IDMS source drains the nodes (2026-11-12)

Dropping the zot image from `publicRedirects.sources` (21 to 20 sources) was the one change of the evening that is not a pure addition. Adding sources reloads `registries.conf` without a drain (both earlier IDMS changes did); **removing one makes the MCO cordon and drain every node**, one by one: the four workers took about 50 minutes, and the last master stayed cordoned because its drain was blocked by the single-replica PodDisruptionBudgets (a2a-gateway, mcp-gateway, ai-gateway, Keycloak `zuno-0`; ADR-0101 accepts 31-65 s of outage there). With the owner's go the four pods were deleted, the drain passed and both pools reached Updated.

Consequences seen: the Quay application pod was rescheduled and stayed not Ready for more than an hour (its liveness probe, 10 failures at 15 s, kills it before the slow start ends), so for that time the gateways could not read the OKF release and fell back to quay.io, which the EgressFirewall now denies (`Init:Error`); the gateways recovered by themselves once Quay was Ready (pods deleted to retry), UnifAI multiagent needed its two pods recreated (`failed to prepare subPath` after the move).

Second consequence, found after the nodes were back: `kuadrant-operator-controller-manager` had been rescheduled by the first drain and crash-looped for about two hours on its start-up ("waiting for CRDs for dns-operator: CRD dnshealthcheckprobes.kuadrant.io not established within 30s", the CRD itself was Established and the RBAC fine, the 30 s wait lost against the loaded API), so the Service `kuadrant-operator-wasm` had no endpoint, the Kuadrant wasm-shim could not be fetched and **failed closed in the MaaS gateway: HTTP 503 on every MaaS route, with or without a token** (golden path `lightspeed` and `blender` red). The operator started on its own at the 18th attempt; the gateway pods had to be recreated afterwards (a wasm fetch that exhausted its retries is not retried), and Authorino was recreated too (its first answers were `UNAVAILABLE`). With the owner's go (option 1) the Authorino and MaaS gateway pods were deleted; golden path 13/13 afterwards.

Rule for next time: batch every IDMS source removal into one change, announce a window of at least two hours, expect a Quay outage of the duration of the drain, and after the drain check `oc get ep -n openshift-operators kuadrant-operator-wasm` and recreate the MaaS gateway pod if the operator was down; consider a startup probe on the Quay application pod.

**Owner decision, 2026-11-13: Quay keeps one replica and no probe change (option A).** The Quay operator already defines a startup probe (10 failures at 15 s, 150 s) and `QuayRegistry` does not expose probes, so the long outage after the drain was a start slower than 150 s under load, not a missing probe. Two replicas (`overrides.replicas: 2`, 8 Gi and 2 CPU each) were declined: the 2026-11-11 decision of no HA stands. What protects the next occurrence is the rule above (no IDMS source removal without a window of at least two hours) and `make d3 check recovery`, which reports "Quay not Ready" first; recreating the Quay application pod breaks the restart loop.

**The workstation copy of the bucket key is gone (2026-11-13).** `~/.config/zuno/zuno-demo333-registry-key.json` was deleted with the owner's go; Vault `registry/quay-bucket` holds the copy. `roles/quay_registry` read the file to build the config bundle and refused to run without it, so it now falls back to Vault when the file is missing (`bucket_key_from_vault.yml`); proven by a `make d2 install quay-registry` run with the file moved aside (ok=130, failed=0). Creating or rotating the key still goes through `registry_bucket.yml`, which writes the file again.

## Restore test of quay-db (2026-11-13, owner's go)

Question: can the `quay-db` backups be restored? The pgBackRest repository is a PVC in the same cluster (`quay-db-repo1`, 5 Gi), with a full backup of 2026-11-11 and an incremental of 2026-11-12, and the WAL archive.

Method: a clone `quay-db-restore-test` (`PostgresCluster`, `dataSource.postgresCluster: quay-db / repo1`, 2 Gi volumes, same namespace; PGO reads the source repository and never writes to it). Result: the restore Job finished in about 100 s, PostgreSQL recovered its timeline and shut down cleanly, the instance started (`PostgresDataInitialized=True, PGBackRestRestoreComplete`) and answered. Compared with the live database, taken within the same minute: users 4, repositories 38, manifests 275, tags 562, blobs 1022, organizations 1, robots 2, and the md5 of the repository list, of the tag list and of the user list are identical, the pushes of the previous evening included (WAL replay reached the latest archived segment). The clone and its volumes were deleted afterwards.

Not proven: a restore after losing the repository PVC or the cluster. The repository is a volume of the same cluster, so this test proves the backups are readable and complete, not that they survive a cluster loss. An S3 repository (`repo2` on the registry bucket or another) is the follow-up if that matters; the `quay-db` is 40 MB.

Observed while it ran: the clone waited for the PGO operator (`openshift-operators/pgo`), which was crash-looping with the other operators of the cluster after the node drains of the evening (liveness probe of 1 s, leader election lost on API timeouts, etcd applies slightly above 200 ms); it recovered by itself within the hour and the restore went through.

