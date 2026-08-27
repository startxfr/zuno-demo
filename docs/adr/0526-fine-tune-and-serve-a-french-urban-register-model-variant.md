# ADR-0526: Fine-tune and serve a French urban-register model variant (`-wesh`)

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-27
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0301](0301-introduce-lora-and-peft-model-customization.md) in part (decisions 1 and 5 — the serving mechanism and the starting candidate's objective) and [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md) in part (decisions 2 and 4 — dataset sourcing and the training objective). Every other decision point of both records remains in effect.

## Context

ADR-0301 and ADR-0302 designed a LoRA capability around one concrete objective:
train a `comage-lora` adapter on Comage's own RAG corpus and evaluation
transcripts, for sales-deal *domain-jargon* adaptation. WP-34 merged that design
in full — `components/mlops/`'s four-stage CLI, `gitops/charts/mlops/`, the
`--enable-lora`/`--lora-modules` wiring and the classification gate in
`gitops/charts/models/`.

It never ran once. The `Pipeline` CR `mlops` exists in `zuno-mlops` with **zero
versions and zero runs**, and the objective it was built for has no data behind
it: Comage's two declared knowledge domains resolve to `rag-sales` (table
present, **0 rows**) and `rag-project` (**no `document_embeddings` table at
all**). The only populated corpus on this platform is `knowledge.tech`, which
belongs to Tekos.

This ADR replaces that objective rather than reviving it. The new one is a
**style** adaptation, not a domain adaptation: a model that answers in
contemporary French urban register ("wesh"), served under its own name beside
its unmodified base, with two agents re-routed to it. It is a demonstration of
the platform's fine-tune → evaluate → register → promote → route loop end to
end, on an objective whose training data exists, whose result is immediately
visible to a human, and whose regression risk is measurable.

Three facts from the live platform shape every decision below.

**A LoRA needs an unquantized checkpoint.** Of the three local models, only one
qualifies:

| Model | S3 size | Architecture | Quantization |
|---|---|---|---|
| `qwen3.6-27b-instruct` | 30.9 GB | `Qwen3_5ForConditionalGeneration`, dense, 64 layers | **FP8** |
| `gpt-oss-20b` | 13.8 GB | `GptOssForCausalLM`, **MoE, 32 experts** | **MXFP4** |
| `qwen3.5-9b` | 19.3 GB | `Qwen3_5ForConditionalGeneration`, dense, 32 layers | **none (bf16)** |

**There is exactly enough GPU capacity, and no more.** Two permanent MIG nodes,
`all-balanced` (`2× mig-1g.24gb + 1× mig-2g.48gb` each):

| Node | AZ | `1g.24gb` #1 | `1g.24gb` #2 | `2g.48gb` |
|---|---|---|---|---|
| `ip-10-18-67-65` | eu-west-2c | embeddings | gpt-oss-20b | *free* |
| `ip-10-18-15-25` | eu-west-2a | *free* | *free* | qwen36-27b-instruct |

`ResourceQuota/zuno-ai-run-gpu-cap` stands at `requests.mig-1g.24gb: 2/3` and
`requests.mig-2g.48gb: 1/2`.

**The training corpus already exists**, staged at
`s3://zuno-corpus/qwen-wesh-training-corpus.tgz`: `qwen-urban-fr-corpus/` in
OpenAI Messages JSONL (one single-turn `user`/`assistant` conversation per line),
**716 train / 113 validation / 79 test**, split at *seed* level so paraphrases of
a seed never cross a split boundary, plus a 21-rule style specification. Two of
its rules are load-bearing for the gate below: *"Facts and reasoning must remain
correct: style changes, information quality does not"* and *"parler différemment
sans raisonner différemment"*.

## Decision

