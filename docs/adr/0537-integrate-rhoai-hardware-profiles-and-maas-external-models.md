# ADR-0537: Integrate RHOAI HardwareProfiles for Local Models

- **Status:** Implemented
- **Target:** v0.5
- **Date:** 2026-09-01
- **Amended:** 2026-09-02 (two corrections: Decision 2's "no live webhook"
  claim was wrong, see Decision 2 and Consequences; Decision 1's
  `HardwareProfile` namespace moved from `zuno-ai-run` to `redhat-ods-
  applications` - the Dashboard's admin page can't see profiles anywhere
  else, see Decision 1)
- **Amended:** 2026-09-03 (split): this ADR originally also covered
  publishing `mistral`/`gpt-oss-120b` as `ExternalModel`+`MaaSModelRef`
  (former Decisions 3-4). That half is permanently blocked by a confirmed
  upstream `maas-controller` defect and has been extracted, unreworded, to
  [ADR-0541](0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md),
  so `Status` here can honestly reflect that the HardwareProfile half
  (Decisions 1-2, kept in this ADR) is fully live-verified. See ADR-0541
  for the full ExternalModel decision, its route-identity finding and the
  upstream issue tracking.
- **Decision owners:** Zuno Demo architecture team

## Context

A live diagnostic session on `granite-7b-redhat-lab` (deployed manually
through the RHOAI Dashboard into `zuno-ai-run`, `CrashLoopBackOff`)
surfaced a gap in how this platform integrates with OpenShift AI (RHOAI)
hardware profiles. (The same session also surfaced an unrelated gap - two
SaaS chat models bypassing MaaS governance - tracked separately in
[ADR-0541](0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md).)

No HardwareProfile parity for local models. Granite's `InferenceService`
carries `opendatahub.io/hardware-profile-name: default-profile`
(`redhat-ods-applications` namespace), set by the Dashboard at creation
time. Live inspection of that `HardwareProfile`
(`infrastructure.opendatahub.io/v1`) shows it declares only `CPU` and
`Memory` identifiers - no `Accelerator` identifier - so the Dashboard never
requested a GPU for the pod. The `vllm-cuda-rhel9` ServingRuntime image then
fails at startup with `RuntimeError: Failed to infer device type` (verified
in `kserve-container` logs), because no `nvidia.com/mig-*`/`nvidia.com/gpu`
resource was ever added to the pod spec. This is not a cluster GPU shortage:
both `zuno-ai-run` GPU nodes are healthy and MIG-partitioned
(`nvidia.com/mig-1g.24gb` x2, `nvidia.com/mig-2g.48gb` x1, per node). It is a
hardware-profile authoring gap.

Our own local models (`qwen35-9b`, `qwen35-9b-wesh`, `gpt-oss-20b`,
`qwen36-27b-instruct`, the `qwen3-embedding-0.6b` embedding) are deployed as
`LLMInferenceService`/`InferenceService` via Helm/ArgoCD
(`gitops/charts/models/templates/`), with `nodeSelector`+`resources` (MIG)
set explicitly in `values.yaml`. **No `HardwareProfile` CR exists anywhere in
this repo** - these deployments therefore never show a hardware profile in
the Dashboard, unlike Granite, even though they are correctly GPU-scheduled.

## Decision

