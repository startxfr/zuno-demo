# ADR-0586: Verify the UnifAI runtime images by digest, signature and attestations before deploying them

- **Status:** Proposed
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
   provenance and an SBOM as attestations. The trust model is the one of ADR-0578 (offline verification against
   the committed Sigstore trusted root), applied to images built outside the cluster; RHTAS stays the mechanism
   for images built inside it (ADR-0535). The images are no longer built or pushed by hand for any cluster that
   verifies them (`make images-devel` stays for local development and yields unsigned images).
2. **Identities are written in one file,** `platform/supply-chain/image-identities.yaml`: the publish workflow
   on a `vX.Y.Z` tag (a release) and on the `devel` branch (a development build); the operator release workflow
   on an `operator-vX.Y.Z` tag (no development identity). A cluster accepts the `devel` identity only if its
   own variables say so (`zuno_unifai_accept_dev_signatures`): demo333 does, a production cluster does not.
3. **Three proofs per image.** A signature by an accepted identity, a provenance attestation and an SBOM
   attestation signed by the same identity. A missing one refuses the image.
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
8. **Admission by the cluster is a later step,** not part of this record. OpenShift's `ClusterImagePolicy`
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

## Security considerations

The signature proves which workflow, on which ref, built the digest; it does not prove the code is safe. A
compromised `devel` branch of the fork produces correctly signed images, so the development identity is only as
strong as that branch's protections (no force-push, reviewed merges) and is accepted only where the cluster opts in.
A production cluster takes release tags only. The verification trusts the committed Sigstore root (no network
trust), the registry is read but never trusted, and a verification that cannot run refuses.

## Before Implemented

On demo333, once the first CI-built images exist: the verifier refuses the current unsigned
`unifai-ui:devel-1bb72a84d` and accepts the CI-built digests; the stack applies only with verified, digest-pinned
images; pointing `images.ui` at an unsigned image makes the run refuse before applying anything; and `make d1
check unifai` fails for a pod started with another image. The operator, bundle and catalog follow with their first
signed release.

## Review evidence

Chart, role and cluster files of zuno-demo; the fork's `Makefile`, `fork/images.yaml`, workflows and operator
`plan.go` (images, `splitTag`, third-party defaults); ADR-0353, 0535, 0574, 0578; OpenShift release notes for
`ClusterImagePolicy`, read on 2026-10-24.
