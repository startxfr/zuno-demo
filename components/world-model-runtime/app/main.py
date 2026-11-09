"""World-model runtime API (ADR-0604 §4, §6). Internal only.

Reached only by world-model-web (NetworkPolicy), never by a browser: users,
leases, quotas and prompt screening live there. When WORLD_MODEL_INTERNAL_TOKEN
is set, every call must carry it in X-World-Runtime-Token (defence in depth).

    GET    /healthz                         process alive
    GET    /readyz                          models loaded and warmed (503 before)
    GET    /metrics                         Prometheus
    GET    /internal/status                 engine, encoder, current world
    POST   /internal/image                  {prompt, seed} -> PNG (FLUX), refused while streaming
    POST   /internal/worlds                 {prompt | image_png_b64, seed} -> new world (resets the engine)
    DELETE /internal/worlds/{world_id}      close it
    WS     /internal/worlds/{world_id}/stream
           in : {"type":"control","seq":n,"keys":[...],"mouse":{"dx":..,"dy":..},"scroll":0}
                {"type":"edit","prompt_version":n,"prompt":"..."}   (a world edit, ADR-0604 D3)
                {"type":"keyframe"} | {"type":"stop"}
           out: JSON events (state, stats, prompt) and binary video messages (session.video_message)
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from app import metrics
from app.config import Settings
from app.encoder import build_encoder
from app.engine import build_engine
from app.imagegen import build_image_generator
from app.session import Busy, NotFound, Runtime, encode_png

logger = logging.getLogger("world-model-runtime")


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    seed: int = 0


class WorldRequest(BaseModel):
    prompt: Optional[str] = Field(default=None, max_length=2000)
    image_png_b64: Optional[str] = Field(default=None, max_length=12_000_000)
    seed: int = 0


def _check_token(token: Optional[str]) -> None:
    expected = os.getenv("WORLD_MODEL_INTERNAL_TOKEN", "")
    if expected and not hmac.compare_digest(token or "", expected):
        raise HTTPException(status_code=401, detail="missing or wrong X-World-Runtime-Token")


def get_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.loader = asyncio.create_task(load())
        yield
        app.state.loader.cancel()

    app = FastAPI(title="world-model-runtime", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.state.settings = settings
    app.state.runtime = None
    app.state.ready = False
    app.state.load_error = None

    async def load() -> None:
        try:
            loop = asyncio.get_running_loop()
            engine = await loop.run_in_executor(None, build_engine, settings)
            images = await loop.run_in_executor(None, build_image_generator, settings)
            runtime = Runtime(settings, engine, images)
            # Warm-up: the first steps compile kernels (torch.compile) and are slow;
            # readiness waits for them so a visitor never meets the cold start.
            warm = await runtime._gpu(images.generate, "warm-up", 0, settings.width, settings.height)
            await runtime._gpu(engine.reset, warm)
            for _ in range(3):
                await runtime._gpu(runtime._timed_step, runtime_warm_ctrl())
            # A first image edit costs ~10 s cold (measured): pay it here, not at the first anchor mid-walk.
            await runtime._gpu(images.edit, warm, "warm-up", 0)
            # The capability probe of ADR-0604 D4: which H.264 encoder this node really has. Not ready without one,
            # and the choice is known (status, metric, preflight) before the first visitor.
            probe = await loop.run_in_executor(None, build_encoder, settings)
            runtime.encoder_name = probe.name
            metrics.ENCODER_INFO.clear()
            metrics.ENCODER_INFO.labels(encoder=probe.name).set(1)
            probe.close()
            app.state.runtime = runtime
            app.state.ready = True
            logger.info("ready: engine=%s image=%s", engine.name, images.name)
        except Exception as exc:  # noqa: BLE001 - reported by /readyz, the pod stays up for diagnosis
            logger.exception("model load failed")
            app.state.load_error = str(exc)[:300]

    def runtime() -> Runtime:
        if not app.state.ready:
            raise HTTPException(status_code=503, detail="warming up")
        return app.state.runtime

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        if app.state.ready:
            return {"status": "ready"}
        body = {"status": "failed" if app.state.load_error else "warming", "error": app.state.load_error}
        return JSONResponse(body, status_code=503)

    @app.get("/metrics")
    async def prometheus():
        return Response(generate_latest(metrics.REGISTRY), media_type=CONTENT_TYPE_LATEST)

    @app.get("/internal/status")
    async def status(x_world_runtime_token: Optional[str] = Header(default=None)):
        _check_token(x_world_runtime_token)
        rt = runtime()
        world = rt.world
        return {
            "engine": rt.engine.name, "image": rt.images.name, "precision": rt.precision,
            "encoder": rt.encoder_name, "streaming": rt.streaming,
            "last_step_ms": round(rt.last_step_seconds * 1000, 1),
            "world": None if world is None else {
                "world_id": world.world_id, "state": world.state.value, "prompt_version": world.prompt_version},
        }

    @app.post("/internal/image")
    async def image(req: ImageRequest, x_world_runtime_token: Optional[str] = Header(default=None)):
        _check_token(x_world_runtime_token)
        rt = runtime()
        if rt.streaming:
            metrics.BUSY_REJECTED.inc()
            raise HTTPException(status_code=409, detail="a world is streaming on this GPU")
        if len(req.prompt) > settings.max_prompt_chars:
            raise HTTPException(status_code=422, detail="prompt too long")
        img = await rt._gpu(rt.images.generate, req.prompt, req.seed, settings.width, settings.height)
        return {"image_png_b64": encode_png(img)}

    @app.post("/internal/worlds", status_code=201)
    async def create_world(req: WorldRequest, x_world_runtime_token: Optional[str] = Header(default=None)):
        _check_token(x_world_runtime_token)
        rt = runtime()
        png = None
        if req.image_png_b64:
            try:
                png = base64.b64decode(req.image_png_b64, validate=True)
            except (binascii.Error, ValueError):
                raise HTTPException(status_code=422, detail="image_png_b64 is not base64")
        try:
            world = await rt.create_world(req.prompt, png, req.seed)
        except Busy:
            raise HTTPException(status_code=409, detail="a world is streaming on this GPU")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return {"world_id": world.world_id, "state": world.state.value,
                "preview_png_b64": encode_png(_thumbnail(world.image))}

    @app.delete("/internal/worlds/{world_id}", status_code=204)
    async def close_world(world_id: str, x_world_runtime_token: Optional[str] = Header(default=None)):
        _check_token(x_world_runtime_token)
        try:
            await runtime().close_world(world_id)
        except NotFound:
            raise HTTPException(status_code=404, detail="no such world")
        return Response(status_code=204)

    @app.websocket("/internal/worlds/{world_id}/stream")
    async def stream(ws: WebSocket, world_id: str):
        try:
            _check_token(ws.headers.get("x-world-runtime-token"))
        except HTTPException:
            await ws.close(code=4401)
            return
        if not app.state.ready:
            await ws.close(code=4503)
            return
        rt: Runtime = app.state.runtime
        world = rt.world
        if world is None or world.world_id != world_id:
            await ws.close(code=4404)
            return
        if rt.streaming:
            metrics.BUSY_REJECTED.inc()
            await ws.close(code=4409)
            return
        await ws.accept()

        async def send_bytes(data: bytes) -> None:
            await ws.send_bytes(data)

        async def send_event(event: dict) -> None:
            await ws.send_text(json.dumps(event))

        async def receive() -> None:
            try:
                while True:
                    msg = json.loads(await ws.receive_text())
                    kind = msg.get("type")
                    if kind == "control":
                        world.controls.update(msg.get("seq"), msg.get("keys") or [], msg.get("mouse"),
                                              msg.get("scroll", 0))
                    elif kind == "edit":
                        version, prompt = msg.get("prompt_version"), msg.get("prompt")
                        if not (isinstance(version, int) and isinstance(prompt, str)
                                and rt.request_edit(version, prompt)):
                            await send_event({"type": "prompt", "prompt_version": version, "status": "rejected"})
                    elif kind == "stop":
                        break
            except (WebSocketDisconnect, json.JSONDecodeError, RuntimeError):
                pass
            finally:
                rt.stop()

        receiver = asyncio.create_task(receive())
        try:
            await rt.stream(world_id, send_bytes, send_event)
        except (Busy, NotFound):
            pass
        except WebSocketDisconnect:
            rt.stop()
        finally:
            receiver.cancel()
            try:
                await ws.close()
            except RuntimeError:
                pass

    return app


def runtime_warm_ctrl():
    from app.controls import Ctrl

    return Ctrl(button=frozenset({87}))


def _thumbnail(image: np.ndarray) -> np.ndarray:
    from PIL import Image

    img = Image.fromarray(image)
    img.thumbnail((320, 180))
    return np.asarray(img)
