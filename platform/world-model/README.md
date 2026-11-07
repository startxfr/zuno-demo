# World model (ADR-0604)

Runtime contract and pinned assets of the world-model experience: Waypoint-1.5-1B (interactive frames) and
FLUX.2 klein 4B (initial image and mid-session world edit), on one full RTX PRO 6000 in a node that exists only while
`zuno_world_model_enabled` is on. Decision record: [ADR-0604](../../docs/adr/0604-introduce-an-interactive-generative-world-model-experience.md).

## Pinned weights (`models.lock.yaml`)

Every file the runtime loads is mirrored to `s3://zuno-demo-sources/models/world-model/<org>/<repo>/<revision>/` and
listed with its size and sha256 in [`models.lock.yaml`](models.lock.yaml) (WP-230). The cluster never downloads from
Hugging Face and holds no HF token. The copy is made off-cluster (in-cluster HF pulls hang), each file streamed at the
pinned revision and checked against the HF API size, the S3 object length and, for LFS files, the HF-published sha256.

| Repository | Revision | Licence | Used for |
|---|---|---|---|
| `Overworld/Waypoint-1.5-1B` | `391f9282` | Apache-2.0 | `config.yaml` + `model.safetensors`, the only files `world_engine` loads |
| `Overworld-Models/taehv1_5` | `a0253886` | MIT | the autoencoder, loaded with `torch.load(..., weights_only=True)` |
| `black-forest-labs/FLUX.2-klein-4B` | `e7b7dc27` | Apache-2.0 | the diffusers layout (`Flux2KleinPipeline`); the single-file checkpoint is not mirrored |

Not mirrored, on purpose: Waypoint-1.1-Small (its autoencoder is CC-BY-NC-SA-4.0) and `google/umt5-xl` (only needed for
text-conditioned checkpoints). Waypoint-1.5 takes no text (`prompt_conditioning: null`), so prompts act through FLUX
edits (ADR-0604 D3).

## Loading without the network

`world_engine` (commit `68b31639`, GPL-3.0, like this repository) tries `huggingface_hub.snapshot_download` and falls back
to a local path when it fails, so the runtime runs with `HF_HUB_OFFLINE=1` and passes local directories:

```python
WorldEngine("/models/Overworld/Waypoint-1.5-1B",
            model_config_overrides={"ae_uri": "/models/Overworld-Models/taehv1_5/taehv1_5.pth"},
            device="cuda")
```

## Upstream dependency pins to honour in the runtime image (WP-231)

From `world_engine`'s `pyproject.toml` at the pinned commit: `torch==2.11.0`, `triton==3.6.0`, `taehv` at
`7dc60ec6`, `gemlite` at `ebfcc197`, `tensordict==0.10.0`, `accelerate==1.12.0`, `transformers>=5.3.0`,
`huggingface-hub>=1.7.0`.
