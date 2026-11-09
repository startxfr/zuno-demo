"""The one world of this GPU (ADR-0604 §4.2, §4.3, D3, D4).

One runtime pod owns one GPU and at most one streaming world. Every GPU call
(FLUX, Waypoint) runs on a single worker thread, so a world edit can never
overlap a generation step. The loop pipelines like upstream's render loop: the
next step is generated while the previous batch is paced out evenly over the
measured step time, so 4-frame batches play smoothly.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Optional

import numpy as np

from app import metrics
from app.config import Settings
from app.controls import ControlState
from app.encoder import FrameEncoder, build_encoder
from app.engine import WorldEngineAdapter
from app.imagegen import ImageGenerator

logger = logging.getLogger(__name__)


class State(str, Enum):
    NEW = "NEW"
    PREPARING_IMAGE = "PREPARING_IMAGE"
    WARMING_ENGINE = "WARMING_ENGINE"
    READY = "READY"
    STREAMING = "STREAMING"
    RECONDITIONING = "RECONDITIONING"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


class Busy(Exception):
    """The GPU already serves a streaming world."""


class NotFound(Exception):
    """No such world."""


# Binary video message: b"V", flags (bit 0 = keyframe), pts in microseconds (8 bytes), the last control
# sequence the frame reflects (4 bytes, 0xFFFFFFFF = none yet), then the Annex-B payload.
VIDEO_TAG = b"V"
NO_SEQ = 0xFFFFFFFF
HEADER_BYTES = 14


def video_message(payload: bytes, keyframe: bool, pts_us: int, seq: int = -1) -> bytes:
    seq32 = NO_SEQ if seq < 0 else seq % NO_SEQ  # never the marker itself
    return VIDEO_TAG + bytes([1 if keyframe else 0]) + pts_us.to_bytes(8, "big") + seq32.to_bytes(4, "big") + payload


# The anchor prompt, measured 2026-11-09 on the GPU node (closed loop with Waypoint, 42 s walks, several seeds).
# - "first-person view" made FLUX redraw the frame but also draw first-person arms and HUD (Waypoint itself
#   hallucinates hands and weapons while walking: it is trained on game footage; FLUX then keeps them).
# - A camera cue that names no character ("a camera at eye level moving through the scene, only the environment")
#   redraws the frame without the arms in most runs; a few runs keep a Waypoint-made hand as a snow-covered lump.
# - An explicit instruction at the end removes the rest ("Remove any hands, arms, weapons and interface elements."),
#   while a negation ("no hands") is ignored or only partial.
# The scene text must not say "first-person": it is stripped.
ANCHOR_CUE = ", cinematic view from a camera at eye level moving through the scene, only the environment"
ANCHOR_CLEAN = ". Remove any hands, arms, weapons and interface elements."
_POV = re.compile(r",?\s*\b(?:cinematic\s+)?first[- ]person(?:\s+(?:camera\s+)?view)?\b", re.IGNORECASE)
FRAME_RATE = 60


def anchor_prompt(scene: str, last_edit: str, limit: int) -> str:
    """The scene (plus the newest world edit) as a FLUX prompt; "" when the world has no text to anchor on."""
    parts = [_POV.sub("", p).strip(" ,.") for p in (scene, last_edit) if p and p.strip()]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    tail = ANCHOR_CUE + ANCHOR_CLEAN
    return ", ".join(parts)[: max(0, limit - len(tail))].rstrip(" ,") + tail


def edit_size(spec: str):
    """"1024x512" -> (1024, 512); "" -> None (edit at the display size)."""
    if not spec:
        return None
    w, h = spec.lower().split("x")
    return int(w), int(h)


@dataclass
class World:
    world_id: str
    seed: int
    image: np.ndarray
    state: State = State.READY
    prompt_version: int = 0
    controls: ControlState = field(default_factory=ControlState)
    created: float = field(default_factory=time.monotonic)
    scene_prompt: str = ""  # the text the first image came from, for drift anchoring
    last_edit: str = ""  # the newest applied world edit: it becomes part of the scene
    moving_seconds: float = 0.0  # generated video time since the last anchor, counted only while moving
    anchors: int = 0


SendBytes = Callable[[bytes], Awaitable[None]]
SendEvent = Callable[[dict], Awaitable[None]]


class Runtime:
    def __init__(self, settings: Settings, engine: WorldEngineAdapter, images: ImageGenerator):
        self.settings = settings
        self.engine = engine
        self.images = images
        self.gpu = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gpu")
        self.world: Optional[World] = None
        self.streaming = False
        self.encoder_name = "none"
        self._edits: "asyncio.Queue[tuple[int, str]]" = asyncio.Queue()
        self._stop = asyncio.Event()
        self.last_step_seconds = 0.0
        precision = settings.quant or ("bf16" if settings.engine == "waypoint" else "cpu")
        self.precision = precision
        metrics.ENGINE_INFO.labels(engine=engine.name, image=images.name, precision=precision).set(1)

    async def _gpu(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(self.gpu, fn, *args)

    # ------------------------------------------------------------------ worlds
    async def create_world(self, prompt: Optional[str], image_png: Optional[bytes], seed: int) -> World:
        if self.streaming:
            metrics.BUSY_REJECTED.inc()
            raise Busy()
        if prompt is not None and len(prompt) > self.settings.max_prompt_chars:
            raise ValueError("prompt too long")
        if image_png is not None:
            image = _decode_png(image_png)
        elif prompt:
            started = time.perf_counter()
            image = await self._gpu(self.images.generate, prompt, seed, self.settings.width, self.settings.height)
            metrics.IMAGE_SECONDS.labels(kind="generate").observe(time.perf_counter() - started)
        else:
            raise ValueError("a prompt or an image is required")
        await self._gpu(self.engine.reset, image)
        metrics.RESETS.labels(reason="new_world").inc()
        self.world = World(world_id=uuid.uuid4().hex, seed=seed, image=image, scene_prompt=prompt or "")
        return self.world

    async def close_world(self, world_id: str) -> None:
        if not self.world or self.world.world_id != world_id:
            raise NotFound()
        self._stop.set()
        self.world.state = State.CLOSED
        self.world = None

    def request_edit(self, prompt_version: int, prompt: str) -> bool:
        world = self.world
        if world is None or prompt_version <= world.prompt_version or len(prompt) > self.settings.max_prompt_chars:
            return False
        self._edits.put_nowait((prompt_version, prompt))
        return True

    # ------------------------------------------------------------------ stream
    async def stream(self, world_id: str, send_bytes: SendBytes, send_event: SendEvent) -> str:
        """Run one streaming session until stopped; returns the end reason."""
        world = self.world
        if world is None or world.world_id != world_id:
            raise NotFound()
        if self.streaming:
            metrics.BUSY_REJECTED.inc()
            raise Busy()
        self.streaming = True
        self._stop = asyncio.Event()
        self._edits = asyncio.Queue()
        metrics.ACTIVE_SESSIONS.set(1)
        started = time.monotonic()
        reason = "closed"
        encoder: Optional[FrameEncoder] = None
        out: "asyncio.Queue[Optional[bytes]]" = asyncio.Queue(maxsize=12)
        stop = self._stop
        sender = asyncio.create_task(_drain(out, send_bytes, stop))

        raw_send_event = send_event

        async def event(payload: dict) -> None:
            # A closed socket ends the session as a disconnect, never as a world failure.
            try:
                await raw_send_event(payload)
            except Exception:  # noqa: BLE001
                stop.set()

        send_event = event
        try:
            encoder = build_encoder(self.settings)
            if encoder.name != self.encoder_name:
                metrics.ENCODER_INFO.clear()
                metrics.ENCODER_INFO.labels(encoder=encoder.name).set(1)
            self.encoder_name = encoder.name
            world.state = State.STREAMING
            await send_event({"type": "state", "state": world.state.value, "engine": self.engine.name,
                              "image": self.images.name, "encoder": encoder.name, "precision": self.precision})
            # The first frame is the world's image itself: something to see at once.
            pts = self._emit(encoder, world.image, 0, out, keyframe=True)
            reason = await self._loop(world, encoder, out, send_event, pts)
        except Exception as exc:  # noqa: BLE001 - the browser gets an honest FAILED, not a frozen frame
            logger.exception("world stream failed")
            world.state = State.FAILED
            reason = "error"
            await send_event({"type": "state", "state": State.FAILED.value, "message": str(exc)[:200]})
        finally:
            # No await in here: when the server cancels this task (the browser went
            # away), every await under the cancelled scope raises again, and the GPU
            # would stay marked busy forever.
            stop.set()
            while not out.empty():
                out.get_nowait()
            out.put_nowait(None)
            broken = False
            if sender.done() and not sender.cancelled() and sender.exception() is None:
                broken = bool(sender.result())
            else:
                sender.cancel()
            if reason == "closed" and broken:
                reason = "disconnect"
            if encoder:
                encoder.close()
            self.streaming = False
            metrics.ACTIVE_SESSIONS.set(0)
            metrics.STREAM_DISCONNECT.labels(reason=reason).inc()
            metrics.SESSION_DURATION.labels(result=reason).observe(time.monotonic() - started)
            if world.state not in (State.FAILED, State.CLOSED):
                world.state = State.READY
                world.controls.clear()
        return reason

    def stop(self) -> None:
        self._stop.set()

    async def _loop(self, world: World, encoder: FrameEncoder, out, send_event: SendEvent, pts: int) -> str:
        step = asyncio.ensure_future(self._gpu(self._timed_step, world.controls.take()))
        while not self._stop.is_set():
            frames, step_seconds, seq, moving = await step
            metrics.FRAMES_GENERATED.labels(model=self.engine.name, precision=self.precision).inc(len(frames))
            if moving:
                world.moving_seconds += len(frames) / FRAME_RATE
            if not self._edits.empty():
                await self._apply_edit(world, encoder, frames[-1], send_event)
            elif self._anchor_due(world):
                await self._reanchor(world, encoder, frames[-1], send_event)
            # Generate the next batch while this one plays (upstream pacing).
            step = asyncio.ensure_future(self._gpu(self._timed_step, world.controls.take()))
            interval = max(step_seconds, 1e-3) / len(frames)
            for frame in frames:
                pts = self._emit(encoder, frame, pts, out, seq=seq)
                if self._stop.is_set():
                    break
                await asyncio.sleep(interval)
            await send_event({"type": "stats", "step_ms": round(step_seconds * 1000, 1),
                              "engine_fps": round(len(frames) / max(step_seconds, 1e-3), 1),
                              "encoder": encoder.name, "prompt_version": world.prompt_version})
        await asyncio.gather(step, return_exceptions=True)
        return "closed"

    def _timed_step(self, ctrl):
        started = time.perf_counter()
        frames = self.engine.step(ctrl)
        spent = time.perf_counter() - started
        self.last_step_seconds = spent
        metrics.ENGINE_STEP.labels(model=self.engine.name).observe(spent)
        moving = bool(ctrl.button) or abs(ctrl.mouse[0]) + abs(ctrl.mouse[1]) > 0.02
        return frames, spent, ctrl.seq, moving

    def _anchor_due(self, world: World) -> bool:
        every = self.settings.anchor_seconds
        return every > 0 and world.moving_seconds >= every and bool(self._anchor_text(world))

    def _anchor_text(self, world: World) -> str:
        return anchor_prompt(world.scene_prompt, world.last_edit, self.settings.max_prompt_chars)

    def _anchor_edit(self, current: np.ndarray, prompt: str, seed: int) -> np.ndarray:
        """FLUX edit, at the autoencoder's native size when configured: about 0.66 s instead of 1.17 s at 720p, and
        the engine takes the result at that size anyway (raw mode)."""
        size = edit_size(self.settings.anchor_edit_size)
        if size and current.shape[1::-1] != size:
            from PIL import Image

            current = np.asarray(Image.fromarray(current).resize(size, Image.LANCZOS))
        return self.images.edit(current, prompt, seed)

    async def _reanchor(self, world: World, encoder: FrameEncoder, current: np.ndarray, send_event) -> None:
        """Redraw the current frame from the scene prompt and splice it back: the world keeps its scene.

        Waypoint-1.5 only invents what it has never seen, so after some seconds of walking it has drifted into
        close-up texture; it never recovers on its own. The UI shows the same banner as a world edit.
        """
        world.state = State.RECONDITIONING
        await send_event({"type": "state", "state": world.state.value, "reason": "stabilize"})
        started = time.perf_counter()
        world.moving_seconds = 0.0  # also on failure: no retry storm
        try:
            fixed = await self._gpu(self._anchor_edit, current, self._anchor_text(world), world.seed + 1000 + world.anchors)
            await self._gpu(self.engine.splice, fixed)
            world.anchors += 1
            encoder.request_keyframe()
            metrics.IMAGE_SECONDS.labels(kind="anchor").observe(time.perf_counter() - started)
            metrics.ANCHORS.labels(result="applied").inc()
            await send_event({"type": "anchor", "status": "applied", "count": world.anchors,
                              "ms": round((time.perf_counter() - started) * 1000)})
        except Exception as exc:  # noqa: BLE001 - a failed anchor keeps the world running, drifting
            logger.exception("world anchor failed")
            metrics.ANCHORS.labels(result="failed").inc()
            await send_event({"type": "anchor", "status": "failed", "message": str(exc)[:200]})
        world.state = State.STREAMING
        await send_event({"type": "state", "state": world.state.value})

    async def _apply_edit(self, world: World, encoder: FrameEncoder, current: np.ndarray, send_event) -> None:
        version, prompt = self._edits.get_nowait()
        while not self._edits.empty():  # only the newest request matters
            version, prompt = self._edits.get_nowait()
        world.state = State.RECONDITIONING
        await send_event({"type": "state", "state": world.state.value, "prompt_version": version})
        started = time.perf_counter()
        try:
            edited = await self._gpu(self.images.edit, current, prompt, world.seed + version)
            metrics.IMAGE_SECONDS.labels(kind="edit").observe(time.perf_counter() - started)
            await self._gpu(self.engine.splice, edited)
            world.prompt_version = version
            world.last_edit = prompt
            world.moving_seconds = 0.0
            encoder.request_keyframe()
            elapsed = time.perf_counter() - started
            metrics.PROMPT_APPLY.labels(result="applied").observe(elapsed)
            await send_event({"type": "prompt", "prompt_version": version, "status": "applied",
                              "apply_ms": round(elapsed * 1000)})
        except Exception as exc:  # noqa: BLE001 - a failed edit keeps the world running
            logger.exception("world edit failed")
            metrics.PROMPT_APPLY.labels(result="failed").observe(time.perf_counter() - started)
            await send_event({"type": "prompt", "prompt_version": version, "status": "failed",
                              "message": str(exc)[:200]})
        world.state = State.STREAMING
        await send_event({"type": "state", "state": world.state.value})

    def _emit(self, encoder: FrameEncoder, frame: np.ndarray, pts: int, out, keyframe: bool = False,
              seq: int = -1) -> int:
        if keyframe:
            encoder.request_keyframe()
        for payload, is_key in encoder.encode(frame):
            message = video_message(payload, is_key, int(pts * 1_000_000 / 60), seq)
            try:
                out.put_nowait(message)
            except asyncio.QueueFull:
                # A slow browser: drop and restart from a keyframe rather than queue latency.
                metrics.FRAMES_DROPPED.labels(reason="backpressure").inc()
                encoder.request_keyframe()
        return pts + 1


async def _drain(out: "asyncio.Queue[Optional[bytes]]", send_bytes: SendBytes, stop: asyncio.Event) -> bool:
    """Send video until the end marker; True when the browser went away first."""
    broken = False
    while True:
        message = await out.get()
        if message is None:
            return broken
        if broken:
            continue  # keep draining so the producer never blocks
        try:
            await send_bytes(message)
        except Exception:  # noqa: BLE001 - the browser went away
            broken = True
            stop.set()


def _decode_png(data: bytes) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def encode_png(image: np.ndarray) -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(image).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
