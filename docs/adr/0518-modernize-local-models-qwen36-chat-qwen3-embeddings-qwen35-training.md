# ADR-0518: Modernize the local model fleet — Qwen3.6-27B chat, Qwen3-Embedding-0.6B, Qwen3.5-9B training base

- **Status:** Implemented (live-verified 2026-08-26 - all three legs: `qwen3.6-27b-instruct` and
  `qwen3-embedding-0.6b` both serving `Ready`, and `rag.document_embeddings` is `vector(1024)`
  carrying a re-ingested corpus, so migration 006 and the big-bang re-embed both completed)
- **Target:** v0.4
- **Date:** 2026-08-25
- **Decision owners:** Zuno Demo architecture team

## Context

The three locally-served GPU workloads dated from very different model
generations: the fleet chat model was Qwen2.5-7B-Instruct (late 2024,
BF16, `--max-model-len=8192`), RAG embeddings ran BAAI/bge-small-en-v1.5
(384-dim, **English-only** — against a live corpus that is largely French
Confluence content), and the mlops LoRA pipeline fine-tuned
ibm-granite/granite-3.1-2b-instruct pulled from huggingface.co at run
time (in-cluster HF downloads hang unreliably here — the exact reason
every *served* model was already staged in S3). The fourth GPU workload,
gpt-oss-20b (ADR-0414), is current (Aug 2025, no successor as of this
writing) and is untouched.

A capacity review against the ADR-0351 MIG layout (one permanent
g7e.4xlarge, RTX PRO 6000 96GB, all-balanced: 1× 2g.48gb + 2× 1g.24gb)
showed headroom to modernize without touching machinesets, MIG
partitioning or quotas: the 2g.48gb slice can hold a ~28GB FP8 27B-class
model, the embedding slice's occupant is ~1.2GB either way, and the
MIG-disabled burst node's full 96GB absorbs a 9B training base.

## Decision

1. **Chat/agents:** `Qwen/Qwen3.6-27B-FP8` (official FP8 checkpoint,
   ~28GB) on the existing 2g.48gb slice, served as
   **`qwen3.6-27b-instruct`** (InferenceService
   `qwen36-27b-instruct`), `--max-model-len=32768` (was 8192),
   `--tool-call-parser=qwen3_xml` (was hermes) and
   `--reasoning-parser=qwen3` (new: Qwen3.6 is hybrid-thinking; without
   it `<think>` blocks leak into agent-visible content). The id is
   renamed **cleanly across every consumer** (ai-gateway, agent-runtime,
   provider-routing, policies, OKF schema, LM-Eval, ansible precheck) —
   no compatibility alias serving the old name for a 4x-larger different
   model.
2. **RAG embeddings:** `Qwen/Qwen3-Embedding-0.6B` (1024-dim,
   multilingual, MTEB-multilingual leader among open models) served as
   **`qwen3-embedding-0.6b`**; the InferenceService keeps the neutral
   name `embeddings` so the `embeddings-predictor` Service URL never
   changes. Cutover is **big-bang**: a guarded SQL migration
   (`006_embedding_1024.sql`) truncates `document_embeddings` and widens
   `vector(384)` → `vector(1024)` in every knowledge-domain database,
   followed by a full re-ingestion — 384-dim and 1024-dim vectors live
   in unrelated spaces, there is nothing to migrate. RAG search is
   degraded between migration and re-ingestion completing (accepted for
   this demo platform). The embedding model also moves from
   `hf://`-at-pod-start to the same staged-in-S3 serving path as every
   other predictor — retiring the last HF-at-runtime dependency in the
   serving plane.
3. **LoRA training base:** `Qwen/Qwen3.5-9B` staged in S3
   (`models/qwen3.5-9b/`, same bucket/credential); `mlops.py` learns to
   resolve an `s3://` `MLOPS_BASE_MODEL` (download via boto3's managed
   transfer, then `from_pretrained` on the local copy — a plain HF repo
   id still passes through). The GPU path now loads in bf16: fp32 for
   9B (~36GB host RAM) would not fit the train pod, and bf16 is the
   checkpoint's native dtype. Train pod memory raised 12/24Gi →
   24/48Gi accordingly; chat predictor limit 32Gi → 48Gi and embedding
   2/4Gi → 3/6Gi for the same weights-transit-host-RAM reason.
