# Operations

Operational documentation will cover agent enable/disable, model health, MCP health, RAG refresh, scheduled tasks, user/session support, quotas, costs, logs and tracing.

## UnifAI image admission (ADR-0586, WP-178)

The Sigstore policy-controller (webhook `policy.rhtas.com`, namespace `policy-controller-operator`) checks the keyless signature of every
`quay.io/zuno/unifai-**` image of a pod created in an opted-in namespace (`zuno-unifai`, `unifai-operator`: label `policy.rhtas.com/include=true`).
The policy is `ClusterImagePolicy zuno-unifai-images`; its identities come from `platform/supply-chain/image-identities.yaml` (release workflows
always, the `devel` build only on a cluster that accepts development signatures). Images that match no policy (MongoDB, Qdrant, RabbitMQ, Redis,
Temporal, docling, the backup Jobs) are only reported (`no-match-policy: warn`). zuno's own verifier and drift check
(`make d2 check unifai`) stay the main guard: the admission is the second one, at the cluster.

### Look at it

```
oc get clusterimagepolicies.policy.sigstore.dev zuno-unifai-images -o jsonpath='{.spec.mode}{"\n"}'   # warn or enforce
oc get ns -l policy.rhtas.com/include=true
oc logs -n policy-controller-operator deploy/zuno-policy-controller-webhook --since=24h | \
  grep -E "Failed to validate at least one policy for quay.io/zuno/unifai|no matching policies for image quay.io/zuno"
```

Use the full resource name `clusterimagepolicies.policy.sigstore.dev`: a bare `clusterimagepolicy` also names OpenShift's own resource.
A line in the webhook log names the namespace, the pod and the image. In `warn` it is an admission warning (the pod was created); in
`enforce` the pod creation was refused (`oc get events -n <namespace>` shows `admission webhook "policy.rhtas.com" denied the request`).

### Warn or enforce

The mode is a cluster variable: `zuno_unifai_admission_mode` (default `warn`) in `ansible/clusters/<cluster>.yml`, applied by
`make d1 install rhtas-config`. `zuno_unifai_admission_enabled: false` removes the policy and the labels. Only the UnifAI policy changes mode:
the first-party policy `zuno-first-party-images` stays in `warn`. A new cluster gets the policy in `warn`.

### A legitimate pod is refused (break-glass)

1. Find the reason in the event or the webhook log. Most often the image is not signed by an identity of `image-identities.yaml` (a hand-built
   image, a branch build on a cluster that does not accept development builds) or it was signed only in the Ed25519 Rekor v2 log, which the
   controller cannot read (zuno's verifier accepts it, the admission does not).
2. Unblock at once, without a deployment: `oc label namespace <namespace> policy.rhtas.com/include-` removes the namespace from the
   webhook (undo with `oc label namespace <namespace> policy.rhtas.com/include=true`, or re-run `make d1 install rhtas-config`, which labels it again).
   Or switch the cluster to `warn` and re-run the install.
3. Fix the cause: pin a CI-built signed digest (`python3 platform/supply-chain/pin_unifai_images.py devel-<sha> --accept-dev`) and apply it with
   `make d2 install unifai`.

### Before a pin

`pin_unifai_images.py` and `pin_operator_catalog.py` verify the digests offline, then send them through the cluster's webhook (a server-side
dry-run Pod in `zuno-unifai`, `platform/supply-chain/admission_preflight.py`). A digest that cosign accepts but the webhook warns about or
refuses stops the pin, with the webhook's own message. When the cluster cannot answer, the step is skipped with a notice;
`--no-admission-preflight` skips it on purpose.

### Limits

- The webhook has `failurePolicy: Ignore` and one replica: if it is down or slower than its 10 s timeout, pods are admitted without a check
  (fail-open). Protection is best-effort; the verifier and the drift check do not depend on it.
- The controller only reads ECDSA transparency-log keys. The trusted root also lists an Ed25519 key (Rekor v2, `log2025-1`): a signature logged only
  there verifies with cosign but not at admission. The pin preflight catches it before a rollout. Re-check when the policy-controller
  supports Ed25519, or if the fork's CI moves to a cosign that signs into Rekor v2.
- Attestations (provenance, SBOM) are not checked at admission: an attestation of an expired Fulcio certificate needs a Rekor lookup. zuno's
  verifier checks them before the stack is applied.
- The trust root is rendered offline from `platform/okf/sigstore/trusted_root.json` (`platform/supply-chain/render_policy_trustroot.py`; CI checks it
  is up to date). After a Sigstore root rotation, regenerate it and re-run `make d1 install rhtas-config`.

## Rolling a UnifAI release, and taking over a roll (WP-176, WP-178)

Operator and application images move in two separate steps, always in this order, each with the user's go and with the owner of any running measurement (stresstest, ranking set) agreeing that no UnifAI pod may restart.

1. **Operator.** The release owner publishes the operator, bundle and catalog digests once its CI and canary are green. From a detached worktree on `origin/devel` with `ansible/confidential.yml` copied in: `python3 platform/supply-chain/pin_operator_catalog.py latest --version X.Y.Z --dry-run` (signatures with the release identity, then the admission preflight), the same without `--dry-run`, commit and push only that commit, then `make d2 install unifai` and `make d2 check unifai`. Only the operator controller restarts. Rolled so far on demo333: 0.1.42 to 0.1.45 and 0.1.47 (0.1.46 was never released).
2. **Application images, one roll.** `python3 platform/supply-chain/pin_unifai_images.py devel-<sha> --accept-dev --dry-run`, then the real pin, then a single `make d2 install unifai`: this restarts the UnifAI pods, so batch every stack change (chart values, CR fields) into the same roll. Settings that a release adds but a measurement owner switches on one by one (ranking `spec.rag.search`, `spec.rag.reranker`, `resyncToken`) stay unset in that roll.
3. **Check.** `make d2 check unifai`, the webhook log (`policy-controller-operator`) for refusals, and the release owner's read-only proofs (digests, environment of the pods).
4. **Rollback.** Re-pin the previous digests and run `make d2 install unifai` again; a stack field added in the roll is removed by dropping it from the chart values.

When the session that owned a roll has disappeared (no entry in the session list), nothing was handed over unless it is committed on `origin/devel`: re-derive the pins with the dry-run, ask the release owner for the CR fields and the settings that must stay unset, and take the user's go again before touching the cluster. A peer's message is information, not the user's approval.