1. **Objective and base model** — LoRA/PEFT fine-tuning of `Qwen/Qwen3.5-9B`
   (staged at `s3://zuno-demo-rag-corpus/models/qwen3.5-9b`, already this
   platform's training base per ADR-0518 decision 3), followed by a **merge**
   (`merge_and_unload()`) into a standalone bf16 checkpoint. This replaces
   ADR-0301 decision 5's `comage-lora` domain-jargon objective. Comage remains
   the first candidate agent; only the objective changes.

2. **Naming** — the merged model is served as `qwen3.5-9b-wesh`
   (`LLMInferenceService` `qwen35-9b-wesh`), and its unmodified base is served
   alongside it as `qwen3.5-9b` (`LLMInferenceService` `qwen35-9b`). The
   `servedModelName`/`inferenceServiceName` split follows ADR-0518 decision 1:
   dots are stripped from the Kubernetes object name, never from the served model
   id. Both models run simultaneously, on different nodes, so the variant can be
   compared against its own base rather than against a different model.

3. **Dataset source — a new collection surface, deliberately** — training draws
   from the staged style corpus named in the Context, read via a new
   `MLOPS_STYLE_CORPUS_S3URI`. This **overrides ADR-0302 decision 2**, which
   restricted datasets to `document_embeddings` plus evaluation transcripts and
   stated that "no new data-collection surface is introduced". A register-shift
   objective cannot be expressed in either of those sources. The corpus is
   **C1**: synthetic conversational style material carrying no business,
   customer or financial content. The merged model therefore inherits C1 under
   ADR-0301 decision 4's artifact-classification rule, and is eligible for C1,
   C2 and C3 routing like every other local provider.

4. **Merged weights, not an adapter served on the shared runtime** — this
   **overrides ADR-0301 decision 1** and reverses the rejection its
   "Alternatives considered" recorded against "a second `InferenceService` per
   adapter". That rejection was correct for its own premise — many adapters over
   one base, where an extra deployment buys nothing. Here the extra deployment
   *is* the requirement: a distinct, routable model id and node-level isolation
   from the base, so the two can serve concurrently and be compared. vLLM's
   `--lora-modules` gives neither — it exposes the adapter from the same process
   as the base. This is **not** the full fine-tuning ADR-0301 also rejected: it
   is a rank-8 LoRA whose result is merged, so training cost stays adapter-scale
   and only the serving artifact is a full checkpoint.

5. **Serving and placement** — two additional `LLMInferenceService` objects in
   `gitops/charts/models/`. `qwen3.5-9b-wesh` takes the free `2g.48gb` slice on
   `ip-10-18-67-65`; `qwen3.5-9b` takes a free `1g.24gb` slice on
   `ip-10-18-15-25`. The variant gets the larger slice because it carries all of
   Comage's traffic. The existing **soft** anti-affinity (`spreadAcrossGpuNodes`,
   selector `kserve.io/component: workload`,
   `preferredDuringSchedulingIgnoredDuringExecution`, topology
   `kubernetes.io/hostname`) is reused unchanged — a `required` term would
   contradict ADR-0351 decision 1 and WP-086, which both chose packing onto a
   survivor over leaving a pod `Pending`. Node separation is guaranteed here by
   slice availability, not by the affinity term.

6. **MaaS publication** — both new models are published through MaaS per ADR-0521
   decisions 5 and 6: a `maas.models[]` entry each (`publishedName`,
   `backendInferenceServiceName`, `subscriptions[]` including the `-ai-gateway`
   grant, `authPolicy`), the `MaaSModelRef`/`MaaSSubscription`/`MaaSAuthPolicy`
   objects, route rules through `_llmisvc-route.tpl`, a NetworkPolicy admitting
   `maas-default-gateway`, and the repeated `--served-model-name` triple. Each
   model gets a `-maas` provider ordered immediately before its direct twin, so
   "MaaS unreachable → the same model still answers directly" stays a
   configuration outcome rather than new code.

7. **Routing** — Comage prefers `qwen3.5-9b-wesh` first on **all four** of its
   tasks; Tekos places it **second**, after its existing first choice, on all
   four of its own. Because `preferences:` is keyed by the `(agent, task)` tuple
   and entries without a `task` are rejected, this is expressed as one entry per
   task, not an agent-level default. Fallback needs no new mechanism: the
   gateway's candidate loop advances on exception, so an unavailable model is
   skipped by exhaustion.

8. **The quality gate covers style *and* substance** — a new register-conformance
   evaluation is added **in addition to** the existing acceptance gate, which
   must stay green unchanged. ADR-0302 decision 5 is extended, not bypassed:
   promotion requires **both** halves to pass, and the pipeline fails the run if
   either does not. This is a direct consequence of the corpus's own rules 14 and
   20 — a model that adopts the register while losing factual accuracy is a
   failed candidate, not a stylistic success.

