# WP-162: Keyless OKF verification in unifai-operator

- **State:** Done
- **ADRs:** [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0577](../../adr/0577-publish-okf-as-per-agent-artifacts-plus-a-corp-index-artifact.md)
- **Depends on:** [WP-159](wp-159-publish-and-sign-okf-releases-from-zuno-demo-agents.md), [WP-150](wp-150-unifai-operator-okf-agent-bundles.md)
- **Related:** [ADR-0564](../../adr/0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0575](../../adr/0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md), [WP-164](wp-164-generate-stack-configuration-from-the-corp-release.md)
- **Target:** v0.12
- **Estimated files touched:** ~10 in the fork (`fork/unifai-operator/internal/okf/`, `api/v1alpha1/` bundle types and CRD, tests, `README.md`); ~4 in `zuno-demo` (`gitops/charts/unifai/templates/{objects,checks}.yaml`, values).

> Fork-only code (ADR-0575): nothing here leaves `fork/`.

## Note (2026-10-23)

Taken by the session that owns `fork/unifai-operator` (the UnifaiAgentBundle
files), after its teamRef/UnifaiTeam bundle work; nobody else edits the fork
meanwhile. The chart takes `spec.verify.keyless` (issuer, subjectRegExp) from
`unifai.verify.keyless` in `platform/okf/stack-config.generated.yaml`
(WP-164), itself read from `platform/okf/sigstore/identity.yaml`: the
identities are written in one place only. Test artifact:
`quay.io/zuno/okf-tekos@sha256:bf429d3e6173781f10c858ed81a7f7c23073d9b0ba7ddd1044651d3868fcadba`
(dev-signed); the trusted root is `platform/okf/sigstore/trusted_root.json`.


`UnifaiAgentBundle.spec.verify.keyless` verifies an agent artifact by
issuer and subject against a mounted trusted root, offline, and reads the
`v2` media type; the zuno chart renders keyless bundles from generated
values.

## Progress (2026-10-23)

Operator side done in the fork (devel 469df4ad8, shipping in unifai-operator
0.1.25): `spec.verify` takes exactly one of `publicKeyRef` or `keyless`
{issuer, subjectRegExp, trustedRootRef} (CEL), the controller verifies the
cosign signature of the manifest digest offline with sigstore-go (Fulcio
chain, SCT, Rekor signed entry timestamp, certificate identity), records the
signer in `status.signer`, and the OCI reader accepts the `v2` media type next
to `v1` (a `v2` artifact refuses a public-key CR). Unit and envtest cover the
real dev-signed `okf-tekos` artifact and the public trusted root: accepted for
the dev workflow identity, refused for the release identity, another issuer,
another digest and a tampered payload.

Chart side done in zuno-demo: `okf.verify.keyless` + `okf.trustedRoot` render
the `spec.verify.keyless` block and the trusted-root Secret, and
`okf.bundles[].groupTeam` renders the bundle-owned team. Live on demo333 (2026-10-23)
with unifai-operator 0.1.25 on `stable`: the five deployed agents of release
v0.1.1 are verified keyless, `status.signer` is the release workflow identity
(`publish.yml@refs/tags/v0.1.1`); evidence in
[wp-154-tekos-pilot-phase-a.md](../evidence/wp-154-tekos-pilot-phase-a.md).

## Steps

1. **Types.** Add `spec.verify.keyless` (`issuer`, `subjectRegExp`,
   `trustedRootRef`), CEL: exactly one of `publicKeyRef`, `keyless`.

2. **Verifier.** In `internal/okf/`, sigstore-go verification of the
   Sigstore bundle attached to the manifest, offline, with the certificate
   identity policy of ADR-0578 clause 2 (including the revision check).
   `Verified=False` with a distinct reason per failure (no signature,
   identity mismatch, tlog proof invalid).

3. **Media types.** Accept `application/vnd.zuno.okf.bundle.v2` (runtime
   files only) and keep `v1` during the transition.

4. **Release and chart.** Release the operator per ADR-0574; the zuno chart
   renders `verify.keyless` and a trusted-root ConfigMap; `checks.yaml`
   requires digests (unchanged) and accepts keyless.

5. **Live on demo333:** a bundle from the first keyless release reaches
   `Ready`; the same digest with a wrong `subjectRegExp` gets
   `Verified=False`.

## Acceptance

Operator tests cover each failure reason; live proof as in step 5; the
`publicKeyRef` path still passes its existing tests.
