# WP-176: Verify the UnifAI runtime images before deploying them

- **State:** Repo work merged
- **ADRs:** [ADR-0586](../../adr/0586-verify-the-unifai-runtime-images-by-digest-signature-and-attestations-before-deploying-them.md), [ADR-0353](../../adr/0353-source-runtime-images-by-family-internal-registry-or-quay-io-zuno.md), [ADR-0574](../../adr/0574-deploy-unifai-through-argocd-from-a-pinned-olm-catalog.md)
- **Depends on:** none
- **Related:** [WP-151](wp-151-deploy-unifai-on-zuno-via-argocd.md), [WP-173](wp-173-unifai-a2a-identity-server-and-approval.md)
- **Target:** v0.11
- **Estimated files touched:** ~14 in `zuno-demo` (verifier, identities, pins check, four role task files, `lint.yml`, `demo333.yml`, docs) and ~2 in the UnifAI fork (a build and signing workflow on a branch, then the operator release workflow)

> Decision of 2026-10-24 (user, option B): the fork builds and signs in CI (keyless GitHub OIDC, provenance and SBOM),
> zuno verifies at deployment and checks what runs; third-party images are pinned by digest, not signed. Fail-closed
> from the first run, with an explicit switch while the first signed images do not exist.

## Goal

No UnifAI image runs on a cluster that verifies unless it is pinned by digest and signed, with its provenance and SBOM,
by the fork's build workflow.

## Steps

1. **zuno-demo (done).** `platform/supply-chain/verify_unifai_images.py` (offline cosign, digest required, three proofs, `--pods` for drift), `image-identities.yaml`,
   `check_unifai_pins.py`, the role tasks `verify_images.yml`, `verify_images_refs.yml`, `verify_running.yml`, `verify_running_compare.yml`, their wiring in
   `install.yml` (before the d0 and the d1) and `check.yml`, the CI step, and 28 unit tests plus a task test against a stub verifier. `demo333.yml` carries
   `zuno_unifai_verify_images: false` and `zuno_unifai_verify_catalog: false` explicitly until steps 4 and 6.
2. **Fork branch.** `.github/workflows/publish-images.yml` on a branch of `startxfr/UnifAI`: matrix of the five components with the `Makefile`'s Dockerfiles and
   arguments, push `:devel-<sha>` or `:vX.Y.Z`, `cosign sign` of the digest, `cosign attest` provenance and SBOM, environment `quay-devel` for `devel` and `quay-release` for tags,
   path filters, manual dispatch, and an entry in `fork/fork-only-paths`. For the fork owner to review and merge.
3. **First signed build.** The owner creates the GitHub environment `quay-devel` (branch `devel`, the quay robot's secrets, write on `unifai-*`). A push to `devel` builds
   and signs. By hand: the verifier refuses the current `unifai-ui:devel-1bb72a84d` and accepts the CI-built digests.
4. **Switch on, in one commit.** The five digests in `demo333.yml`, `zuno_unifai_verify_images: true`, `zuno_unifai_accept_dev_signatures: true`. Waits for the operator to render
   a digest explicitly (the operator owner announces the version).
5. **Third-party images** by digest in `demo333.yml` (databases, queues, docling, embedding), with the note that they are unsigned. Decide separately what replaces `bitnamilegacy`. **Done 2026-10-25** (repo): seven services pinned in `demo333.yml`, required by `check_unifai_pins.py`; the `aws-cli` image of the backup CronJobs is not in `spec.images` and stays on its tag (operator side).
6. **The operator, bundle and catalog.** (a) a9, on a fork branch: the operator image is built and signed in CI (`publish-images.yml` on `devel`, identity `refs/heads/devel`), the canary deploys that digest, the release retags it without rebuilding and the CSV references it by digest. (b) zuno-demo, on a fork branch based on a9's (`feat/signed-bundle-catalog`): `unifai-operator-release.yml` signs the bundle and the catalog, attests their provenance, publishes their SBOM as a signed artifact, and adds the release identity's own signature on the operator digest. (c) `image-identities.yaml` accepts the operator image under the `devel` identity (development only) and under the release workflow's. (d) **Done 2026-10-25 (operator 0.1.39, the first release signed end to end):** operator, bundle and catalog verify without `--accept-dev` (release identity, provenance, signed SBOM); `catalogImage` of the d0 chart is on the signed catalog digest, `zuno_unifai_verify_catalog: true` on demo333, the CSV references the operator by digest. demo333's CatalogSource and Subscription were applied by hand (`:latest`), so the role patches only `spec.image` of the existing CatalogSource to the verified digest (`pin_catalog.yml`) and the drift check reads it. Operator 0.1.36 to 0.1.38 stay unsigned, no re-cut.
7. **Release path rehearsal. Done 2026-10-25:** `v0.0.0-rc1` built and signed the five images under `quay-release` (the first attempt failed in 2 s: that environment did not allow `v*` tags, now fixed by the owner); the verifier accepts all five WITHOUT `--accept-dev`. **Cleaned up 2026-10-25:** the `v0.0.0-rc1` tag is deleted from the five quay repositories and from the fork (the untagged images and their signatures expire with quay's garbage collection).
   Original text: A pre-release tag (`v0.0.0-rc1`) on the fork builds the five images with the `quay-release` environment and the owner's approval; the verifier accepts them without `--accept-dev` and refuses a `devel` build; the rc tags are removed from quay afterwards.
8. **Done 2026-10-25 (repo and demo333):** the backup Jobs' images pinned (`stack.backup.images`), the drift check of the third-party pins, the operator pod namespace, `pin_unifai_images.py` (one command: resolve, verify, rewrite the five digests). The cluster-side admission is WP-178.

## Acceptance

The verifier refuses an unsigned, an unpinned and a wrongly signed image and accepts the CI-built ones; the stack applies only with verified, digest-pinned images;
`make d2 check unifai` fails for a pod started with another image (the original text said `d1`: `unifai` is a Day 2 component). Live steps wait for demo333 to be powered on and the user's go.

## Open questions

- Whether the operator's bundle should reference the operator image by digest (decision of the operator owner, not needed for step 6).
- The cluster-side admission (`ClusterImagePolicy`, ADR-0586 decision 8) once the keyless identity type is confirmed on the live cluster.
