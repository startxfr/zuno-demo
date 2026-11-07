"""Runtime settings, read once from the environment (ADR-0604 D2-D4).

The adapters are chosen here, so the same image runs on a CPU laptop with the
mock adapters and on the world-model GPU node with the real ones.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    # "mock" (CPU, procedural frames) or "waypoint" (world_engine on CUDA).
    engine: str = "mock"
    # "mock" (preset-like images) or "flux2" (FLUX.2 klein 4B through diffusers).
    image: str = "mock"
    # "auto" (h264_nvenc when the GPU exposes it, else libx264), "nvenc" or "x264".
    encoder: str = "auto"
    # Root of the model cache filled from S3 (platform/world-model/models.lock.yaml layout).
    model_dir: Path = Path("/models")
    # world_engine quantization: None (bf16), "intw8a8", "fp8w8a8" or "nvfp4".
    quant: Optional[str] = None
    width: int = 1280
    height: int = 720
    # Mock engine only: simulated time per generation step (4 frames).
    mock_step_seconds: float = 0.066
    # Encoder: target bitrate and a keyframe at most every N frames.
    bitrate: int = 6_000_000
    gop_frames: int = 60
    # Prompts reaching the runtime are already screened by world-model-web; this
    # is a last ceiling against oversized payloads.
    max_prompt_chars: int = 600
    # FLUX.2 klein distilled: 4 steps, guidance 1.0 (model card).
    flux_steps: int = 4
    flux_guidance: float = 1.0

    @property
    def waypoint_dir(self) -> Path:
        return self.model_dir / "Overworld" / "Waypoint-1.5-1B"

    @property
    def taehv_path(self) -> Path:
        return self.model_dir / "Overworld-Models" / "taehv1_5" / "taehv1_5.pth"

    @property
    def flux_dir(self) -> Path:
        return self.model_dir / "black-forest-labs" / "FLUX.2-klein-4B"

    @classmethod
    def from_env(cls) -> "Settings":
        quant = os.getenv("WORLD_MODEL_QUANT", "").strip() or None
        settings = cls(
            engine=os.getenv("WORLD_MODEL_ENGINE", "mock").strip(),
            image=os.getenv("WORLD_MODEL_IMAGE", "mock").strip(),
            encoder=os.getenv("WORLD_MODEL_ENCODER", "auto").strip(),
            model_dir=Path(os.getenv("WORLD_MODEL_DIR", "/models")),
            quant=quant,
            width=_int("WORLD_MODEL_WIDTH", 1280),
            height=_int("WORLD_MODEL_HEIGHT", 720),
            mock_step_seconds=_float("WORLD_MODEL_MOCK_STEP_SECONDS", 0.066),
            bitrate=_int("WORLD_MODEL_BITRATE", 6_000_000),
            gop_frames=_int("WORLD_MODEL_GOP_FRAMES", 60),
            max_prompt_chars=_int("WORLD_MODEL_MAX_PROMPT_CHARS", 600),
            flux_steps=_int("WORLD_MODEL_FLUX_STEPS", 4),
            flux_guidance=_float("WORLD_MODEL_FLUX_GUIDANCE", 1.0),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.engine not in ("mock", "waypoint"):
            raise ValueError(f"WORLD_MODEL_ENGINE must be mock or waypoint, not {self.engine!r}")
        if self.image not in ("mock", "flux2"):
            raise ValueError(f"WORLD_MODEL_IMAGE must be mock or flux2, not {self.image!r}")
        if self.encoder not in ("auto", "nvenc", "x264"):
            raise ValueError(f"WORLD_MODEL_ENCODER must be auto, nvenc or x264, not {self.encoder!r}")
        if self.quant not in (None, "intw8a8", "fp8w8a8", "nvfp4"):
            raise ValueError(f"WORLD_MODEL_QUANT {self.quant!r} is not a world_engine quantization")
        if self.width % 16 or self.height % 16:
            raise ValueError("width and height must be multiples of 16")
