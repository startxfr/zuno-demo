# ADR-0586: Verify the UnifAI runtime images by digest, signature and attestations before deploying them

- **Status:** Implemented
- **Target:** v0.11
- **Date:** 2026-10-24
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0353](0353-source-runtime-images-by-family-internal-registry-or-quay-io-zuno.md), [ADR-0574](0574-deploy-unifai-through-argocd-from-a-pinned-olm-catalog.md), [ADR-0578](0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0535](0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md), [ADR-0549](0549-close-the-secnumcloud-supply-chain-gap-with-an-in-cluster-release-ledger.md), [ADR-0575](0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)

## Context

ADR-0353 split the images by family and left one gap in writing: the UnifAI runtime images are pinned by
reference but not signature-verified by this platform, while the OKF artifacts are verified by identity
(ADR-0578) and the first-party images built in the cluster are signed and verified through RHTAS (ADR-0535).

The state found on 2026-10-24:

- The five application images (`quay.io/zuno/unifai-{rag,multiagent,backend,identity,ui}`) are built from the
  fork (`startxfr/UnifAI`) by `make` on a person's machine and pushed by hand. No workflow signs them or produces
  an SBOM or a provenance. demo333 references them by tag (`devel-<sha>`), not by digest.
- The operator, its bundle and its catalog are published by a release workflow that does not sign them. The
  catalog is pinned by digest in the chart, which makes it immutable but not verified.
- Nothing in zuno-demo covers these images: `verify_signatures.py` reads the internal registry; the Sigstore
  `policy-controller` is deployed but inactive (its unconditional "referenced by digest" gate rejects pods that
  use tags, ADR-0535).
- The images carry users' tokens (the multi-agent service forwards them to the gateways), talk to Keycloak and to
  the MaaS path, and the operator runs with cluster-wide rights. Whoever can push to `quay.io/zuno` can replace
  the image behind a tag and nothing detects it.

## Decision

1. **The fork builds and signs in CI; zuno verifies.** A GitHub Actions workflow of the fork builds the five
   images, pushes them, signs each digest keyless with the workflow's GitHub OIDC identity, and attaches a build
   provenance as an attestation and publishes the SBOM as a signed artifact (clause 3). The trust model is the one of ADR-0578 (offline verification against
   the committed Sigstore trusted root), applied to images built outside the cluster; RHTAS stays the mechanism
   for images built inside it (ADR-0535). The images are no longer built or pushed by hand for any cluster that
   verifies them (`make images-devel` stays for local development and yields unsigned images).
2. **Identities are written in one file,** `platform/supply-chain/image-identities.yaml`: the publish workflow
   on a `vX.Y.Z` tag (a release) and on the `devel` branch (a development build); the operator release workflow
   on an `operator-vX.Y.Z` tag (no development identity). A cluster accepts the `devel` identity only if its
   own variables say so (`zuno_unifai_accept_dev_signatures`): demo333 does, a production cluster does not.
3. **Three proofs per image.** A signature by an accepted identity, a provenance attestation and a signed SBOM
   artifact by the same identity. A missing one refuses the image. The SBOM is not an attestation: the first CI
   run (2026-10-25) showed a 25 MB SPDX document for `unifai-backend`, which the public Rekor log rejects
   (provenance, 971 bytes, was accepted). The fork pushes it as its own OCI artifact tagged
   `sha256-<image digest>.sbom` and signs that artifact; the verifier derives the tag from the pinned digest.
4. **Pinned by digest, per cluster.** Every UnifAI image a cluster verifies is written `repo@sha256:...` in
   `ansible/clusters/<cluster>.yml`. A tag is refused as unpinned. `check_unifai_pins.py` fails in CI for a
   cluster that verifies without pinning, and reports a cluster that switched verification off.
5. **Verified at deployment, fail-closed.** The `unifai` role runs `verify_unifai_images.py` before it applies
   the stack (the five application images) and before it applies the operator (the catalog image); a failure
   stops the run with nothing applied. Verification of the stack is on by default
   (`zuno_unifai_verify_images`); a cluster that must turn it off says so in its own file, with the reason.
   Verification of the catalog is a separate switch (`zuno_unifai_verify_catalog`), off until the operator release
   workflow signs its images.
6. **What runs is checked too.** `make d1 check unifai` reads the pods' `imageID`, compares every running
   application image to the pinned digests (drift) and verifies the signature and attestations of every running
   UnifAI image, the operator included once its switch is on.
7. **Third-party images are pinned, not signed.** MongoDB, Qdrant, RabbitMQ, Redis, Temporal, docling and the
   embedding image are written by digest in the cluster file. Their publishers do not sign them, so this is a
   pin and not a proof of origin, and the record says so. The RabbitMQ image comes from `bitnamilegacy`, a
   repository that receives no more updates; replacing it is a separate decision.
   *Applied 2026-10-25 on demo333:* the seven services the stack runs are pinned (the manifest list of the tag
   that ran, so the image does not change), `temporal` leaves `latest`, and `check_unifai_pins.py` requires them
   while verification is on. Not covered: the `aws-cli` image of the two backup CronJobs, which the operator sets
   outside `spec.images`, and `embedding`, which this cluster does not run.
   *Update 2026-10-25:* the backup Jobs' two images are pinned too (`stack.backup.images.awsCli` and `.mongo`, operator
   0.1.36 takes them verbatim), and `make d2 check unifai` compares what runs to every third-party pin from the pod spec
   (the runtime reports the platform manifest digest for a pinned manifest list, never the pin). The RabbitMQ image stays
   `bitnamilegacy`, frozen: its chart is the vendored Bitnami one, so replacing the image means rewriting an upstream
   chart; the user accepts that residual risk (2026-10-25).
