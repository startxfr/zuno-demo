# Model bench on the 24 GB MIG slice (2026-10-25)

Question (from the Lightspeed tool-result inspection work): can ONE light local model, sovereign, fit a 24 GB `mig-1g.24gb` slice with much more input
and output context than today, serve Lightspeed and zuno-demo, and be the base to fine-tune the wesh variant?

Method: throwaway namespace `zuno-bench` (the `zuno-ai-run-gpu-cap` quota is full), plain vLLM Pods with the same `rhaii/vllm-cuda-rhel9` image as the live
models, pinned to the GPU node with the free slice, one candidate at a time, deleted after each run; no route, model or quota touched. The client ran on the
workstation through `oc port-forward` (TTFT includes the tunnel, the same for every candidate). Weights come from our S3 bucket
(`s3://zuno-demo-sources/models/...`), not from Hugging Face at serving time.

| | (a) gpt-oss-20b, 131072 | (c) qwen3.5-9b, 32768 | (b) qwen3.6-27b, 4-bit, 49152 |
|---|---|---|---|
| Weights in GPU | 13.8 GiB | 17.7 GiB | 17.9 GiB (bitsandbytes 4-bit from the BF16 checkpoint) |
| KV cache (tokens) | 6.43 GiB, 276,212 (2.1x at 131k) | 2.77 GiB, 85,395 (2.6x at 32k) | 3.19 GiB, 49,152 (1.0x at 49k; 64k does not fit: needs 4.16 GiB) |
| Classifier call (json_schema, max_tokens 128), 5 runs | 5/5 with request `reasoning_effort=low` (44-61 tok); 1/5 with the server default | 5/5 with `enable_thinking=false` default (15-16 tok) | 5/5 with `enable_thinking=false` default (16-23 tok) |
| Needle, real prompt tokens | found at 23k, 46k, 92k | found at 14k, 32k | found at 14k, 32k, 46k |
| Tokens/s, 1 then 4 concurrent | 85, 234 | 22.5, 81.5 | 15.7, 30.7 |
| TTFT, 1 then 4 concurrent | 0.11 s, 0.17 s | 0.11 s, 0.52 s | 0.24 s, 0.77 s |
| 5 Red Hat docs questions (expected terms found, of 15) | 13 | 11 | 14 |

Notes:
- gpt-oss-20b: vLLM `--default-chat-template-kwargs '{"reasoning_effort":"low"}'` is accepted but has no effect; only the top-level request field works. Lightspeed sends
  it itself through `reasoningConfig.effort` (see lightspeed-tool-result-inspection-2026-10-25.md).
- qwen3.6-27b in our S3 (`models/qwen3.6-27b-instruct/`, the live copy) is an FP8 checkpoint of 29 GB: it does not fit 24 GB and cannot be quantized online. A BF16 copy was
  downloaded by an in-cluster Job (bounded retries) to **`s3://zuno-demo-sources/models/qwen3.6-27b-bf16/`** (27 files, 55.6 GB, `Qwen/Qwen3.6-27B`), additive, nothing existing touched.
  It is also the right base for fine-tuning. First load takes about 7 minutes (S3 download plus 4-bit quantization).
- The qwen models run with `--enforce-eager` here (as live); CUDA graphs would raise their tokens/s.
- Not measured: the 4-bit quality loss against the FP8 copy beyond the five docs questions, a larger qwen3.5-9b context (KV allows about 85k tokens in total), tool-calling accuracy.

Reading: gpt-oss-20b is the only candidate with a long context (131k) and high throughput on 24 GB, but needs `reasoning_effort` per request. qwen3.5-9b is light and
simple but short-context and slow. qwen3.6-27b fits only in 4-bit, with about 49k tokens, one long request at a time, and is the slowest.
