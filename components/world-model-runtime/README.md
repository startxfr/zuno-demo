# world-model-runtime

ADR-0604, WP-231. The one container that owns the world-model GPU: FLUX.2 klein 4B for the first image and every world
edit, Overworld Waypoint-1.5-1B for the interactive frames (4 per step, 720p), and the H.264 encoder that feeds the
browser's WebCodecs decoder. Internal only: `world-model-web` (WP-234) is its sole client, and holds the users, leases,
quotas and prompt screening.

| Adapter | GPU node | CPU / tests |
|---|---|---|
| `WORLD_MODEL_ENGINE` | `waypoint` (world_engine `68b31639`, `WORLD_MODEL_QUANT` none/intw8a8/fp8w8a8/nvfp4) | `mock`: the image panned and zoomed by the controls, watermarked SIMULATED |
| `WORLD_MODEL_IMAGE` | `flux2` (diffusers `Flux2KleinPipeline`, 4 steps) | `mock`: a gradient seeded by the prompt |
| `WORLD_MODEL_ENCODER` | `auto`: `h264_nvenc` (PyAV's FFmpeg, needs `NVIDIA_DRIVER_CAPABILITIES=...,video`), else `libx264` | `x264` |

| `WORLD_MODEL_ANCHOR_SECONDS` | `3` in the chart: every 3 s of walking FLUX redraws the frame from the scene prompt and it is spliced back (ADR-0604 D9); `0` = off | unused by the mock tests unless set |
| `WORLD_MODEL_AE_RAW` | `true` in the chart: no bilinear 720p/512x1024 round trip, GPU bicubic upscale | n/a |

Waypoint-1.5 takes no text (`prompt_conditioning: null`). A mid-session prompt is a **world edit**: FLUX edits the current
frame and `append_frame` splices it, while the session reports `RECONDITIONING`.

## API (see `app/main.py`)

`/healthz`, `/readyz` (models loaded and warmed), `/metrics`, `GET /internal/status`, `POST /internal/image`,
`POST /internal/worlds`, `DELETE /internal/worlds/{id}`, `WS /internal/worlds/{id}/stream`. Video messages are binary:
`b"V"`, a flags byte (bit 0 = keyframe), the pts in microseconds (8 bytes), then one Annex-B access unit. Set
`WORLD_MODEL_INTERNAL_TOKEN` to require `X-World-Runtime-Token` on every call.

## Run and test without a GPU

```bash
cd components/world-model-runtime
pip install -r requirements.txt pytest
python -m pytest -q tests                      # 13 tests on the mock adapters
WORLD_MODEL_ENGINE=mock WORLD_MODEL_IMAGE=mock uvicorn app.main:get_app --factory --port 8080
```

## Image and models

`Dockerfile` installs two hash-checked locks (`requirements.txt`, `gpu/requirements.txt`, ADR-0603 M20), then the pinned
`world_engine`, `taehv` and `gemlite` archives after a sha256 check. Weights are never baked in: an init container runs
`gitops/charts/world-model/files/fetch_models.py` to copy the revisions of `platform/world-model/models.lock.yaml` from S3.
`app/smoke.py` is the GPU smoke test (`platform/world-model/tests/gpu-smoke-job.yaml`, WP-232).