8. **Admission by the cluster is a later step,** not part of this record (WP-178, 2026-10-25).
   *Update 2026-10-25:* WP-178 runs it on demo333 in `warn` mode with the Sigstore policy-controller (offline public-Sigstore TrustRoot, the
   identities of `image-identities.yaml`, `no-match-policy: warn` for the unsigned third-party services). *Update 2026-10-25 (WP-178 Done):* `zuno-unifai-images` is in
   `enforce` on demo333 (an unsigned UnifAI image is refused at admission in `zuno-unifai` and `unifai-operator`; the third-party services stay `warn`); the pin scripts run an
   admission preflight; the webhook stays fail-open (`failurePolicy: Ignore`), so it is the second guard after zuno's verifier and drift check. OpenShift's `ClusterImagePolicy`
   (`config.openshift.io/v1`, generally available since 4.20) verifies at pull and has no "digest only" rule
   like `policy-controller`, but it matches a keyless signer by e-mail, which a GitHub workflow identity is not;
   the choice between a public-key policy and keyless needs `oc explain` on the live cluster first.

## Alternatives considered

- **Pin by digest only:** detects drift after the pin, proves nothing about where the image came from. Kept as
  the first step (decision 4), not as the end state.
- **Import the images into the internal registry and sign them there with `zuno-signer`:** reuses the existing
  machinery, but the signature says "zuno accepted this digest", not "this workflow built it from this commit".
  Rejected for the application images; a candidate for third-party images if they ever need a signature.
- **Enforce at admission now (`policy-controller` or `ClusterImagePolicy`):** the first rejects tag-referenced pods,
  the second cannot express a workflow identity by e-mail and has no audit mode. Deferred (decision 8).
- **Verify only in CI:** CI cannot reach the clusters' pins or see what runs.

## Consequences

- The fork gains a workflow (`publish-images.yml`) and a GitHub environment `quay-devel` without approval for
  `devel` builds; releases keep `quay-release` with its approval. Both are the fork owner's to merge and create.
- demo333 stops following `devel-<sha>` by tag: a deployment is a commit that changes five digests, verified.
- The operator must render an image given by digest explicitly: `splitTag` handles `repo@sha256:...` only by
  accident today (it also leaks the bare hex where a chart reads the tag as a version). That fix is the operator
  owner's and comes before any pin is written.
- Images pushed by hand (`make images-devel`) cannot be pinned on a cluster that verifies.

## Residual risks (2026-10-25)

- **Unsigned operator releases.** Operator 0.1.36 to 0.1.38 (and the catalog the d0 chart pins, 0.1.30) are unsigned and are not
  re-cut: the first signed release is the first one after the operator image is built and signed in CI (`publish-images.yml`
  on `devel`, the release workflow retags that digest without rebuilding and the CSV references it by digest) and the
  bundle and catalog are signed. `zuno_unifai_verify_catalog` stays false until then.
- **Operator identity.** The operator image is signed by the `devel` identity of `publish-images.yml`, also when it is released
  (`vX.Y.Z` is that same digest). A cluster that does not accept the development identity needs the release workflow to
  add its own signature on the digest; written in WP-176 step 6.
- **RabbitMQ and the third-party services** are pinned, not signed, and RabbitMQ is frozen (decision 7).
- **No admission at the cluster:** a manifest applied outside the role is not refused until WP-178.

## Security considerations

The signature proves which workflow, on which ref, built the digest; it does not prove the code is safe. A
compromised `devel` branch of the fork produces correctly signed images, so the development identity is only as
strong as that branch's protections (no force-push, reviewed merges) and is accepted only where the cluster opts in.
A production cluster takes release tags only. The verification trusts the committed Sigstore root (no network
trust), the registry is read but never trusted, and a verification that cannot run refuses.

## Implementation evidence (2026-10-25, demo333)

- The verifier refuses the unsigned `unifai-ui:devel-1bb72a84d` (a tag, and its digest `sha256:0b851c4f...` has "no
  signatures found") and accepts the CI-built digests; the five application images are pinned by digest, verified by
  `make d2 install unifai` and deployed; the third-party services and the backup Jobs' images are pinned by digest.
- Pointing `images.ui` at the unsigned digest makes the role stop before applying anything ("The stack images do not
  verify (ADR-0586), nothing was applied").
- `make d2 check unifai` (not `d1`: `unifai` is a Day 2 component) failed on the pods that ran other images before the
  pins were applied, and flags a third-party pod running another image than its pin.
- The release path ran: `v0.0.0-rc1` built and signed the five images under `quay-release`, accepted WITHOUT
  `--accept-dev`. Operator 0.1.39 and 0.1.40 (operator, bundle, catalog) verify with the operator release workflow's
  identity; the catalog digest is pinned in the d0 chart and the hand-applied CatalogSource runs it (checked by the drift
  check). Residual risks are listed above; cluster-side admission is WP-178.

## Review evidence

Chart, role and cluster files of zuno-demo; the fork's `Makefile`, `fork/images.yaml`, workflows and operator
`plan.go` (images, `splitTag`, third-party defaults); ADR-0353, 0535, 0574, 0578; OpenShift release notes for
`ClusterImagePolicy`, read on 2026-10-24.
