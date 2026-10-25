# WP-178: Admit only signed UnifAI images at the cluster

- **State:** Not started
- **ADRs:** [ADR-0586](../../adr/0586-verify-the-unifai-runtime-images-by-digest-signature-and-attestations-before-deploying-them.md)
- **Depends on:** [WP-176](wp-176-verify-the-unifai-runtime-images-before-deploying-them.md)
- **Related:** [WP-110](wp-110-rhtas-operator-live-findings.md)
- **Target:** v0.11
- **Estimated files touched:** ~6 in `zuno-demo` (a `policy-controller` chart or values, a `ClusterImagePolicy`, the `unifai` role, docs) and none in the fork

> Decision of 2026-10-25 (user): the cluster-side admission of ADR-0586 decision 8 is deferred out of WP-176, which closes on
> "verified at deployment and checked on what runs".

## Goal

A pod of `quay.io/zuno/unifai-*` that is not signed by the fork's workflow identity is refused by the cluster itself, not only
by the `unifai` role, so a hand-applied manifest or a rollout outside the role cannot run an unsigned UnifAI image.

## What is known (checked on demo333, OCP 4.22.8, 2026-10-25)

- OpenShift's `ClusterImagePolicy` (`config.openshift.io/v1`) cannot express the identity: `fulcioCAWithRekor.fulcioSubject`
  requires `oidcIssuer` and a `signedEmail`, and a GitHub workflow certificate carries a URI subject, not an e-mail. It stays
  usable only with a public-key policy, which is a different trust model (keys, not the committed Sigstore root).
- The Sigstore `policy-controller` CRD (`policy.sigstore.dev/v1beta1`, `ClusterImagePolicy`) is installed and dormant. It was
  dormant because it refused tag references; the five application images are now pinned by digest. Third-party images
  (unsigned) must stay outside its glob.

## Steps

1. Scope: images matching `quay.io/zuno/unifai-*` only, in namespaces `zuno-unifai` and the operator namespace.
2. Mode `warn` first (violations logged, nothing refused); watch one full release cycle.
3. Identities: the same regexps as `platform/supply-chain/image-identities.yaml` (one source, rendered into the policy), `devel`
   identity only on clusters that accept it.
4. `enforce`, after a release has gone through `warn` without a finding; keep an explicit break-glass (label opt-out) written
   in the runbook.

## Acceptance

A pod running an unsigned `quay.io/zuno/unifai-ui` digest is refused in `enforce`, a CI-signed one is admitted, and a pod of a
third-party image is unaffected.
