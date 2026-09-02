# ADR-0537: Integrate RHOAI HardwareProfiles and MaaS ExternalModels

- **Status:** Proposed
- **Target:** v0.5
- **Date:** 2026-09-01
- **Amended:** 2026-09-02 (two corrections: Decision 2's "no live webhook"
  claim was wrong, see Decision 2 and Consequences; Decision 1's
  `HardwareProfile` namespace moved from `zuno-ai-run` to `redhat-ods-
  applications` - the Dashboard's admin page can't see profiles anywhere
  else, see Decision 1)
- **Decision owners:** Zuno Demo architecture team

## Context

A live diagnostic session on `granite-7b-redhat-lab` (deployed manually
through the RHOAI Dashboard into `zuno-ai-run`, `CrashLoopBackOff`) surfaced
two unrelated gaps in how this platform integrates with OpenShift AI (RHOAI).

**Gap 1 - no HardwareProfile parity for local models.** Granite's
`InferenceService` carries `opendatahub.io/hardware-profile-name:
default-profile` (`redhat-ods-applications` namespace), set by the Dashboard
at creation time. Live inspection of that `HardwareProfile`
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

**Gap 2 - two SaaS chat models sit outside MaaS governance.** `mistral`
(native Mistral API, `api.mistral.ai`) and `gpt-oss-120b`
(OVHcloud AI Endpoints, ADR-0416) are called directly from `ai-gateway`
(`components/ai-gateway/app/providers.py`), with credentials mounted
directly into that component. Since ADR-0521, every **local** model's
traffic is routed through the RHOAI MaaS governance plane
(`MaaSModelRef`/`MaaSSubscription`/`MaaSAuthPolicy`), giving group-based
access control and platform-native rate limiting. These two external models
get neither - they are governed only by Zuno's own C1/C2/C3 classification
(ADR-0021) and the fleet-wide OVHcloud eligibility/exclusion rules ADR-0416
already established (Finage excluded via `zuno.model.local_only: true`).

The transport for a MaaS-routed SaaS candidate already exists in skeleton
form: `components/ai-gateway/app/maas_adapter.py::should_use_maas()`
(lines 110-124) has a third gate, `candidate_kind != "local" and not
MAAS_EXTERNAL_EGRESS_ENABLED`, anticipated since ADR-0201/WP-27 but never
exercised - no `provider-routing.yaml` entry sets `via_maas: true` on a SaaS
candidate, and `MAAS_EXTERNAL_EGRESS_ENABLED` is never set to `true`. This is
a gap to **activate**, not a mechanism to build from zero.

RHOAI's `ExternalModel` CRD was explicitly evaluated and rejected once
before, in ADR-0201, for a **local** vLLM Service - the CRD's
`externalProviderRefs[].ref` → `ExternalProvider` shape requires an
authenticated external FQDN + `auth` config, which does not fit an
unauthenticated in-cluster Service. That is exactly the shape of `mistral`
and `gpt-oss-120b`, both genuine external, authenticated SaaS endpoints -
`ExternalModel` is the right fit here, unlike in its original evaluation.

Live verification during this ADR's preparation confirmed:
- Two distinct `ExternalModel` CRDs exist on this cluster:
  `externalmodels.inference.opendatahub.io` (generic, multi-provider,
  weighted `externalProviderRefs[]`) and `externalmodels.maas.opendatahub.io`
  (single-provider: `endpoint`, `provider`, `targetModel`,
  `credentialRef.name`). `MaaSModelRef.spec.modelRef.kind: ExternalModel`
  is the `maas.opendatahub.io` one - it is the one referenced throughout
  ADR-0201 and is the one this ADR uses.
- `spec.provider` is a free string with no CRD-level enum
  (`oc apply --dry-run=server` accepted `provider: mistral` without
  rejection) - no admission webhook validates it; behaviour depends on the
  `maas-controller` reconciler at runtime, unverified until a live call
  succeeds.
- `credentialRef` requires the referenced Secret's data key to be literally
  `api-key`. The existing Secrets (`llm-provider-mistral`,
  `llm-provider-ovhcloud`, both `ExternalSecret`-managed) use `api_key`. This
  is a real mismatch this ADR must resolve, not a naming nit.

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
     namespace: zuno-ai-run
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
     namespace: zuno-ai-run
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

