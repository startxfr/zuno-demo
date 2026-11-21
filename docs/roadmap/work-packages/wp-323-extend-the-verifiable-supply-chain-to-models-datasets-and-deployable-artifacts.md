# WP-323: Extend the verifiable supply chain to models, datasets and deployable artifacts

- **State:** Not started (proposed by ADR-0625 on 2026-11-21; the ADR is `Proposed`, so this work package is not approved)
- **ADRs:** [ADR-0625](../../adr/0625-evolve-zuno-toward-a-modular-sovereign-enterprise-ai-platform.md)
- **Depends on:** none
- **Related:** [ADR-0115](../../adr/0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md), [ADR-0535](../../adr/0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md), [ADR-0549](../../adr/0549-close-the-secnumcloud-supply-chain-gap-with-an-in-cluster-release-ledger.md), [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0580](../../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md), [ADR-0586](../../adr/0586-verify-the-unifai-runtime-images-by-digest-signature-and-attestations-before-deploying-them.md), [ADR-0612](../../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md)
- **Target:** v0.19
- **Estimated files touched:** ~10: admission rules, a ledger extension, tests, this brief

## Goal

Digest pins, signatures, admission coverage and provenance for models, datasets and deployable artifacts, as they exist today for images and OKF releases.

Horizon in the ADR's indicative roadmap: Day 30-60. The horizons count from the start of an approved initiative. They are not calendar dates.

## Proposed work

1. Extend immutable digest pins and signature and admission coverage to model weights and datasets.
2. Record provenance: hashes, model bills of materials, licences.
3. Validate the failure behaviour: an unsigned or altered artifact is refused.

## Existing work it builds on

- The release ledger of [ADR-0549](../../adr/0549-close-the-secnumcloud-supply-chain-gap-with-an-in-cluster-release-ledger.md), RHTAS ([ADR-0535](../../adr/0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md)), the keyless signing and offline verification of [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md) and [ADR-0586](../../adr/0586-verify-the-unifai-runtime-images-by-digest-signature-and-attestations-before-deploying-them.md), the digest pin of [ADR-0580](../../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md) and the internal Quay of [ADR-0612](../../adr/0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md).
- [ADR-0115](../../adr/0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md) is `Deferred`. This work package does not reopen its pipeline.

## Acceptance

- An admitted release can be rebuilt from verified, immutable artifacts, and rolled back with a documented procedure.
- An altered model or dataset is refused, and the test proves it.
