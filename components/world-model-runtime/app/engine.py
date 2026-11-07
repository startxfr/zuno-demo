"""World engine adapters (ADR-0604 D2): Waypoint-1.5 on CUDA, or a CPU mock.

Both take an RGB uint8 image (H, W, 3) to start or edit the world and return a
batch of frames (N, H, W, 3) per step. Waypoint-1.5 takes NO text
(prompt_conditioning: null): prompts reach the world only as images, through a
FLUX edit spliced with `splice` (ADR-0604 D3).
"""
from __future__ import annotations

import math
import time
from typing import Optional, Protocol

import numpy as np

from app.config import Settings
from app.controls import Ctrl

FRAMES_PER_STEP = 4  # Waypoint-1.5 temporal compression


class WorldEngineAdapter(Protocol):
    name: str
    frames_per_step: int

    def reset(self, image: np.ndarray) -> None:
        """Forget the previous world and start from this image."""

    def splice(self, image: np.ndarray) -> None:
        """Insert an edited image as the latest context, keeping the history."""

    def step(self, ctrl: Ctrl) -> np.ndarray:
        """Generate the next frames, shape (frames_per_step, H, W, 3), uint8."""

    def close(self) -> None:
        ...


def _stamp(frame: np.ndarray, label: str) -> np.ndarray:
    """A visible, honest watermark (ADR-0604 D7: never pass a mock off as inference)."""
    try:
        from PIL import Image, ImageDraw

        img = Image.fromarray(frame)
        draw = ImageDraw.Draw(img)
        draw.rectangle((8, 8, 8 + 9 * len(label), 30), fill=(0, 0, 0))
        draw.text((14, 12), label, fill=(255, 210, 0))
        return np.asarray(img)
    except Exception:  # pragma: no cover - Pillow is a dependency, this is belt and braces
        frame[8:30, 8:200] = (0, 0, 0)
        return frame


class MockEngine:
    """CPU stand-in: pans, zooms and turns the current image with the controls.

    Not a world model. Its frames carry a SIMULATED watermark, and it exists so
    the session, encoder, browser and policy paths are tested without a GPU.
    """

    name = "mock"
    frames_per_step = FRAMES_PER_STEP

    def __init__(self, settings: Settings):
        self.width, self.height = settings.width, settings.height
        self.step_seconds = settings.mock_step_seconds
        self.base: Optional[np.ndarray] = None
        self.x = self.y = 0.0
        self.zoom = 1.0
        self.t = 0

    def reset(self, image: np.ndarray) -> None:
        self.base = _fit(image, self.width, self.height)
        self.x = self.y = 0.0
        self.zoom = 1.0
        self.t = 0

    def splice(self, image: np.ndarray) -> None:
        self.base = _fit(image, self.width, self.height)

    def step(self, ctrl: Ctrl) -> np.ndarray:
        if self.base is None:
            raise RuntimeError("reset() first")
        started = time.perf_counter()
        forward = (87 in ctrl.button) - (83 in ctrl.button)
        strafe = (68 in ctrl.button) - (65 in ctrl.button)
        frames = []
        for _ in range(self.frames_per_step):
            self.t += 1
            self.zoom = min(2.0, max(1.0, self.zoom + 0.01 * forward))
            self.x += 6 * strafe + 40 * ctrl.mouse[0]
            self.y += 20 * ctrl.mouse[1]
            frame = _view(self.base, self.x, self.y, self.zoom)
            # A drifting horizon band so a static scene still visibly animates.
            band = int((math.sin(self.t / 15) + 1) * 0.5 * (self.height - 4))
            frame[band:band + 2, :, :] = 255 - frame[band:band + 2, :, :]
            frames.append(_stamp(frame, f"SIMULATED (mock engine) t={self.t}"))
        spent = time.perf_counter() - started
        if spent < self.step_seconds:
            time.sleep(self.step_seconds - spent)
        return np.stack(frames)

    def close(self) -> None:
        self.base = None


def _fit(image: np.ndarray, width: int, height: int) -> np.ndarray:
    if image.shape[:2] == (height, width):
        return np.ascontiguousarray(image[..., :3])
    from PIL import Image

    return np.asarray(Image.fromarray(image[..., :3]).resize((width, height)))


def _view(base: np.ndarray, x: float, y: float, zoom: float) -> np.ndarray:
    h, w = base.shape[:2]
    shifted = np.roll(base, (int(y) % h, -int(x) % w), axis=(0, 1))
    if zoom <= 1.001:
        return shifted.copy()
    ch, cw = int(h / zoom), int(w / zoom)
    top, left = (h - ch) // 2, (w - cw) // 2
    crop = shifted[top:top + ch, left:left + cw]
    rows = (np.arange(h) * ch // h).clip(0, ch - 1)
    cols = (np.arange(w) * cw // w).clip(0, cw - 1)
    return crop[rows][:, cols]


class WaypointEngine:
    """Overworld world_engine at the pinned commit, offline, on CUDA."""

    name = "waypoint-1.5-1b"
    frames_per_step = FRAMES_PER_STEP

    def __init__(self, settings: Settings):
        import torch  # heavy imports stay out of the mock path
        from world_engine import CtrlInput, WorldEngine

        self._torch, self._ctrl_cls = torch, CtrlInput
        self.width, self.height = settings.width, settings.height
        self.engine = WorldEngine(
            str(settings.waypoint_dir),
            quant=settings.quant,
            # Local autoencoder: snapshot_download fails offline and world_engine
            # falls back to the path it was given.
            model_config_overrides={"ae_uri": str(settings.taehv_path)},
            device="cuda",
        )

    def _batch(self, image: np.ndarray):
        frame = _fit(image, self.width, self.height)
        return self._torch.from_numpy(np.repeat(frame[None], self.frames_per_step, axis=0))

    def reset(self, image: np.ndarray) -> None:
        self.engine.reset()
        self.engine.append_frame(self._batch(image))

    def splice(self, image: np.ndarray) -> None:
        self.engine.append_frame(self._batch(image))

    def step(self, ctrl: Ctrl) -> np.ndarray:
        out = self.engine.gen_frame(ctrl=self._ctrl_cls(
            button=set(ctrl.button), mouse=ctrl.mouse, scroll_wheel=ctrl.scroll_wheel))
        return out.cpu().numpy()

    def close(self) -> None:
        self.engine = None
        self._torch.cuda.empty_cache()


def build_engine(settings: Settings) -> WorldEngineAdapter:
    return WaypointEngine(settings) if settings.engine == "waypoint" else MockEngine(settings)
