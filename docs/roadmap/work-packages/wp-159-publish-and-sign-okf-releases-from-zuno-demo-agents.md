# WP-159: Publish and sign OKF releases from zuno-demo-agents

- **State:** Not started
- **ADRs:** [ADR-0577](../../adr/0577-publish-okf-as-per-agent-artifacts-plus-a-corp-index-artifact.md), [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md)
- **Depends on:** [WP-158](wp-158-bootstrap-the-zuno-demo-agents-repository.md)
- **Related:** [ADR-0564](../../adr/0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [WP-150](wp-150-unifai-operator-okf-agent-bundles.md), [WP-160](wp-160-admit-the-corp-okf-release-in-zuno-demo.md)
- **Target:** v0.12
- **Estimated files touched:** ~10 in `zuno-demo-agents` (`.github/workflows/publish.yml`, `tools/okf_oci.py` and its tests, `RELEASING.md`).

> A tag is a release. Nothing is published from a branch, and nothing
> deployable exists without a corp artifact.

## Goal

Pushing `v<semver>` or `<agent>-v<semver>` builds reproducible per-agent
artifacts and a corp artifact, pushes them to `quay.io/zuno` (configurable),
signs every manifest keyless, attaches provenance and contract-test
attestations, and dispatches `okf-release` to `startxfr/zuno-demo`.

## Steps

1. **Library.** Move the layer builder of
   `platform/supply-chain/publish_okf_bundle.py` into `tools/okf_oci.py`,
   switch to the `v2` media types and runtime-only file set of ADR-0577
   clause 1, add the corp artifact (policies layer + index JSON, clause 2).
   Unit tests: two builds of one commit give one digest; `tests/` and
   `README.md` never enter a layer.

2. **Workflow `publish.yml`.** Triggers: tags `v*`, `*-v*`,
   `workflow_dispatch` (dry run, no push). Permissions: `id-token: write`,
   `contents: read`. Steps: run the full CI; compute changed agents (all on
   `v*`); `oras push` each changed agent; build and push `okf-corp` from the
   previous index plus the new digests; `cosign sign` keyless each digest;
   `cosign attest` SLSA provenance and the contract-tests predicate
   (ADR-0578 clause 3); send `repository_dispatch` `okf-release` with the
   corp digest and tag. `OKF_REGISTRY` defaults to `quay.io/zuno`.

3. **Secrets.** `QUAY_ROBOT_USER`/`QUAY_ROBOT_TOKEN`; a dispatch token
   restricted to `startxfr/zuno-demo` (fine-grained, `contents: write` is the
   minimum `repository_dispatch` accepts; prefer a GitHub App installed on
   that one repository). Ask the user to create them.

4. **First release.** Tag `v0.12.0-rc.1`; verify from a workstation with
   `cosign verify --certificate-identity-regexp ... --certificate-oidc-issuer
   https://token.actions.githubusercontent.com` on the corp and on each
   agent digest; verify that a wrong identity regexp fails;
   `oras manifest fetch` the corp index and resolve every agent digest.

5. **`RELEASING.md`.** How to cut a global and a single-agent release, and
   how to read the attestations.

## Acceptance

A tag produces signed, attested artifacts for every agent and one corp
artifact; offline verification succeeds with the expected identity and
fails with any other; two runs of the dry-run build print identical digests;
the `okf-release` dispatch reaches `zuno-demo` (visible in its Actions tab,
even before WP-160 handles it).

## Open questions

- Does quay.io accept OCI referrers (Sigstore bundle attached as a referrer)
  or must cosign fall back to the tag-based `.sig`/`.att` scheme? Either
  works for verification; record which one is used.
- WP-150's remaining step "publication with the real platform key" becomes
  this WP's keyless release; update WP-150's brief when this one starts.
