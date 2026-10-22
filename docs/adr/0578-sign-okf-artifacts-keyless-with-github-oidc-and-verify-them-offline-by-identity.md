# ADR-0578: Sign OKF artifacts keyless with GitHub OIDC and verify them offline by identity

- **Status:** Accepted
- **Target:** v0.12
- **Date:** 2026-10-22
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md) in part (the Transit signature of clause 1 as amended on 2026-10-17, and `spec.verify.publicKeyRef` as the only verification mode of clause 2)
- **Related:** [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md), [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md), [ADR-0420](0420-sign-supply-chain-artifacts-in-cluster-with-vault-transit.md), [ADR-0535](0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md), [ADR-0576](0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md), [ADR-0577](0577-publish-okf-as-per-agent-artifacts-plus-a-corp-index-artifact.md), [ADR-0580](0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md)

## Context

OKF bundles are signed today by `make d3 sign agents`: an in-cluster Job
signs each bundle's content digest with the Vault Transit key
`zuno-platform-signer` (ADR-0420, mechanism kept by ADR-0535 as its rollback
path), and consumers verify against the committed
`agents/zuno-platform-signer.pub`. Two failure modes are on record: a bundle
edited without re-signing wedged a rollout, and a regenerated Transit key
silently broke every offline check because nothing re-exports the public key
(ADR-0106 note of 2026-08-25).

That design proves one thing: *the platform* signed the bytes. After
ADR-0576 the bytes are produced in another repository, by its CI, on GitHub.
The cluster's Vault is not reachable from GitHub Actions, and should not be.
Signing in the cluster after the fact would sign whatever was pulled, which
proves acceptance, not origin.

ADR-0420 removed keyless GitHub-OIDC signing on 2026-08-22 because nothing
consumed its signatures and because running entirely inside the cluster was
a stated goal. ADR-0535 then adopted RHTAS for keyless signing of images
inside the cluster. Neither applies to an artifact that is built, published
and released outside the cluster by design: the user decision of 2026-10-22
places the agents repository on GitHub and its artifacts on quay.io.

## Decision

**1. OKF artifacts are signed keyless by the publish workflow.** The
`publish.yml` workflow of `startxfr/zuno-demo-agents` requests a GitHub OIDC
token (`id-token: write`), and `cosign sign` signs each pushed manifest
digest, agent artifacts and corp artifact alike (ADR-0577), through
Sigstore's public-good Fulcio and Rekor. The signature, certificate and Rekor
inclusion proof are attached to the artifact as a Sigstore bundle (OCI
referrer). There is no long-lived key to store, rotate or re-export.

**2. Verification is by identity, never by key.** A valid OKF signature is
one whose certificate has:

- issuer `https://token.actions.githubusercontent.com`;
- subject matching
  `^https://github\.com/startxfr/zuno-demo-agents/\.github/workflows/publish\.yml@refs/tags/`
  (only the release workflow, only from a tag);
- the GitHub `sourceRepositoryRef` and `sourceRepositoryDigest` certificate
  extensions, whose commit must equal the artifact's
  `org.opencontainers.image.revision` annotation.

A signature from another repository, another workflow, a branch build or a
fork fails. The expected identity is configuration in `zuno-demo`, kept in
one place (`platform/okf/sigstore/identity.yaml`).

**3. Attestations travel with the artifact.** The workflow also attaches,
signed the same way, an SLSA provenance attestation (`cosign attest
--type slsaprovenance1`) and a `https://zuno.startx.fr/okf/contract-tests/v1`
predicate recording the CI checks that passed (schema, bundle validation,
contract suites, matrix drift) and the `platform-contract.json` digest used.
Admission (ADR-0580) requires both.

**4. Verification works offline.** Consumers in the cluster never call
Fulcio, Rekor or the Sigstore TUF mirror at verification time. `zuno-demo`
commits the Sigstore `trusted_root.json` under `platform/okf/sigstore/`; the
attached bundle carries the Rekor inclusion proof; `cosign verify
--offline --trusted-root ...` (and sigstore-go in `unifai-operator`) checks
both. The trusted root is refreshed by a dedicated make target that fetches
it through TUF and is reviewed like any pin bump.

**5. Vault Transit leaves the OKF path.** `day3_sign.yml`'s signing Job, the
Vault KV `zuno/okf-signatures` path, the agent-runtime ExternalSecret and the
vault role's export of `agents/zuno-platform-signer.pub` stop serving OKF
(removed by WP-165). The Transit key stays for whatever else ADR-0535 keeps
it for.

**6. `UnifaiAgentBundle.spec.verify` gains a keyless mode.** Next to
`publicKeyRef` (kept for the transition), `keyless` takes `issuer`,
`subjectRegExp` and a `trustedRootRef` (a ConfigMap key). Exactly one mode is
required; there is still no "skip".

**7. Scope of the exception.** This is a deliberate, bounded exception to
the in-cluster-only posture of ADR-0420 and ADR-0535, for the OKF supply
chain only. Container images keep RHTAS (ADR-0535).

## Amendment (2026-10-22) - identities and attestations, as built

Corrected while `Accepted`, before the first release. Clauses 1, 4, 5, 6
and 7 stand.

- **Clause 2, revision check.** The certificate commit is compared with the
  corp artifact's `org.opencontainers.image.revision` only. An agent
  artifact's revision is the last commit touching that agent (ADR-0577
  amendment), so it legitimately differs from the release commit; the agent
  is bound to the release through the signed corp index instead.
- **Dev artifacts** are signed keyless by `publish-dev.yml` on
  `refs/heads/devel` or `refs/heads/main`. That identity never matches
  clause 2's release subject, and the dev cluster run verifies exactly it.
- **Clause 3, attestations.** Every artifact carries the
  `https://zuno.startx.fr/okf/contract-tests/v1` attestation. SLSA build
  provenance is produced by `actions/attest-build-provenance` for the corp
  artifact, the release unit, and pushed to the registry.
- **Trust root.** Release tags are created only by the release GitHub App
  (`zuno-release-bot`), enforced by a tag ruleset on `v*` and `*-v*` that
  also forbids moving or deleting them; `stable` likewise. This replaces
  "maintainers only" in the security considerations.

## Consequences

The signature now proves origin (this repository, this workflow, this tag,
this commit) instead of "the platform signed what it had". Key loss and
re-export drift disappear because there is no key.

The cluster depends on Sigstore's public-good instance at signing time only,
and on GitHub's OIDC issuer remaining the identity root. If Sigstore
public-good is unavailable, no new release can be published; admitted
releases keep verifying offline.

`unifai-operator` gains a dependency on sigstore-go in its zuno-specific
`internal/okf/` package (ADR-0575: fork-only code).

## Security considerations

Anyone who can push a `v*` or `<agent>-v*` tag to `zuno-demo-agents` can
produce a valid release. Tag protection rules restricted to maintainers, and
required reviews on `main`, are therefore part of the trust root and a
precondition of WP-159.

Signing records the artifact digest, the repository and the workflow in
Rekor's public log. The repository is already public, so this discloses
nothing new.

The `trusted_root.json` pin is security-relevant: a refresh is reviewed
against the Sigstore TUF root, never edited by hand.

## Operational considerations

The publish workflow needs `id-token: write`, `packages: write` is not
needed (the registry is quay.io), and a quay.io robot secret. No step of this
decision touches a cluster; verification changes on the cluster land with
ADR-0580's WPs.