9. **Promotion stays human-reviewed** — ADR-0302 decision 7 is unchanged. A
   passing, registered model reaches serving only through a GitOps pull request
   editing `gitops/charts/models/values.yaml`. The pipeline never writes to that
   file.

## Alternatives considered

- **Fine-tune `qwen3.6-27b-instruct`, the model Comage actually uses today** —
  rejected on mechanics, not on merit. The checkpoint is FP8. Training would
  require dequantizing to bf16 (~54 GB, beyond the burst node's 64 GiB host-RAM
  headroom) and then **re-quantizing to FP8** after the merge to fit back into
  the 48 GB slice that is the only anti-affine slot free. This repo has no
  quantization capability, and adding one is a larger decision than this ADR.
- **Fine-tune `gpt-oss-20b`** — rejected. MXFP4 weights on a 32-expert MoE is the
  least-supported LoRA path in `peft`/`transformers`, and anti-affinity would
  force the variant onto `ip-10-18-15-25`, where only `1g.24gb` slices are free,
  making re-quantization mandatory there too.
- **Serve the adapter on a second vLLM instance of the same base** (keeping
  ADR-0301 decision 1 intact, `--enable-lora` on a dedicated pod) — rejected. It
  costs the same GPU, still requires an adapter-download mechanism that does not
  exist in the chart, and leaves the instance exposing the base model id as well
  as the variant's, which makes routing and per-model telemetry ambiguous for no
  compensating benefit.
- **Serve only the variant, falling back to the existing `qwen3.6-27b-instruct`**
  — rejected by explicit operator decision. It would have preserved one free
  `1g.24gb` slice and a stronger fallback model, but forgoes the base-vs-variant
  comparison that is the point of the exercise.

## Consequences

- The MIG `ResourceQuota` for `zuno-ai-run` reaches `3/3` on `mig-1g.24gb` and
  `2/2` on `mig-2g.48gb`. It does **not** need raising, but it becomes exactly
  saturated: the next GPU workload requires either a quota change plus capacity,
  or the retirement of an existing model.
- **ADR-0351 decision 5's single-node survivability property is lost.** That
  decision recorded that "either node alone holds all three model workloads
  (1× 2g.48gb + 2× 1g.24gb = 3/3 slices)". With five GPU workloads across six
  slices, losing a node now leaves at least two models unschedulable until
  capacity returns. This is accepted, not overlooked.
- `qwen3.5-9b` in a 24 GB slice is the tight case: 19.3 GB of bf16 weights, plus
  a KV cache of ~32 KB/token (only 8 of 32 layers are `full_attention`, with
  `num_key_value_heads: 4` and `head_dim: 256`; the 24 `linear_attention` layers
  hold a constant-size state) — about 1 GB at a 32 768-token context. It fits
  with a high `--gpu-memory-utilization` and low concurrency; its
  `--max-model-len` is reduced accordingly. The variant, in 48 GB, has ample room.
- Adding providers changes the resolved model chain for **every** agent, so all
  eight generated OKF authorization-matrix blocks must be regenerated.
- ADR-0303's dynamic per-request adapter selection is neither implemented nor
  contradicted; it is bypassed. Routing to a separately served model uses the
  pre-existing provider/preference mechanism, so `adapters:` stays empty and the
  `serves_adapters` flag keeps its current meaning.

## Security considerations

The register shift must not become a classification shift. The corpus is C1 by
construction and adds no business content, so the merged model inherits C1 and
its `eligible_for` list is the same as any local provider's. But because Comage
routes to it by default, the variant will answer **C3** turns — Comage's
`compare-historical-deals` escalates to C3 under ADR-0034 whenever
`knowledge.sxa-legacy` contributes. That is legitimate for a local provider, and
it is precisely why decision 8 keeps the substance half of the gate mandatory:
a style model that degrades reasoning on C3 financial and legacy data is a
security-relevant regression, not a cosmetic one.

