# WP-257: Document how to publish, verify and roll back an OKF release safely

- **State:** Repo work merged (2026-11-13, shipped in zuno-demo-agents v0.14.4; the proofs that need a canary or unifai-compare remain)
- **ADRs:** [ADR-0577](../../adr/0577-publish-okf-as-per-agent-artifacts-plus-a-corp-index-artifact.md),
  [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md),
  [ADR-0580](../../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md)
- **Depends on:** none
- **Related:** [WP-255](wp-255-okf-field-reference-in-the-agents-repository.md), [WP-258](wp-258-unifaiagentbundle-custom-resource-page-in-the-agents-repository.md)
- **Target repository:** `startxfr/zuno-demo-agents` (public, English); tracked here, landed there by pull request
- **Estimated files touched:** ~3 in zuno-demo-agents: `docs/publish-and-verify.md`, `RELEASING.md` (links), the README

> Execute this brief as a standalone task. Documentation only, except one decision (the SBOM) recorded in the page. Opened 2026-11-13 (user's go).

## Why

`RELEASING.md` says how the maintainers release. It does not tell a consumer how to verify what they pull, how to go back, or how to
adapt the trust settings to a different identity, registry or key. A third party who copies the repository has no path to a safe release.

## Goal

A consumer or a third party can verify an agent artifact and the corp index, roll back a bad release, and adapt the trust to their own
setup, from this repository alone.

## Content

1. **Verify an agent artifact and the corp index:** `cosign verify` by identity (GitHub OIDC), offline, with the expected issuer and subject.
2. **Contract tests and provenance:** `cosign verify-attestation`, the attestation type, what it proves.
3. **Limits:** the 32-layer limit of a bundle artifact and what to do near it.
4. **Rollback:** re-pin the previous corp digest; what a consumer must do; no deletion of a published artifact.
5. **Adapt it elsewhere:** the identity (workflow subject), the registry (default `quay.io/zuno`), the attestation type.
6. **Key signing:** `verify.publicKeyRef` for a consumer without GitHub OIDC; how the key is generated, stored and rotated.
7. **SBOM:** absent today. Decide in this WP whether to produce one and where; record the decision with its reason. Whatever is decided,
   the page says so.

## Source

`RELEASING.md`, `platform/release/` (build, publish, version gate), the signing and verification workflows, zuno-demo ADR-0577, 0578 and 0580.
Every command in the page is run once against a real release; the output is described, never pasted with secrets.

## Proof

- The verification commands succeed on the latest release and fail on a tampered copy (a wrong subject is enough).
- The rollback steps are checked against a canary pin before they are written down as safe.

## Lots

| Lot | Content |
|---|---|
| 1 | Verification and attestation sections, run against a real release |
| 2 | Rollback, adaptation, key signing, the SBOM decision; pull request |

## Out of scope

- Changing the signing chain itself.
