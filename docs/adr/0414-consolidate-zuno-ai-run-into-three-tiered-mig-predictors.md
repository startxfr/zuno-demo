# ADR-0414: Consolidate zuno-ai-run into three tiered MIG predictors

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-20
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0412](0412-serve-gpt-oss-20b-on-the-unmanaged-full-gpu-node.md) (its full-GPU exception)
- **Amends:** [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md) decision 7 (the unmanaged IPI workergpu machinesets no longer stay unmanaged)

## Context

`zuno-ai-run` currently runs four GPU predictors across two physical RTX PRO
6000 Blackwell cards (96GB each), verified live 2026-08-20:

- **Card A** (`zuno-gpu-a`, managed by `gitops/charts/machines`, ADR-0351):
  MIG `all-balanced` = 2x `mig-1g.24gb` + 1x `mig-2g.48gb`, 100% allocated —
  `qwen25-7b-instruct` (2g.48gb), `embeddings` (`hf://BAAI/bge-small-en-v1.5`,
  1g.24gb), `qwen25-7b-instruct-maas-backend` (1g.24gb).
- **Card B** (the IPI `demo222-kpkqk-workergpu-eu-west-2a` machineset,
  **unmanaged** per ADR-0351 decision 7, used anyway per ADR-0412): whole
  `nvidia.com/gpu: 1`, MIG-disabled — `gpt-oss-20b`, using ~16-24GB of a
  96GB card. ADR-0412 names this "deliberate waste-tolerance" and states
  its own remediation: shrink gpt-oss-20b to a MIG slice once its real
  footprint is known. That footprint is now confirmed against public specs
  (MXFP4, ~13.8GB on disk, 16-24GB VRAM at runtime) — well within
  `mig-1g.24gb`.

Two more facts drove this decision:

- This GPU's MIG implementation caps at **four quarter-slices**, with only
  three valid shapes: `1g.24gb`, `2g.48gb`, and `4g.96gb` (100% of the card
  — there is no partial-card whole-instance size). Any "give tier 1 room to
  spare while still using most of a card" design has to stay at `2g.48gb`,
  not attempt a fractional whole-card size.
- vLLM pins each server process to one runner (`generate` xor `pooling`) —
  confirmed against current vLLM docs. A checkpoint cannot serve both
  embedding and chat requests from one process even if the weights would
  support both, so "one predictor" doing both roles means one pod running
  two containers on a shared MIG slice, not one model doing two jobs.
- No sourcing policy in this repo requires S3 over `hf://` for served
  models — the repo's actual "sovereignty" concept (ADR-0021/0114/0201,
  C1/C2/C3 classification) governs external-provider request routing, not
  local model weight provenance. `embeddings`' live `hf://` pull was a
  deliberate, documented exception for its small size, not a policy
  violation. This decision moves it to S3 anyway, because it will share a
  pod with a chat container and a stalled/slow `hf://` pull at pod start
  would take that container down with it — an operational reason, not a
  sovereignty one.

## Decision

**Replace the four predictors with three, on both cards under MIG
management, no repartitioning of the already-managed card required:**

| Tier | Role | Slice | Model |
|---|---|---|---|
| 1 | Strategic reasoning / advanced conversation | `mig-2g.48gb` | `Qwen3-32B` (fp8/AWQ) |
| 2 | Merged embeddings + everyday chat, 2 containers in 1 pod | `mig-2g.48gb` | `Qwen3-Embedding-0.6B` + `Qwen3-8B` |
| 3 | `maas-default-gateway-istio` backend | `mig-1g.24gb` | `gpt-oss-20b` (unchanged weights, resized only) |

Physical layout:

