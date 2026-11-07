# WP-231: World-model GPU runtime image (delivers ADR-0604 D2, D3, D4)

- **State:** Repo work in review
- **ADRs:** ADR-0604
- **Depends on:** WP-230
- **Blocks:** WP-232, WP-234
- **Estimated files touched:** ~25

> Execute this brief as a standalone task from the repository root.

## Goal

One container that owns the GPU: FLUX.2 klein for the first image, Waypoint-1.5 for the interactive loop, and the H.264
encoder. It is built and tested without a GPU through mock adapters behind the same interfaces.

## ADR references

ADR-0604 D2, D3 (single-GPU contract), D4 (encoder, coalescing), §4.2, §4.3, §6.3, §10.

## Repo changes

1. `components/world-model-runtime/` (Python 3.12, FastAPI, uvicorn):
   - internal API: `POST /internal/image`, `WS /internal/session` (controls and world-edit requests in; state events
     and H.264 Annex-B access units out), `/healthz`, `/readyz` (true only after warm-up), `/metrics`;
   - world edit (ADR-0604 D3): on a prompt change, FLUX.2 klein edits the current frame and the result is spliced with
     `append_frame`; the session reports `RECONDITIONING` meanwhile. Waypoint-1.5 takes no text, so there is no
     `set_prompt` call anywhere;
   - `WorldEngineAdapter` with `MockEngine` (CPU, procedural 720p frames that react to the controls, watermarked
     "SIMULATED") and `WaypointEngine` (`world_engine` at the pinned commit, quantization from config);
   - `ImageGenerator` (`generate` and `edit`) with `MockFlux` (preset images, a visible tint for edits) and
     `Flux2Klein` (pinned diffusers);
   - `FrameEncoder` on PyAV, whose wheels bundle FFmpeg with both `h264_nvenc` and `libx264` (no PyNvVideoCodec
     needed): `auto` opens NVENC and falls back to x264, and the choice is exported;
   - 4 frames per step paced to the measured step time; last-value control coalescing; one lease; browser key codes mapped
     to `CtrlInput` server-side; `HF_HUB_OFFLINE=1`, model paths from the cache directory.
2. `Dockerfile`: `python:3.12-slim` from the `zuno-ai-build` mirror, torch CUDA wheels pinned to a version that supports
   sm_120 with driver 595, `world_engine` at the pinned commit, diffusers pinned, non-root, no build-time downloads of weights.
3. Tests (pytest, mock adapters only): protocol, coalescing, lease, state machine, encoder round trip decoded with PyAV;
   registered in `.github/workflows/lint.yml`.
4. `platform/world-model/tests/gpu-smoke-job.yaml`: a Job on the world-model node that prints a JSON report:
   `nvidia-smi`, torch device capability, NVENC probe, N Waypoint steps per quantization (bf16, intw8a8, fp8w8a8, nvfp4)
   with step time and peak VRAM, one FLUX image and one FLUX edit with latency and VRAM, a splice with `append_frame`
   followed by 100 steps, both models resident together.
5. `ansible/roles/world_model_build/` from `ansible/roles/token_proxy_build/tasks/build.yml` through
   `ansible/tasks/apply_openshift_build.yml` (signed by the existing chain); `.github/workflows/build-publish.yml` matrix
   entry; `components/README.md` row. Record the licence of the bundled encoder library.

## Result (2026-11-07)

`components/world-model-runtime` (app, 13 mock tests passing, two hashed locks, Dockerfile with sha256-checked
`world_engine`/`taehv`/`gemlite` archives), `app/smoke.py`, `platform/world-model/fetch_models.py` (S3 to the model cache,
pinned revisions only, run in the mirrored storage-initializer image), `platform/world-model/tests/gpu-smoke-job.yaml`,
`ansible/roles/world_model_build`, the build matrix entry and the lint.yml test step. The world-model-web image joins
the build role in WP-234.

## Operator steps (with the user's go)

Before the first build, check the ephemeral storage of the nodes that run builds (a CUDA image is about 10 GB; DiskPressure
on a master has cascaded before). Then `make d2 build world-model`.

## Verification

Tests pass locally; the image runs on CPU and `python -c "import torch, world_engine, diffusers"` succeeds in it; the
smoke Job manifest passes `oc apply --dry-run=client`.
