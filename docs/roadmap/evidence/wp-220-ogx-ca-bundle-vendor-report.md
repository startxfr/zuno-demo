<!-- Draft of an upstream report, written 2026-11-06 for WP-220. Not sent. Reproduction step 4 was not replayed on the day. -->

# OGXServer with spec.tls.trust.caCertificates never converges: operator rewrites the merged CA ConfigMap about every second

**Product / version:** Red Hat OpenShift AI 3.6.0-ea.2 (rhods-operator.3.6.0-ea.2), CRD `ogxservers.ogx.io/v1beta1`
**Cluster:** OpenShift (single cluster, fresh MaaS consumer portal install)
**Severity:** playground created from the MaaS consumer portal (gen-ai-studio) is unusable

## Summary

An `OGXServer` created by the portal playground carries `spec.tls.trust.caCertificates`
(two sources: `odh-trusted-ca-bundle` and `ogx-router-ca-bundle`). The operator keeps
rewriting the merged ConfigMap `<name>-ca-bundle` (241 certificates) about once per
second. The content alternates between two orderings of the same certificates. The
Deployment annotation `configmap.hash/ca-bundle` is derived from the ConfigMap
resourceVersion, so every rewrite changes the pod template and triggers a rollout.

## Observed

- 35 ReplicaSets in 2 minutes for one OGXServer; the server never reaches Ready.
- Portal symptoms: only an inline reranker model is listed (greyed), the passthrough
  provider models do not appear, and file upload fails with `Vector_store ... not found`
  (the sqlite kvstore is lost at each restart).
- An OGXServer without the `spec.tls` block (the platform's own `zuno-ogx` in
  `redhat-ods-applications`) is stable.

## Expected

The merge of CA sources must be deterministic (sorted, deduplicated), and the hash
annotation must be computed from the content, not from the resourceVersion, so that an
unchanged bundle does not roll the Deployment.

## Reproduction

1. From the MaaS consumer portal, create a playground in any project the user can edit.
2. `oc get rs -n <project> | wc -l` grows by about 15 per minute.
3. `oc get cm <name>-ca-bundle -n <project> -w` shows a new resourceVersion about every second.
4. `oc get cm <name>-ca-bundle -o jsonpath='{.data}' | sha256sum`, sampled repeatedly,
   alternates between two values.

## Tested mitigations

- Keeping a single CA source: the loop continues.
- Removing the block (`oc patch ogxserver <name> --type merge -p '{"spec":{"tls":null}}'`):
  the OGXServer becomes Ready with one stable pod. This is only a live edit; a playground
  created again by the portal brings the block back.

## Workaround we ship

A ready-made OGXServer without `spec.tls`, deployed by GitOps in a dedicated namespace.
