# ADR-0301: Introduce LoRA and PEFT model customization

- **Status:** Superseded in part by ADR-0526 for the adapter objective and serving mechanism (decisions 1 and 5); the static-selection, artifact-registration and classification-inheritance rules (decisions 2-4) remain in effect and are now live-verified (WP-133, 2026-09-05): a genuine non-merged adapter (`tekos-lora`, Model Registry version `wp126-20260904-201830`) was statically selected via `loraAdapters`, loaded by vLLM's native multi-LoRA serving, and served a real completion at `/v1/models`/`/v1/completions`. Prior status for the record: Partially implemented - serving configuration and classification gating merged.
- **Target:** v0.3
- **Date:** 2026-08-12
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.3-roadmap entry
(`../roadmap/adr-decisions-v0.3.md`) to a full record, since `ansible/roles/mlops`
(ADR-0056's `run` component list) needs a real design to scaffold
against rather than staying a registered-but-empty contract. This ADR
adds the capability to customize a deployed base model with LoRA/PEFT
adapters; it deliberately does **not** cover how those adapters get
trained (ADR-0302), loaded dynamically at request time (ADR-0303), or
chosen by a routing policy (ADR-0304) - each stays its own decision so
this one doesn't grow into an unreviewable bundle.

1. **Serving mechanism** - adapters are served through the existing
   vLLM `ServingRuntime` (`gitops/charts/models`, `servingRuntimeName:
   vllm-runtime`, `image.vllm: quay.io/modh/vllm:rhoai-2.16-cuda`)
   using vLLM's native multi-LoRA support (`--enable-lora`,
   `--lora-modules`), not a second `InferenceService` per adapter. This
   is additive to the existing chart, not a parallel serving path: one
   base-model deployment can carry several registered adapters.
2. **Adapter selection is static in this ADR** - which adapter (if any)
   applies to a given request is fixed at deployment/config time
   (`gitops/charts/models/values.yaml`), the same way the base model
   choice is today. Dynamic, per-request adapter selection is ADR-0303's
   explicit scope, not this one's - keeping the two separate lets
   ADR-0303 be rejected or delayed without unwinding this ADR's serving
   mechanism.
3. **Adapters are versioned, registered artifacts** - produced by
   ADR-0302's training pipeline and pushed to the OpenShift AI Model
   Registry, which is already `managementState: Managed` in this
   platform (`gitops/charts/openshift-ai/values.yaml`,
   `modelregistry.registriesNamespace: zuno-ai-build`). An adapter is
   referenced by registry name/version in `models/values.yaml`, the same
   way container images are referenced by tag elsewhere in this repo
   (ADR-0115) - no adapter is ever loaded from an unversioned or
   untracked location.
4. **Classification propagates to the adapter, not just its outputs** -
   an adapter trained (even partially) on C2 or C3 source data inherits
   that classification for the adapter artifact itself, computed the
   same way ADR-0034 computes effective classification from complete
   context. A C2/C3-classified adapter may only be loaded into a serving
   path an agent is already authorized to reach under ADR-0021's C1/C2/C3
   routing - it does not bypass or widen that routing, it is bound by it.
5. **Starting candidate: Comage** - per the original roadmap entry,
   domain/jargon adaptation for sales-deal conversations is the first
   concrete use case ADR-0302's pipeline should target once built, since
   Comage is the next agent in ADR-0326's generalization order to reach
   real usage volume.

## Alternatives considered

- **Full fine-tuning per agent** - rejected: duplicates the full base
  model per agent (storage and serving cost), and risks base-model
  capability drift that a small adapter avoids by construction.
- **Prompt-engineering only** (each agent's `prompts/` directory) -
  already in use and not replaced by this ADR, but insufficient on its
  own for consistent domain jargon/style adaptation at the token-
  distribution level; LoRA is additive to prompting, not a replacement
  for it.
- **A second `InferenceService` per adapter** - rejected: multiplies
  KServe/vLLM deployments linearly with adapter count for no serving
  benefit, when vLLM already supports multi-adapter serving from one
  deployment.

## Security considerations

An adapter is a classified artifact per point 4 above - Model Registry
entries need the same `acl_groups`-style access reasoning ADR-0046
already applies to RAG chunks, evaluated when this ADR is implemented.
Loading an adapter must not be a path that grants a lower-privileged
serving deployment access to higher-classification behavior than its
existing C1/C2/C3 routing would otherwise allow.

## Operational considerations

Rollback is adapter-level, not base-model-level: removing or
downgrading an adapter reference in `models/values.yaml` and letting
ArgoCD sync is the expected recovery path, without touching the
underlying `InferenceService`/`ServingRuntime`. Adapter loading/serving
health becomes part of `make d1 check models` once implemented.

## Evolution (2026-08-15)

Point 3's Model Registry reference used this Decision text's original
`zuno-ai-build` namespace assumption, written before ADR-0331's
reversion. The live `gitops/charts/openshift-ai/values.yaml`
(`modelregistry.registriesNamespace`) is `rhoai-model-registries`, RHOAI's
own true default - `components/mlops/`'s push-registry stage (WP-34)
reads this from the real Helm value via an env var
(`MODEL_REGISTRY_NAMESPACE`), never hardcoding either string, so this
correction needs no further ADR/code change to stay accurate.

See [Standard clauses](README.md#standard-clauses) for Context,
Consequences, Migration/evolution and Acceptance criteria.

## Related ADRs

- [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md) - Use OpenShift AI model serving for local inference
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md) - Route models according to C1/C2/C3 classification
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md) - Compute effective classification from the complete context
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md) - Make RAG retrieval metadata-aware and bilingual (precedent for metadata-driven access control)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md) - Use immutable and verifiable software supply chain artifacts (precedent for versioned/registered artifacts)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) - Restructure deployment into Day 0 / Day 1 sequencing (`mlops` run component)
- [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md) - Build dataset-to-model MLOps pipelines (produces the adapters this ADR serves)
- [ADR-0303](../roadmap/adr-decisions-v0.3.md#adr-0303-support-dynamic-lora-adapter-loading) - Support dynamic LoRA adapter loading (later, out of this ADR's scope)
- [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md) - Generalize the Tekos vertical slice to the four remaining agents (Comage, the starting candidate)
