# ADR-0412: Serve gpt-oss-20b on the unmanaged full-GPU node

- **Status:** Superseded by ADR-0414
- **Target:** v0.4
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team
- **Superseded:** 2026-08-20 by [ADR-0414](0414-consolidate-zuno-ai-run-into-three-tiered-mig-predictors.md)

## Context

The platform gains a second local chat model, `gpt-oss-20b` (13.8GB MXFP4
weights, staged at `s3://zuno-demo-rag-corpus/models/gpt-oss-20b/` on
2026-08-18), so that reasoning-heavy agent tasks can prefer it over
`qwen2.5-7b-instruct` — most importantly on C3/local-only turns
([ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md))
where until now qwen was the *only* candidate. The ai-gateway side of this
(the `local-gpt-oss` provider entry and the per-(agent,task)
`preferences:` mechanism in `policies/model-routing/model-routing-policy.yaml`)
reorders but never widens classification eligibility; this ADR covers only
where the model's GPU comes from.

**All sanctioned capacity is taken.** [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md)'s
all-balanced MIG partition on the permanent g7e.4xlarge (2x `1g.24gb` +
1x `2g.48gb`) is fully allocated — qwen chat on the 48GB slice,
embeddings and the MaaS backend on the 24GB ones — and the
`zuno-ai-run-gpu-cap` ResourceQuota sits exactly at those limits.
Verified live 2026-08-18.

Options weighed:

1. **Take the MaaS backend's 24GB slice** (`maas.enabled: false`) — free,
   inside the ADR-0351 contract, but removes the ADR-0201 governance demo
   (currently blocked on the payload-processing mTLS issue recorded on
   ADR-0201, but expected to resume).
2. **Scale `zuno-gpu-c` to 1** — a second all-balanced g7e.4xlarge,
   ~$2.9k/mo for a model that needs 14 of its 96GB.
3. **Use the unmanaged workergpu node** `ip-10-18-31-252` (g7e.2xlarge,
   IPI machineset `demo222-kpkqk-workergpu-eu-west-2a`): MIG-disabled,
   advertises one whole `nvidia.com/gpu`, 0 allocated, untainted, driver
   stack healthy — an idle 96GB GPU the demo is already paying for.

## Decision

**Option 3.** The operator chose to use the idle, already-billing GPU
rather than sacrifice the MaaS demo or pay for a second node.

1. `gitops/charts/models` `gptOssModel` (ServingRuntime
   `vllm-gpt-oss-runtime` + InferenceService `gpt-oss-20b` + its own
   unconditional S3 credentials pair + NetworkPolicy) requests
   `nvidia.com/gpu: "1"` — a full GPU, not a MIG slice. That request is
   itself the scheduling steer: the MIG node exposes only `mig-*`
   resources, so the only node that can satisfy it is the workergpu node.
2. `gitops/charts/namespaces` `openshiftAi.gpuQuota` raises
   `nvidia.com/gpu` from `"0"` to `"1"` — the one sanctioned exception to
   ADR-0351's "whole GPUs in zuno-ai-run are a config error" rule. It
   stays a hard cap: a second full-GPU request is still refused at
   admission.

## Accepted risks (and their remediations)

- **The node is unmanaged and ADR-0351 expects it gone.** ADR-0351
  decision 7 leaves the IPI `workergpu` machinesets "live at replicas 0,
  unmanaged by this repo"; this node exists in deviation from that.
  Anyone reconciling the machinesets to the ADR deletes the node and
  gpt-oss-20b goes Pending (nothing else can satisfy `nvidia.com/gpu`).
  Remediation is to re-choose capacity: flip to option 1 (swap
  `gptOssModel.resources` to `nvidia.com/mig-1g.24gb` and disable MaaS)
  or option 2 — and return the quota exception to `"0"` if the full-GPU
  path is abandoned. This ADR supersedes decision 7's "replicas 0"
  expectation for as long as gpt-oss-20b serves there.
- **`gpu-driver-upgrade-state=upgrade-failed` node label.** The driver
  daemonset, device plugin and cuda-validator were all verified healthy
  live (2026-08-18); the label records a past upgrade attempt. Watch the
  first rollout; if the driver wedges, the node reboot/delete path is the
  standard GPU-operator remediation.
- **Ephemeral disk headroom.** ~66GB allocatable vs ~17.7GB vLLM image +
  ~13.8GB S3 storage-initializer download (per pod (re)start) + driver
  artifacts — workable but monitored at rollout, the same failure class
  that originally motivated the qwen PVC
  (`gitops/charts/models/values.yaml` modelStorage history).
- **A 96GB GPU for a 14GB model** is deliberate waste-tolerance: the node
  is already billing and otherwise idle. `maxModelLen: 32768` spends some
  of the surplus on reasoning-task context; revisit if the node gains
  other tenants.
