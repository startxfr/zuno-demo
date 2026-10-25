# WP-178: Admit only signed UnifAI images at the cluster

- **State:** Repo work merged
- **ADRs:** [ADR-0586](../../adr/0586-verify-the-unifai-runtime-images-by-digest-signature-and-attestations-before-deploying-them.md)
- **Depends on:** [WP-176](wp-176-verify-the-unifai-runtime-images-before-deploying-them.md)
- **Related:** [WP-110](wp-110-rhtas-operator-live-findings.md)
- **Target:** v0.11
- **Estimated files touched:** ~9 in `zuno-demo` (`gitops/charts/rhtas-config`, `ansible/roles/rhtas_config`, `platform/supply-chain`, docs) and none in the fork

> Decision of 2026-10-25 (user): the cluster-side admission of ADR-0586 decision 8 is built on the Sigstore `policy-controller` the
> platform already runs (RHTAS, ADR-0535), with an offline public-Sigstore trust root, `no-match-policy: warn`, and the namespaces
> `zuno-unifai` and `unifai-operator`. Mode `warn` first; `enforce` is a separate, later decision.

## Goal

A pod of `quay.io/zuno/unifai-**` whose image is not signed by the fork's workflow identity is refused by the cluster itself, not only
by the `unifai` role, so a hand-applied manifest or a rollout outside the role cannot run an unsigned UnifAI image.

## What was found (demo333, OCP 4.22.8, policy-controller-operator 1.0.2, 2026-10-25)

- OpenShift's `ClusterImagePolicy` (`config.openshift.io/v1`) cannot express the identity: `fulcioSubject` needs a `signedEmail`.
- The policy-controller (webhook `policy.rhtas.com`, `failurePolicy: Ignore`) only sees namespaces labelled `policy.rhtas.com/include=true`.
  None was labelled: it admitted nothing. Its `zuno-first-party-images` policy (internal registry, warn) is untouched.
- A `TrustRoot` with `sigstoreKeys` takes **base64-encoded PEM** (`certChain`, `publicKey`); a bare PEM is refused ("illegal base64 data").
  Its reconciler rejects any non-ECDSA log key ("public key 1 is not ecdsa.PublicKey"), so the Ed25519 Rekor v2 key of the trusted root is left
  out: signatures logged only there verify with zuno's own offline verifier but not at admission. Rekor v1 (ECDSA) signs what cosign 2.4.1 produces.
- An image that matches no policy is **denied** in an opted-in namespace ("no matching policies") whatever the policy mode, which would refuse
  the unsigned third-party services: `no-match-policy: warn` (`PolicyController` `webhook.configData`, rendered into `config-policy-controller`).
- Tags are resolved to digests by the defaulting webhook (a tagged image got `repo:tag@sha256:...`).
- Attestations are not checked at admission: an attestation of an expired Fulcio certificate needs a Rekor lookup ("expected a signed timestamp
  to verify an expired certificate"). The signature identity is checked; provenance and SBOM stay with zuno's verifier before the stack is applied.
- Verified in a labelled test namespace with server-side dry-run pods: a CI-signed digest and operator 0.1.40 pass without warning, an unsigned
  digest is a warning in `warn` and refused in `enforce`, a third-party digest is a warning with `no-match-policy: warn`.

## Steps

1. **Done (repo).** `platform/supply-chain/render_policy_trustroot.py` renders `gitops/charts/rhtas-config/files/public-sigstore-trustroot.yaml` from
   `platform/okf/sigstore/trusted_root.json` (CI runs `--check`); chart templates `trustroot-public.yaml`, `clusterimagepolicy-unifai.yaml`,
   `policycontroller.yaml` (`configData`); `ansible/roles/rhtas_config` passes the identities from `image-identities.yaml` (development ones only on a
   cluster that accepts them), waits for the policy, and labels the namespaces.
2. **Done 2026-10-25 (demo333).** `make d1 install rhtas-config` (`zuno-unifai-images` Ready in `warn`, TrustRoot `public-sigstore-trust-root`, `config-policy-controller` `no-match-policy: warn`, `zuno-unifai` and `unifai-operator` labelled). On both namespaces, server-side dry-run pods: a CI-signed `unifai-ui` digest and operator 0.1.40 are admitted without a warning, the unsigned digest is a warning, a third-party digest is a `no matching policies` warning; a real pod (redis-insight) was deleted and recreated normally. `make d1 check rhtas-config` and `make d2 check unifai` stay green.
3. **One release cycle in `warn`** (first real admission 2026-10-25: operator 0.1.41, catalogue moved by the role, the new operator pod `quay.io/zuno/unifai-operator@sha256:ed6a01f5...` admitted with no warning; the `zuno-unifai` pods were not recreated, so the application images still wait for their next pin) without an unexpected warning (watch the webhook log).
3b. **Done (repo, 2026-10-25), closing work decided by the user:** an admission preflight in the pin scripts (`platform/supply-chain/admission_preflight.py`:
   a server-side dry-run Pod per digest through the real webhook, run by `pin_unifai_images.py` and `pin_operator_catalog.py` after the offline verification, so a
   digest cosign accepts but the controller does not, e.g. one signed only in the Ed25519 Rekor v2 log, stops the pin), the runbook in `docs/platform/operations.md`
   (look, warn/enforce, break-glass, limits), `zuno_unifai_admission_enabled: false` removes the labels too. The webhook keeps `failurePolicy: Ignore` and one replica
   (fail-open, accepted). Other clusters get the policy in `warn` by default.
3c. **Real admission of the application images** (restart of `unifai-ui`, `unifai-identity`, `unifai-rag-server`, `unifai-backend` one by one, no warning in the webhook):
   `unifai-backend` done 2026-10-25 20:49 UTC (admitted without a warning); the others wait for the tekos stresstest series of 2026-10-25 to end (about 21:40 UTC).
4. **`enforce`** for `zuno-unifai-images` only (the third-party services stay `warn` through `no-match-policy`), by the user's decision, with a break-glass in the
   runbook (remove the namespace label).

## Acceptance

A pod running an unsigned `quay.io/zuno/unifai-ui` digest is refused in `enforce` and warned in `warn`, a CI-signed one is admitted, and a pod of a
third-party image is unaffected.