2. **Annotate the five existing `LLMInferenceService`/`InferenceService`
   templates** so the Dashboard displays a hardware profile the same way it
   does for Granite:

   ```yaml
   annotations:
     opendatahub.io/hardware-profile-name: mig-1g-24gb   # or mig-2g-48gb
     opendatahub.io/hardware-profile-namespace: zuno-ai-run
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

3. **Publish `mistral-large-latest` and `gpt-oss-120b` as `ExternalModel` +
   `MaaSModelRef`**, bringing both under the same governance plane as local
   models, with **no change to which upstream endpoint each one calls**:

   ```yaml
   apiVersion: maas.opendatahub.io/v1alpha1
   kind: ExternalModel
   metadata:
     name: mistral-large
     namespace: zuno-ai-run
   spec:
     endpoint: api.mistral.ai
     provider: mistral
     targetModel: mistral-large-latest
     credentialRef:
       name: llm-provider-mistral-maas   # mirror Secret, see below
   ---
   apiVersion: maas.opendatahub.io/v1alpha1
   kind: ExternalModel
   metadata:
     name: gpt-oss-120b-ovhcloud
     namespace: zuno-ai-run
   spec:
     endpoint: oai.endpoints.kepler.ai.cloud.ovh.net
     provider: openai-compatible
     targetModel: gpt-oss-120b
     credentialRef:
       name: llm-provider-ovhcloud-maas   # mirror Secret, see below
   ```

   Each is paired with its own `MaaSModelRef` (`modelRef.kind: ExternalModel`)
   in the existing `range .Values.maas.models` loop
   (`gitops/charts/models/templates/maas.yaml`), and its own
   `MaaSSubscription` set, **reusing the exact per-group pattern already in
   production** for local models (`values.yaml`'s `maas.models[].
   subscriptions`): `group: agent_tekos` (priority 10), `group: sales`
   (priority 1), and a catch-all `user:
   system:serviceaccount:zuno-ai-run:ai-gateway` (priority 100) - not a
   single shared subscription.

   **Explicit decision: `mistral` stays on its native API** -
   `api.mistral.ai`, not OVHcloud. Only `gpt-oss-120b` uses OVHcloud. Wrapping
   `mistral` in `ExternalModel` changes its governance, not its endpoint or
   credential.

   **Secret key mismatch.** `ExternalModel.spec.credentialRef` requires a
   Secret with a data key literally named `api-key`; the existing
   `ExternalSecret`-managed Secrets (`llm-provider-mistral`,
   `llm-provider-ovhcloud`) use `api_key`. Per ADR-0416/ADR-0415's
   already-settled principle ("one key per account, not per model" -
   not reopened here), a **dedicated mirror Secret** is created by a new
   Helm template (`gitops/charts/models/templates/externalmodel-*.yaml`),
   sourced from the same Vault path (`providers/mistral`,
   `providers/ovhcloud`) as a second `ExternalSecret` target with the
   required key name - rather than editing the existing `ExternalSecret`'s
   key name and risking every current direct-call consumer.

   **Finage's exclusion from `gpt-oss-120b`** (ADR-0416,
   `zuno.model.local_only: true`) stays enforced **only** in `ai-gateway`'s
   own routing/classification layer, not duplicated into
   `MaaSAuthPolicy.spec.subjects`. Zuno's classification is already the
   stricter outer policy (ADR-0521's Security considerations framing);
   duplicating the exclusion into MaaS would create a second source of
   truth that can silently drift from the first.

   **Known unresolved risk, inherited from ADR-0201**: MaaS's subscription
   selection keys on `<modelRef namespace>/<modelRef name>`, while KServe's
   own adopted-Gateway publication used `publishers/<ns>/<model>` for a
   local `LLMInferenceService` - a mismatch that cost two days to debug for
   `gpt-oss-20b`. An `ExternalModel` has no KServe workload to adopt a route
   from, so it is **not known** whether the same mismatch class applies, or
   whether `maas-controller` computes route identity differently for this
   backend kind. This must be verified live (see Acceptance criteria) before
   either `MaaSSubscription` can be trusted to actually gate traffic.

4. **Activate the existing `via_maas` SaaS path in `ai-gateway`, then retire
   the direct-call branches (full cutover).** Set
   `MAAS_EXTERNAL_EGRESS_ENABLED=true`; add `via_maas: true` and
   `maas_model_ref: <published-name>` to the `mistral` and
   `ovhcloud-gpt-oss-120b` entries in `platform/ai-gateway/
   provider-routing.yaml`. `maas_adapter.py`'s existing `chat_model_via_maas`
   transport (already proven for local models under ADR-0521) requires no
   new adapter code - only its third, currently-closed gate needs opening.
   Once a live smoke test confirms both models answer correctly through
   MaaS (Acceptance criteria), remove the old direct-`ChatOpenAI`/
   `ChatMistralAI` branches for these two providers from
   `components/ai-gateway/app/providers.py` in a follow-up phase of the same
   WP-106 - this is a full cutover, not a permanent dual path (unlike
   ADR-0521's own local-model fallback, which is direct-Service, not a
   second SaaS credential path, and is explicitly kept).

## Consequences

Local models gain the same Dashboard hardware-profile display as manually
deployed ones, closing a real operator-confusion gap (this ADR's own
trigger: Granite's crash was invisible as a GPU problem until the profile's
`spec.identifiers` were read directly). `mistral` and `gpt-oss-120b` gain
group-based access control and rate limiting equivalent to local models,
removing the last two SaaS providers that bypassed MaaS governance
entirely. The cost: a mirror Secret per externally-published model (until/
unless the `api-key` key-naming requirement is relaxed upstream), and a
firm dependency on `maas-controller`'s undocumented route-identity behavior
for a backend kind (`ExternalModel`) this platform has never exercised
before - the live verification in Acceptance criteria is not optional
diligence, it is this ADR's central open question.

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

## Security considerations

No new Vault path is introduced - both mirror Secrets source from the
already-existing `providers/mistral`/`providers/ovhcloud` paths, preserving
ADR-0416/ADR-0415's "one key per account" principle. `ExternalModel.spec.
provider` has no CRD-level validation (confirmed via dry-run) - its
correctness is a runtime concern, not an admission-time guarantee.
Removing the direct-call branches in Decision 4 shrinks `ai-gateway`'s own
credential surface for these two providers once the cutover completes.

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

Beyond the Standard clauses - live verification, required before `Status`
can move to `Implemented`:

- Dashboard shows a hardware profile badge for all five annotated
  InferenceServices, matching Granite's presentation.
- `oc apply --dry-run=server` (or equivalent) confirms both `HardwareProfile`
  CRs and both `ExternalModel` CRs are schema-valid on the live cluster.
- The exact Secret key name (`api-key`) is confirmed live by a successful,
  real completion request through each `MaaSModelRef` - not just a `Ready`
  status.
- The MaaS route-identity question flagged in Decision 3 is resolved by
  observation (inspect the generated route/subscription-selection identity
  for each `ExternalModel`-backed `MaaSModelRef` and confirm it matches what
  `MaaSAuthPolicy`/`MaaSSubscription` actually key on).
- A live negative test confirms Finage is still denied `gpt-oss-120b` after
  cutover.
- A live test per persona group (`agent_tekos`, `sales`, catch-all) confirms
  the expected `MaaSSubscription` priority/quota is the one actually
  enforced.
- The direct-call branches for `mistral`/`ovhcloud-gpt-oss-120b` are removed
  from `providers.py` only after the above pass - not before.

## References

- Work package: [WP-106](../roadmap/work-packages/wp-106-rhoai-hardware-profiles-and-maas-external-models.md).

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md)
  - the MaaS governance plane this extends, and the source of the
    route-identity risk flagged in Decision 3.
- [ADR-0416](0416-consume-gpt-oss-120b-via-ovhcloud-ai-endpoints.md) - the
  OVHcloud credential/endpoint and Finage exclusion this ADR reuses without
  reopening.
- [ADR-0521](0521-route-local-model-traffic-through-maas.md) - the local-model
  MaaS cutover and per-group `MaaSSubscription` pattern this ADR extends to
  external models.
- [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md)
  - the MIG partitioning strategy the two `HardwareProfile` CRs describe.