- **Card A** keeps its `all-balanced` MIG profile completely unchanged.
  Tier 1 takes the `2g.48gb` slot (replacing `qwen25-7b-instruct`); tier 3
  takes one `1g.24gb` slot (replacing the MaaS backend). The other
  `1g.24gb` slot (today's `embeddings`) goes free.
- **Card B** is adopted into `gitops/charts/machines` management for the
  first time and gets `all-balanced` applied. Tier 2 takes its `2g.48gb`
  slot. Both `1g.24gb` slots go free.

Net: three `1g.24gb`-equivalent quarter-slices free across the cluster
after this lands. Because Card A's profile never changes — only which
pods are scheduled into its existing slices — it avoids ADR-0351's "a node
is never repartitioned while busy, MIG layout changes mean node
replacement" cost; only Card B pays that cost, and only once, as part of
being adopted.

All three new/changed model weights are staged in
`s3://zuno-demo-rag-corpus/models/<name>/` by hand, from the operator's
workstation — the same undocumented-but-consistent process already used
for `qwen2.5-7b-instruct` and `gpt-oss-20b` (no HF→S3 job exists in this
repo; this decision does not add one).

## Alternatives considered

- **Keep gpt-oss-20b on the unmanaged whole GPU and only redesign Card A**
  — rejected: leaves ADR-0412's "node disappears if anyone reconciles
  machinesets to ADR-0351" risk standing indefinitely, and caps total
  usable capacity at Card A's four quarter-slices alone.
- **`gpt-oss-120b` for tier 1** — already ruled out
  (`gitops/charts/models/values.yaml` comment: staged in S3 as "transit
  storage for the operator's own workstation only, NOT servable on this
  cluster's GPUs").
- **Llama 4 Scout (INT4) for tier 1 on a full `4g.96gb` card** — considered
  for its higher capability ceiling; rejected in favor of `Qwen3-32B` on
  `2g.48gb` to keep tier 1 license-clean (Meta's Llama 4 Community License
  carries usage/geographic clauses; every other model in this decision is
  Apache-2.0/MIT) and to leave headroom on that card rather than consuming
  it entirely — a `4g.96gb` slice leaves nothing else schedulable on that
  card by construction.
- **Literal single-model embedding+chat merge** (e.g. a GRIT-style unified
  checkpoint) — rejected: vLLM's one-runner-per-process constraint makes
  this either infeasible or requires abandoning vLLM for tier 2, a much
  larger change for uncertain quality benefit.

## Accepted risks (and their remediations)

- **Tier 2's two-container-per-predictor shape has no precedent in this
  repo.** Every existing `InferenceService` here uses KServe's standard
  single-`kserve-container` predictor. Whether KServe's predictor spec
  cleanly supports a second application container alongside the
  storage-initializer / `kube-rbac-proxy` sidecars this repo already
  attaches is **not yet verified**. Remediation: validate this narrowly
  (a throwaway two-container InferenceService) before committing the real
  tier-2 manifest; if KServe's predictor spec fights a second container,
  the fallback is two separate `InferenceService`s pinned to the same MIG
  slice via pod affinity — which breaks the "one predictor" framing but
  keeps the resource math intact.
- **`Qwen3-32B` at fp8/AWQ inside `mig-2g.48gb` is sized from published specs,
  not measured on this hardware.** ~32GB weights against a 48GB slice
  leaves ~16GB for KV cache/context — expected workable but unverified
  live. Remediation: load-test tier 1 before cutting traffic to it;
  fall back to a smaller Qwen3 dense size or a lower context ceiling if
  it's tight.
- **Three new manual S3 uploads** (`Qwen3-32B` fp8 ~32GB, `Qwen3-8B` ~16GB,
  `Qwen3-Embedding-0.6B` ~1.3GB), each done by hand with no automation,
  same as every prior model in this bucket. Remediation: none planned —
  matches existing accepted practice; a future ADR can add a real upload
  job if this keeps recurring.
- **Card B's first-time MIG partition requires a node replacement, and
  `gpt-oss-20b` (moving to Card A, not staying on Card B) is its only
  current tenant.** Card B must be fully drained before it can be safely
  repartitioned — a live node is never repartitioned in place (ADR-0351).
  Remediation, in order: (1) retire the standalone MaaS backend
  (`templates/maas.yaml`) to free Card A's `1g.24gb` slot that gpt-oss-20b
  is moving into; (2) resize and move `gpt-oss-20b` onto that freed Card A
  slot, now also serving the MaaS role, and verify it; this leaves Card B
  fully idle; (3) only then bring Card B under `machines` management and
  apply `all-balanced` — a node replacement with nothing running on it
  yet, not a live repartition; (4) land tier 2 on Card B's new `2g.48gb`
  slot; (5) land tier 1 on Card A's `2g.48gb` slot, independently of the
  above, whenever `Qwen3-32B` is staged. Sequence tier-by-tier, not as one
  atomic change.
- **Retiring ADR-0412's `nvidia.com/gpu: "1"` quota exception** in
  `gitops/charts/namespaces/values.yaml` must happen in the same change
  that removes the last whole-GPU request, or an already-scheduled pod
  keeps running against a quota line nothing else needs — cosmetic risk
  only, but worth sequencing correctly to keep `docs check` clean.

## Related ADRs

- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md)
- [ADR-0412](0412-serve-gpt-oss-20b-on-the-unmanaged-full-gpu-node.md)

See [Standard clauses](README.md#standard-clauses) for Consequences, Security/Operational
considerations, Migration/evolution, Acceptance criteria and Review evidence.