1. **Create two GitOps-managed `HardwareProfile` CRs**, matching the two MIG
   tiers already in production use, as new Helm templates in
   `gitops/charts/models/templates/`.

   **Correction, 2026-09-02 (live-verified):** originally placed in the
   `zuno-ai-run` namespace to stay owned by the same ArgoCD Application as
   the models they describe. This broke the ADR's own goal: the Dashboard's
   Settings > Hardware profiles page is RBAC-scoped to `redhat-ods-
   applications` only (`fetch-hardware-profiles-role`/`hardware-profile-
   role-binding`, granted to `system:authenticated`, with no equivalent
   grant in any other namespace) - a `HardwareProfile` anywhere else is
   invisible to that page, even though the mutating scheduling path
   (Decision 2's correction) still honors it correctly cross-namespace.
   `default-profile` (the operator-seeded profile Granite uses) already
   lives in `redhat-ods-applications` for this reason. Both CRs now target
   `redhat-ods-applications` instead - confirmed live: the `zuno` AppProject
   allows it (`destinations: [{namespace: "*"}]`,
   `namespaceResourceWhitelist: [{group: "*", kind: "*"}]`), so the same
   `zuno-models-d1` Application can own a resource outside its own
   destination namespace without a second Application. Verified via
   `helm template` diff before applying: this move changes only
   `metadata.namespace` on both CRs and the `opendatahub.io/hardware-
   profile-namespace` annotation value on the five models - the resolved
   `nodeSelector` on every model is byte-identical before and after, so it
   does not re-trigger the Decision 2 rollout risk.

   ```yaml
   apiVersion: infrastructure.opendatahub.io/v1
   kind: HardwareProfile
   metadata:
     name: mig-1g-24gb
     namespace: redhat-ods-applications
   spec:
     identifiers:
       - identifier: nvidia.com/mig-1g.24gb
         displayName: GPU (1g.24gb MIG slice)
         resourceType: Accelerator
         minCount: 1
         defaultCount: 1
         maxCount: 2
       - identifier: cpu
         displayName: CPU
         resourceType: CPU
         minCount: 1
         defaultCount: 2
         maxCount: 8
       - identifier: memory
         displayName: Memory
         resourceType: Memory
         minCount: 4Gi
         defaultCount: 8Gi
         maxCount: 20Gi
     scheduling:
       type: Node
       node:
         nodeSelector:
           nvidia.com/gpu.present: "true"
   ```

   ```yaml
   apiVersion: infrastructure.opendatahub.io/v1
   kind: HardwareProfile
   metadata:
     name: mig-2g-48gb
     namespace: redhat-ods-applications
   spec:
     identifiers:
       - identifier: nvidia.com/mig-2g.48gb
         displayName: GPU (2g.48gb MIG slice)
         resourceType: Accelerator
         minCount: 1
         defaultCount: 1
         maxCount: 1
       - identifier: cpu
         displayName: CPU
         resourceType: CPU
         minCount: 1
         defaultCount: 2
         maxCount: 8
       - identifier: memory
         displayName: Memory
         resourceType: Memory
         minCount: 8Gi
         defaultCount: 16Gi
         maxCount: 48Gi
     scheduling:
       type: Node
       node:
         nodeSelector:
           nvidia.com/gpu.present: "true"
   ```

   `mig-1g-24gb` covers `qwen35-9b`, `gpt-oss-20b` and the embedding model;
   `mig-2g-48gb` covers `qwen35-9b-wesh` and `qwen36-27b-instruct` - the exact
   split already in `values.yaml`'s `resources` blocks today.

   `granite-7b-redhat-lab` stays **out of GitOps** (it is a manual
   Dashboard-driven deployment by design) - it is fixed and annotated by
   hand, selecting `mig-1g-24gb` at redeploy time, not folded into this
   chart.

   > **2026-09-03: the object no longer exists.** The diagnostic that
   > motivates this ADR stands, but `granite-7b-redhat-lab` was deleted to
   > release the `mig-1g.24gb` slice its stalled rollout was holding. The
   > hand-applied hardware profile had not been enough: with the GPU quota
   > saturated, its `minReplicas: 2` demanded a replica that could never be
   > admitted, so the ISVC stayed `READY=False` while its running pod starved
   > `embeddings` for nine days. This does not change the decision - a
   > redeployed Granite still stays out of GitOps - it only records that the
   > example is gone, and that `minReplicas: 1` is a precondition for
   > redeploying it at all.

2. **Annotate the five existing `LLMInferenceService`/`InferenceService`
   templates** so the Dashboard displays a hardware profile the same way it
   does for Granite:

   ```yaml
   annotations:
     opendatahub.io/hardware-profile-name: mig-1g-24gb   # or mig-2g-48gb
     opendatahub.io/hardware-profile-namespace: redhat-ods-applications
   ```

   applied to `llminferenceservice-qwen35.yaml`, `-gptoss.yaml`,
   `inferenceservice-embedding.yaml` (→ `mig-1g-24gb`) and
   `llminferenceservice-wesh.yaml`, `-qwen.yaml` (→ `mig-2g-48gb`).

   **Correction, 2026-09-02 (live-verified, WP-106 Phase 2 rollout):** this
   annotation is **not** purely declarative Dashboard metadata as first
   assumed here. A live RHOAI mutating admission path (fired on
   `InferenceService`/`LLMInferenceService` create/update) reads
   `opendatahub.io/hardware-profile-name`/`-namespace`, resolves the
   referenced `HardwareProfile`, and injects its
   `spec.scheduling.node.nodeSelector` into the generated pod template.
   Proven live: annotating `embeddings` (the one model with no pre-existing
   `nodeSelector`) produced a NEW pod template hash
   (`nodeSelector: {nvidia.com/gpu.present: "true"}` appearing where the old
   ReplicaSet had none) - a real Deployment rollout, not a no-op. The
   `resources` block remains the actual GPU-slice reservation (unaffected -
   confirmed identical between old/new pod templates); what this correction
   retracts is only the claim that the annotation has **no** live effect.
   The 4 other models were unaffected by this same mechanism only because
   they already carried an identical, hand-authored `nodeSelector` - the
   webhook's output happened to match, so no new pod template hash resulted.

## Consequences

Local models gain the same Dashboard hardware-profile display as manually
deployed ones, closing a real operator-confusion gap (this ADR's own
trigger: Granite's crash was invisible as a GPU problem until the profile's
`spec.identifiers` were read directly).

**Live incident, 2026-09-02 (WP-106 Phase 2 rollout):** Decision 2's
annotation triggered the mutating path corrected above, which produced a new
`embeddings` pod template and a `RollingUpdate` surge pod - rejected by the
`zuno-ai-run-gpu-cap` `ResourceQuota` (`mig-1g.24gb` already at 3/3: the
other two co-resident models plus `embeddings`' own running pod), leaving
`embeddings` `Progressing` and the whole `zuno-models-d1` Argo Application
stuck `Healthy: Progressing` (sync itself still succeeded). This is the
exact recurring trap WP-105 already documented for this chart's
GPU-saturated, single-replica, default-`RollingUpdate` models - not a new
failure mode, but the first time it was triggered by a metadata-only
annotation rather than a resources/image change. Recovered manually: scale
the stale ReplicaSet to 0 (frees the quota slot), then nudge the new
ReplicaSet `0→1` to bypass its exponential backoff. **Any future
`HardwareProfile`/annotation change to one of these five models carries the
same risk** - Operational considerations below now calls this out
explicitly; WP-105's own long-standing recommendation (`strategy:
{type: Recreate}`) would remove the trap at its root but is out of scope
here, same as it was there.

## Operational considerations

Granite's `HardwareProfile` correction is a one-time manual Dashboard
action (select `mig-1g-24gb` at redeploy), not a GitOps change - it carries
no ArgoCD drift-detection and must be re-applied by hand if the deployment
is ever recreated from scratch.

Any future edit to a `HardwareProfile`-annotated model's manifest - not
just a `resources`/image change, an annotation edit is enough, per the live
incident above - can trigger a `RollingUpdate` surge pod against these five
permanently GPU-quota-saturated models. Before merging such a change,
check whether the target model's own `nodeSelector` output would actually
change (a same-value mutation is a no-op); if it would, expect a stuck
rollout and be ready to run the WP-105 remedy: scale the stale ReplicaSet
to 0, then nudge the new one `0→1` past its exponential backoff.

## Acceptance criteria

Beyond the Standard clauses - both live-verified 2026-09-02:

- Dashboard shows a hardware profile badge for all five annotated
  InferenceServices, matching Granite's presentation.
- `oc apply --dry-run=server` (or equivalent) confirms both `HardwareProfile`
  CRs are schema-valid on the live cluster.

## References

- Work package: [WP-106](../roadmap/work-packages/wp-106-rhoai-hardware-profiles-and-maas-external-models.md).

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md)
  - the MIG partitioning strategy the two `HardwareProfile` CRs describe.
- [ADR-0541](0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md)
  - the sibling ADR this one was split from 2026-09-03: publishing
    `mistral`/`gpt-oss-120b` as `ExternalModel`+`MaaSModelRef`, blocked
    upstream and tracked separately.
