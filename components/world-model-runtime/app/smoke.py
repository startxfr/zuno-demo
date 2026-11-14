"""GPU smoke test (ADR-0604 WP-232): one JSON report, nothing changed.

    python -m app.smoke            (in the runtime image, on the world-model node)

Env: SMOKE_QUANTS (comma list: none,intw8a8,fp8w8a8,nvfp4), SMOKE_STEPS (default 100).
Measures, on THIS GPU: device and driver, the encoder actually available, FLUX
generate and edit latency, Waypoint step time and peak VRAM per quantization, a
world edit spliced with append_frame followed by more steps, and both models
resident together. Vendor figures from other GPUs are never reported here.
"""
from __future__ import annotations

import dataclasses
import json
import os
import statistics
import subprocess
import sys
import time
import traceback

import numpy as np

from app.config import Settings
from app.controls import Ctrl
from app.encoder import build_encoder


def _nvidia_smi() -> str:
    try:
        return subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,encoder.stats.sessionCount",
             "--format=csv,noheader"], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"unavailable: {exc}"


def _percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def main() -> int:
    import torch

    base = Settings.from_env()
    steps = int(os.getenv("SMOKE_STEPS", "100"))
    quants = [q.strip() for q in os.getenv("SMOKE_QUANTS", "none").split(",") if q.strip()]
    report = {"gpu": _nvidia_smi(), "torch": torch.__version__, "cuda": torch.version.cuda,
              "capability": ".".join(map(str, torch.cuda.get_device_capability())), "steps": steps}

    encoder = build_encoder(base)
    frame = np.zeros((base.height, base.width, 3), dtype=np.uint8)
    started = time.perf_counter()
    for _ in range(120):
        encoder.encode(frame)
    report["encoder"] = {"name": encoder.name, "ms_per_frame": round((time.perf_counter() - started) / 120 * 1000, 2)}

    from app.imagegen import Flux2Klein

    flux = Flux2Klein(base)
    t0 = time.perf_counter()
    image = flux.generate("a snowy medieval village at dusk, cinematic first-person view", 7, base.width, base.height)
    t1 = time.perf_counter()
    edited = flux.edit(image, "the sky turns red and a volcano erupts beyond the village", 8)
    t2 = time.perf_counter()
    report["flux"] = {"generate_s": round(t1 - t0, 2), "edit_s": round(t2 - t1, 2),
                      "vram_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2)}

    from app.engine import WaypointEngine

    report["waypoint"] = {}
    for quant in quants:
        settings = dataclasses.replace(base, quant=None if quant == "none" else quant)
        try:
            torch.cuda.reset_peak_memory_stats()
            engine = WaypointEngine(settings)
            engine.reset(image)
            for _ in range(5):  # compile / warm-up, not measured
                engine.step(Ctrl(button=frozenset({87})))
            times = []
            for i in range(steps):
                ctrl = Ctrl(button=frozenset({87} if i % 20 < 15 else {68}), mouse=(0.1 if i % 10 < 5 else -0.1, 0.0))
                s = time.perf_counter()
                engine.step(ctrl)
                torch.cuda.synchronize()
                times.append(time.perf_counter() - s)
            s = time.perf_counter()
            engine.splice(edited)
            splice_s = time.perf_counter() - s
            after = []
            for _ in range(min(steps, 100)):
                s = time.perf_counter()
                engine.step(Ctrl(button=frozenset({87})))
                torch.cuda.synchronize()
                after.append(time.perf_counter() - s)
            mean = statistics.mean(times)
            report["waypoint"][quant] = {
                "step_ms_mean": round(mean * 1000, 1), "step_ms_p95": round(_percentile(times, 0.95) * 1000, 1),
                "frames_per_second": round(engine.frames_per_step / mean, 1),
                "splice_ms": round(splice_s * 1000, 1),
                "step_ms_mean_after_splice": round(statistics.mean(after) * 1000, 1),
                "peak_vram_gb_with_flux": round(torch.cuda.max_memory_allocated() / 1e9, 2),
            }
            engine.close()
        except Exception as exc:  # noqa: BLE001 - one quantization failing must not hide the others
            report["waypoint"][quant] = {"error": str(exc)[:300], "trace": traceback.format_exc()[-1200:]}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
