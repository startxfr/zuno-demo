"""Image generation and world edits (ADR-0604 D3): FLUX.2 klein 4B on CUDA, or a CPU mock.

`generate` creates the first frame of a world from a prompt; `edit` rewrites the
current frame from a prompt, which is how a mid-session prompt reaches
Waypoint-1.5 (it takes no text). Local only: there is no remote fallback.
"""
from __future__ import annotations

import hashlib
from typing import Optional, Protocol

import numpy as np

from app.config import Settings


class ImageGenerator(Protocol):
    name: str

    def generate(self, prompt: str, seed: int, width: int, height: int) -> np.ndarray:
        """RGB uint8 (height, width, 3)."""

    def edit(self, image: np.ndarray, prompt: str, seed: int) -> np.ndarray:
        """RGB uint8, same size as `image`."""


def _color(prompt: str) -> np.ndarray:
    digest = hashlib.sha256(prompt.encode()).digest()
    return np.array([digest[0], digest[1], digest[2]], dtype=np.float32)


class MockFlux:
    """Deterministic stand-in: a gradient seeded by the prompt, with the prompt written on it."""

    name = "mock"

    def generate(self, prompt: str, seed: int, width: int, height: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        top, bottom = _color(prompt), _color(prompt[::-1] + str(seed))
        ramp = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
        image = top * (1 - ramp) + bottom * ramp
        noise = rng.normal(0, 6, (height, width, 1)).astype(np.float32)
        image = np.clip(np.broadcast_to(image, (height, width, 3)) + noise, 0, 255).astype(np.uint8)
        return _caption(image, f"MOCK IMAGE: {prompt[:60]}")

    def edit(self, image: np.ndarray, prompt: str, seed: int) -> np.ndarray:
        tint = _color(prompt)
        edited = np.clip(image.astype(np.float32) * 0.6 + tint * 0.4, 0, 255).astype(np.uint8)
        return _caption(edited, f"MOCK EDIT: {prompt[:60]}")


def _caption(image: np.ndarray, text: str) -> np.ndarray:
    from PIL import Image, ImageDraw

    img = Image.fromarray(image)
    draw = ImageDraw.Draw(img)
    y = img.height - 34
    draw.rectangle((8, y, 8 + 7 * len(text), y + 22), fill=(0, 0, 0))
    draw.text((14, y + 4), text, fill=(255, 255, 255))
    return np.asarray(img)


class Flux2Klein:
    """black-forest-labs/FLUX.2-klein-4B (Apache-2.0), diffusers layout from the S3 mirror."""

    name = "flux2-klein-4b"

    def __init__(self, settings: Settings):
        import torch
        from diffusers import Flux2KleinPipeline

        self._torch = torch
        self.steps, self.guidance = settings.flux_steps, settings.flux_guidance
        self.pipe = Flux2KleinPipeline.from_pretrained(
            str(settings.flux_dir), torch_dtype=torch.bfloat16, local_files_only=True
        ).to("cuda")

    def _run(self, prompt: str, seed: int, width: int, height: int, image: Optional[np.ndarray] = None):
        from PIL import Image

        kwargs = {}
        if image is not None:
            kwargs["image"] = [Image.fromarray(image)]
        generator = self._torch.Generator("cuda").manual_seed(seed)
        result = self.pipe(
            prompt=prompt, height=height, width=width, num_inference_steps=self.steps,
            guidance_scale=self.guidance, generator=generator, **kwargs,
        )
        return np.asarray(result.images[0].convert("RGB"))

    def generate(self, prompt: str, seed: int, width: int, height: int) -> np.ndarray:
        return self._run(prompt, seed, width, height)

    def edit(self, image: np.ndarray, prompt: str, seed: int) -> np.ndarray:
        h, w = image.shape[:2]
        return self._run(prompt, seed, w, h, image=image)


def build_image_generator(settings: Settings) -> ImageGenerator:
    return Flux2Klein(settings) if settings.image == "flux2" else MockFlux()