The corpus's own rule set anticipates the adjacent risk and must be verified
rather than assumed: rules 11-13 forbid slangifying technical terminology, code,
YAML, JSON, SQL and shell syntax, and rule 19 forbids adding insults, aggression
or discriminatory content to simulate the register. The register-conformance
evaluation asserts the first; the acceptance gate's existing security checks
remain unchanged and continue to assert identity propagation and authorization
behavior, which a model swap must not perturb.

## Operational considerations

Training runs on the existing MIG-disabled burst node via the ADR-0351 decision 4
scale-from-zero path, unchanged — a whole `nvidia.com/gpu`, the
`zuno.io/gpu-burst` toleration, and the `machine.startx.io/group=gpu-burst`
selector. No machineset, MIG partition or permanent node is added.

Rollback is per-model and GitOps-native: remove the variant's entry from
`gitops/charts/models/values.yaml` and its provider entries from
`platform/ai-gateway/provider-routing.yaml`, then let ArgoCD sync. Comage's
preference lists degrade to their existing chains by candidate exhaustion, so a
partial rollback (providers removed, model still running) is safe in either
order.

Two known defects in the WP-34 code stand between this decision and a first run,
and are in scope for the work package implementing it: `mlops.py` loads the base
with `AutoModelForCausalLM` and builds a `LoraConfig` with no `target_modules`,
neither of which is valid for a `Qwen3_5ForConditionalGeneration` checkpoint
whose weight map is `model.language_model.layers.*` with mixed
`self_attn`/`linear_attn` projections and an `mtp.*` head; and nothing in the
repository compiles or uploads a `PipelineVersion`, which is why the pipeline has
never run.

Catastrophic forgetting is the principal training risk: 716 single-turn casual
exchanges can erode business and technical competence. Mitigations are a low LoRA
rank, few epochs, and the substance half of the gate as the enforcing check.

## Acceptance criteria

Beyond the Standard clauses:

- A pipeline run completes all stages and registers a model version whose
  artifact URI points at the merged checkpoint in S3.
- The run fails, and pushes nothing to the registry, if **either** the
  register-conformance evaluation **or** the existing acceptance gate fails.
- Both models report `Ready`, on different nodes, and each lists its own served
  model id on `/v1/models`.
- A Comage turn is answered by `qwen3.5-9b-wesh` in the target register, and
  falls back to the next candidate when the variant is made unavailable.
- A Tekos turn is answered by its existing first choice while the variant is
  healthy, and by the variant when the first choice is unavailable.

## References

- Corpus: `s3://zuno-corpus/qwen-wesh-training-corpus.tgz` — `qwen-urban-fr-corpus/`,
  716/113/79 OpenAI Messages JSONL, seed-level splits, 21-rule style specification.
- Base weights: `s3://zuno-demo-rag-corpus/models/qwen3.5-9b` (bf16, 19.3 GB).
- Work package: [WP-087](../roadmap/work-packages/wp-087-french-urban-register-model.md).

See [Standard clauses](README.md#standard-clauses) for Alternatives considered,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0301](0301-introduce-lora-and-peft-model-customization.md) - Introduce LoRA and PEFT model customization (superseded in part: decisions 1 and 5)
- [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md) - Build dataset-to-model MLOps pipelines (superseded in part: decisions 2 and 4)
- [ADR-0303](0303-support-dynamic-lora-adapter-loading.md) - Support dynamic LoRA adapter loading (bypassed, not contradicted)
- [ADR-0305](0305-introduce-automated-model-benchmarking.md) - Introduce automated model benchmarking (a candidate model needs a benchmark artifact before a routing-policy change)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md) - Route models according to C1/C2/C3 classification
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md) - Compute effective classification from the complete context
- [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md) - Share RTX PRO 6000 GPUs via NVIDIA MIG (decision 5's survivability property is given up here)
- [ADR-0419](0419-split-model-preference-into-preferred-fallback-with-prompt-slot-overrides.md) - Split model preference into preferred/fallback
- [ADR-0518](0518-modernize-local-models-qwen36-chat-qwen3-embeddings-qwen35-training.md) - Modernize the local model fleet (decision 3 supplies this ADR's training base)
- [ADR-0521](0521-route-local-model-traffic-through-maas.md) - Route ai-gateway's local model traffic through MaaS (binds both new models)