4. **No infrastructure change:** machinesets, MIG partition, GPU quotas
   (`mig-2g.48gb:1, mig-1g.24gb:2, nvidia.com/gpu:0`) and the burst
   scale-from-zero mechanism are all untouched.

Weights are streamed HF→S3 out-of-cluster (`curl | aws s3 cp -`,
per-file size-verified against the HF API — the operator workstation has
no 50GB to stage locally, and in-cluster HF pulls hang).

## Alternatives considered

- **Qwen3.6-35B-A3B (MoE)** for chat: better throughput per active
  param, but its Gated-DeltaNet-heavy stack is the newer/riskier vLLM
  path and its Q8 (~37GB) leaves thin KV margin on 48GB. The dense 27B
  also benches better on coding (SWE-bench 77.2 vs 73.4), which Tekos
  exercises hardest. Revisit if concurrency becomes the bottleneck.
- **Gemma 4 31B BF16**: ~62GB — full-GPU only, does not fit any slice;
  would compete with training for the burst node. Rejected for the chat
  slot on capacity, not quality.
- **Keeping the `qwen2.5-7b-instruct` API id** (or dual-alias): zero
  consumer churn, but a demo platform serving a 27B Qwen3.6 under a
  "qwen2.5-7b" name is actively misleading; rejected.
- **Blue/green re-ingestion** (parallel 1024-dim table, switch at the
  end): zero RAG downtime but throwaway dual-write plumbing in
  rag-service/rag-ingestion; big-bang accepted instead.
- **gpt-oss-120b on a second permanent GPU**: deliberately out of scope
  here (no second permanent node exists); noted as the natural next
  step if one is added.

## Verification before implementation

Checked live on 2026-08-25 against the running
`rhaii-early-access/vllm-cuda-rhel9` image (vLLM 0.21.0+rhaiv.10):
`Qwen3_5ForConditionalGeneration` (Qwen3.6-27B's actual architecture —
hybrid linear attention, *not* plain Qwen3 dense) and `Qwen3ForCausalLM`
(the embedding model) are both in `ModelRegistry.get_supported_archs()`;
`qwen3_xml` is in the `--tool-call-parser` choices; `qwen3` resolves in
`ReasoningParserManager`.

## Consequences

- Every consumer routes by `qwen3.6-27b-instruct`; the old id 404s (by
  design — same failure mode the servedModelName comment documents).
- The full corpus must be re-ingested after the schema migration
  (manifest.json deleted to force a full run); LM-Eval's tokenizer
  prefetch path follows the chat model rename.
- The old `models/qwen2.5-7b-instruct/` S3 directory stays as instant
  rollback weights; rollback is `git revert` + re-sync + re-ingestion
  back to 384.
- `HISTORY_TOKEN_BUDGET`'s 1800 default is now conservative rather than
  ceiling-bound (both local models serve 32768); deliberately unchanged.

## Dated progress notes

- 2026-08-25: Phase 0 verifications green (arch/parsers/S3 access), HF→S3
  streaming transfer started, full repo change landed with all four
  touched component test suites passing (mlops 22, ai-gateway 118,
  rag-service 59, rag-ingestion 42, evaluations 37) and the four touched
  charts rendering. Awaiting S3 transfer completion, then deploy +
  re-ingestion + live verification.
- 2026-08-27: closed out to `Implemented`. The note above is superseded - the S3 transfer,
  deploy, re-ingestion and live verification all completed. Confirmed live:
  `qwen36-27b-instruct` and `embeddings` (serving `qwen3-embedding-0.6b`) are both `Ready`, and
  `rag.document_embeddings` in `rag-tech` is `vector(1024)` holding a re-ingested corpus - so
  migration 006's TRUNCATE-then-widen and the big-bang re-embed both ran to completion. The
  empty `rag-sxa-legacy` table is not a gap in this ADR: that re-embed is WP-084's open operator
  action, and `rag-sales` is empty because `domains.sales` ships `enabled: false` per ADR-0218.
