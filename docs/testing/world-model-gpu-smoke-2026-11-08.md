# World-model GPU smoke test, 2026-11-08 (WP-232)

Measured on the on-demand GPU node of ADR-0604, by `platform/world-model/tests/gpu-smoke-job.yaml` running
`python -m app.smoke` from the runtime image. Every figure below comes from this GPU; none is a vendor figure.

**Decision: GO.** The go criteria of WP-232 (about 20 displayed FPS at 720p, an encoder that keeps up, a FLUX edit plus
splice in about 2 seconds or less) are met with a wide margin on the default precision.

## Hardware and stack

| Item | Value |
|---|---|
| Node | `ip-10-18-34-245` (`zuno-gpu-world-model-a`, `g7e.4xlarge`, eu-central-1b), no MIG |
| GPU | NVIDIA RTX PRO 6000 Blackwell Server Edition, 97 887 MiB, compute capability 12.0 (sm_120) |
| Driver, CUDA, torch | 595.91.07, CUDA 13.0, torch 2.11.0+cu130 |
| Runtime image | `world-model-runtime` build 4, digest `sha256:4bd49654…53df4` (signed, keyless) |
| Waypoint steps measured | 100 per precision, 4 frames per step |

## Measurements

| Waypoint precision | Step mean | Step p95 | Frames per second | Splice (`append_frame`) | Step after splice | Peak VRAM with FLUX resident |
|---|---|---|---|---|---|---|
| bf16 (`quant: ""`, the chart default) | 49.6 ms | 50.8 ms | **80.7** | 11.9 ms | 51.4 ms | 23.5 GB |
| `fp8w8a8` | 40.6 ms | 42.0 ms | **98.6** | 12.0 ms | 42.3 ms | 23.5 GB |
| `intw8a8` | not measured | | | | | see below |
| `nvfp4` | not measured | | | | | see below |

| Other measurement | Value |
|---|---|
| Encoder | NVENC, 4.05 ms per frame (the CPU x264 fallback was not needed) |
| FLUX.2 klein 4B, text to image | 1.04 s, 18.3 GB of VRAM |
| FLUX.2 klein 4B, edit of the current frame | 1.16 s |
| Time to splice an edited frame into the running world | 11.9 ms, the next steps stay at the same cost (51.4 ms against 49.6 ms) |
| Copying the three models from S3 into the node-local cache | about 2.5 minutes |
| Whole smoke Job (three engine loads and kernel compilations) | 21 minutes |

Reading: a step is 4 frames, so 49.6 ms per step is the engine producing 80.7 frames per second against 20 needed, and
about 60 for a smooth display. A world edit costs one FLUX call (1.2 s) and a 12 ms splice: the edited frame reaches the
running world well inside the 5 seconds the demo script allows. Both models fit together in 23.5 GB of the 96 GB.

## What did not work, and why it does not matter for the demo

- **`intw8a8`** failed in `gemlite` with `PermissionError: 'gemlite_config.json'`: the library writes its autotune file in
  the current directory, which is read-only in the non-root image. It is a working-directory problem of the smoke Job, not of
  the GPU. bf16 and fp8 already clear the bar, so the runtime does not use it.
- **`nvfp4`** failed with `NameError: name 'nvfp4_quantize' is not defined` inside `world_engine/quantize.py` at the pinned
  commit (the function is not imported there). A defect of the pinned library, not worth a patch: the demo does not need it.
- The inductor log shows several "Runtime error during autotuning, ignoring this choice" lines: candidate kernels that do not
  fit sm_120 are discarded by the autotuner, which then picks one that does. Expected, not an error of the run.

## What the first image build and run taught

- Triton compiles a small C launcher at run time (flex attention, `gemlite`): the image needs `gcc` and `libc6-dev`
  (`CC=gcc`). Without them every Waypoint engine failed with "Failed to find C compiler" (first run of this test).
- `world_engine` cannot be imported in a build pod because `gemlite` queries the CUDA device at import: the image build only
  checks that the packages are present, and the import is proven by this Job.

## Decision for the demo

- Keep `runtime.quant: ""` (bf16): 80.7 FPS leaves a margin over the display rate and avoids an unvalidated precision.
  `fp8w8a8` (98.6 FPS) is the fallback if WP-237 sees dropped frames under load.
- Startup is dominated by kernel compilation, not by the weights: `runtime.startupFailureThreshold: 120` (20 minutes)
  stays. WP-237 measures the real cold start of the pod.
