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


# Binary video message: b"V", flags (bit 0 = keyframe), pts in microseconds (8 bytes), Annex-B payload.
VIDEO_TAG = b"V"


def video_message(payload: bytes, keyframe: bool, pts_us: int) -> bytes:
    return VIDEO_TAG + bytes([1 if keyframe else 0]) + pts_us.to_bytes(8, "big") + payload


@dataclass
class World:
    world_id: str
    seed: int
    image: np.ndarray
    state: State = State.READY
    prompt_version: int = 0
    controls: ControlState = field(default_factory=ControlState)
    created: float = field(default_factory=time.monotonic)


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
        self.world = World(world_id=uuid.uuid4().hex, seed=seed, image=image)
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
            frames, step_seconds = await step
            metrics.FRAMES_GENERATED.labels(model=self.engine.name, precision=self.precision).inc(len(frames))
            if not self._edits.empty():
                await self._apply_edit(world, encoder, frames[-1], send_event)
            # Generate the next batch while this one plays (upstream pacing).
            step = asyncio.ensure_future(self._gpu(self._timed_step, world.controls.take()))
            interval = max(step_seconds, 1e-3) / len(frames)
            for frame in frames:
                pts = self._emit(encoder, frame, pts, out)
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
        return frames, spent

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

    def _emit(self, encoder: FrameEncoder, frame: np.ndarray, pts: int, out, keyframe: bool = False) -> int:
        if keyframe:
            encoder.request_keyframe()
        for payload, is_key in encoder.encode(frame):
            message = video_message(payload, is_key, int(pts * 1_000_000 / 60))
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
