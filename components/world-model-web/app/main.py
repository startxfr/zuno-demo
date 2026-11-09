"""world-model-web: the browser API of the world-model demo (ADR-0604 §6.1).

    GET    /api/me                          who the token says you are
    GET    /api/presets                     the curated scenes
    GET    /api/status                      runtime readiness, busy or not, engine and encoder in use
    POST   /api/worlds                      {preset_id | prompt, seed?} -> takes the GPU lease and builds a world (409 busy)
    GET    /api/sessions/{id}               state of your session
    POST   /api/sessions/{id}/prompts       {prompt} -> a world edit, screened and enhanced (202)
    POST   /api/sessions/{id}/reset         back to the image the world started from
    POST   /api/sessions/{id}/client-stats  {fps?, latency_ms?} measured in the browser
    DELETE /api/sessions/{id}               release the lease (owner or ops)
    WS     /api/sessions/{id}/stream        controls up; state events and H.264 video down
    GET    /healthz /readyz /metrics        and the built UI at /

Identity comes from the validated token only. A session belongs to the user who created it.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import yaml
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, ConfigDict, Field

from app import metrics
from app.auth import Authenticator, Caller
from app.config import Settings
from app.prompts import PromptRefused, Screener
from app.runtime_client import RuntimeBusy, RuntimeClient, RuntimeUnavailable
from app.sessions import Busy, Lease, QuotaExceeded, Session

logger = logging.getLogger("world_model_web")

MAX_CONTROL_BYTES = 2048
KEY_NAME_MAX = 24


class WorldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset_id: Optional[str] = Field(default=None, max_length=64)
    prompt: Optional[str] = Field(default=None, max_length=2000)
    seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)


class PromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(max_length=2000)


class ClientStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fps: Optional[float] = Field(default=None, ge=0, le=240)
    latency_ms: Optional[float] = Field(default=None, ge=0, le=10_000)


def load_presets(path: Path) -> list:
    """The curated scenes (platform/world-model/config/presets.yaml, WP-236); empty when absent."""
    if not path.is_file():
        return []
    presets = (yaml.safe_load(path.read_text()) or {}).get("presets") or []
    out = []
    for item in presets:
        image = item.get("image")
        out.append({**item, "_image_path": (path.parent / image) if image else None})
    return out


def logout_url(settings: Settings) -> Optional[str]:
    """Where the browser goes to sign out: the oauth2-proxy drops its cookie, then Keycloak ends the SSO session
    and sends the browser back to the site. Without the second hop the next visit would sign straight back in."""
    if not settings.public_url:
        return None
    keycloak = (f"{settings.issuer}/protocol/openid-connect/logout?client_id={quote(settings.logout_client_id, safe='')}"
                f"&post_logout_redirect_uri={quote(settings.public_url + '/', safe='')}")
    return "/oauth2/sign_out?rd=" + quote(keycloak, safe="")


def get_app(settings: Optional[Settings] = None, authenticator: Optional[Authenticator] = None,
            runtime: Optional[RuntimeClient] = None, screener: Optional[Screener] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    auth = authenticator or Authenticator(settings)
    rt = runtime or RuntimeClient(settings)
    scr = screener or Screener(settings)
    lease = Lease(settings)
    presets = load_presets(settings.presets_file)

    async def reaper() -> None:
        while True:
            await asyncio.sleep(5)
            reason = lease.expired()
            if reason and lease.current is not None:
                await release(lease.current, reason)

    async def release(session: Session, reason: str) -> None:
        world_id = session.world_id
        if lease.release(session, reason) and world_id:
            await rt.delete_world(world_id)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(reaper())
        yield
        task.cancel()
        await asyncio.gather(scr.aclose(), rt.aclose(), return_exceptions=True)

    app = FastAPI(title="world-model-web", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.lease, app.state.settings = lease, settings

    # --------------------------------------------------------------------------- helpers
    def caller_of(request) -> Caller:
        return auth.authenticate(request)

    def owned(request, session_id: str, allow_ops: bool = False) -> "tuple[Caller, Session]":
        caller = caller_of(request)
        session = lease.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="no such session (it may have expired)")
        if session.owner_sub != caller.sub and not (allow_ops and caller.in_any(settings.ops_groups)):
            raise HTTPException(status_code=403, detail="this session belongs to another user")
        return caller, session

    def preset_by_id(preset_id: str) -> dict:
        for item in presets:
            if item.get("id") == preset_id:
                return item
        raise HTTPException(status_code=404, detail="unknown preset")

    # --------------------------------------------------------------------------- plain routes
    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        return {"status": "ready", "runtime_ready": await rt.ready()}

    @app.get("/metrics")
    async def prometheus():
        return Response(generate_latest(metrics.REGISTRY), media_type=CONTENT_TYPE_LATEST)

    @app.get("/api/me")
    async def me(request: Request):
        caller = caller_of(request)
        return {"user": caller.username, "groups": caller.groups, "ops": caller.in_any(settings.ops_groups),
                "logout_url": logout_url(settings)}

    @app.get("/api/presets")
    async def list_presets(request: Request):
        caller_of(request)
        return {"presets": [
            {"id": p["id"], "title": p.get("title", p["id"]), "description": p.get("description", ""),
             "prompt": p.get("prompt", ""), "event": p.get("event"), "has_image": bool(p.get("_image_path"))}
            for p in presets]}

    @app.get("/api/status")
    async def status(request: Request):
        caller = caller_of(request)
        body = {"runtime_ready": False, "busy": lease.current is not None,
                "you_hold": bool(lease.current and lease.current.owner_sub == caller.sub),
                "limits": {"idle_seconds": settings.idle_seconds, "max_session_seconds": settings.max_session_seconds,
                           "max_prompt_chars": settings.max_prompt_chars},
                "enhancement": "on" if settings.gateway_url else "off"}
        if lease.current is not None and caller.in_any(settings.ops_groups):
            body["holder"] = lease.current.owner_name
            body["holder_session_id"] = lease.current.session_id
        try:
            info = await rt.status()
            body.update(runtime_ready=True, engine=info.get("engine"), image=info.get("image"),
                        encoder=info.get("encoder"), precision=info.get("precision"),
                        last_step_ms=info.get("last_step_ms"))
        except (RuntimeUnavailable, RuntimeBusy):
            pass
        return body

    # --------------------------------------------------------------------------- worlds
    @app.post("/api/worlds", status_code=201)
    async def create_world(req: WorldRequest, request: Request):
        caller = caller_of(request)
        if (req.preset_id is None) == (req.prompt is None):
            raise HTTPException(status_code=422, detail="send exactly one of preset_id or prompt")
        seed = req.seed if req.seed is not None else random.randrange(2**31)
        source = f"preset:{req.preset_id}" if req.preset_id else "prompt"
        kind = "preset" if req.preset_id else "prompt"
        preset = preset_by_id(req.preset_id) if req.preset_id else None
        # Screen first: a refused prompt must not cost the visitor (or the GPU) a lease.
        screened = None
        if preset is None:
            try:
                screened = await scr.screen(req.prompt, "scene", caller.token)
            except PromptRefused as exc:
                metrics.WORLDS.labels(source=kind, result=f"refused_{exc.reason}").inc()
                raise HTTPException(status_code=422, detail={"error": "prompt_refused", "reason": exc.reason})
        if not await rt.ready():
            metrics.WORLDS.labels(source=kind, result="runtime_not_ready").inc()
            raise HTTPException(status_code=503, detail="the GPU runtime is not ready (models loading?)")
        try:
            session = await lease.acquire(caller.sub, caller.username, source, seed)
        except Busy as exc:
            detail = {"error": "busy", "message": "another world is running on the GPU"}
            if caller.in_any(settings.ops_groups):
                detail["holder"] = exc.holder
            raise HTTPException(status_code=409, detail=detail)
        except QuotaExceeded as exc:
            metrics.WORLDS.labels(source=kind, result="quota").inc()
            raise HTTPException(status_code=429, detail="too many worlds started this hour",
                                headers={"Retry-After": str(exc.retry_after)})
        try:
            if preset is not None and preset.get("_image_path") and Path(preset["_image_path"]).is_file():
                base = base64.b64encode(Path(preset["_image_path"]).read_bytes()).decode()
                effective = preset.get("prompt", "")
            else:
                effective = screened.prompt if screened else preset.get("prompt", "")
                base = await rt.image(effective, seed)
            world = await rt.create_world(base, seed, effective)
        except (RuntimeBusy, RuntimeUnavailable) as exc:
            lease.release(session, "create_failed")
            metrics.WORLDS.labels(source=kind, result="runtime_error").inc()
            status_code = 409 if isinstance(exc, RuntimeBusy) else 503
            raise HTTPException(status_code=status_code, detail=f"the GPU runtime refused the world: {exc}")
        except BaseException:
            lease.release(session, "create_failed")
            raise
        session.world_id, session.base_png_b64, session.state = world["world_id"], base, "READY"
        session.scene_prompt = effective
        session.touch()
        metrics.WORLDS.labels(source=kind, result="created").inc()
        return {
            **session.public(),
            "prompt": None if screened is None else
            {"effective": screened.prompt, "original": screened.original, "enhancement": screened.enhancement},
            "preview_png_b64": world.get("preview_png_b64"),
            "limits": {"idle_seconds": settings.idle_seconds, "max_session_seconds": settings.max_session_seconds},
        }

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str, request: Request):
        _, session = owned(request, session_id)
        return session.public()

    @app.post("/api/sessions/{session_id}/prompts", status_code=202)
    async def change_prompt(session_id: str, req: PromptRequest, request: Request):
        caller, session = owned(request, session_id)
        if not session.streaming or session.runtime_ws is None:
            raise HTTPException(status_code=409, detail="open the stream first: a prompt edits the running world")
        try:
            screened = await scr.screen(req.prompt, "edit", caller.token)
        except PromptRefused as exc:
            raise HTTPException(status_code=422, detail={"error": "prompt_refused", "reason": exc.reason})
        session.prompt_requested += 1
        version = session.prompt_requested
        try:
            await session.runtime_ws.send(json.dumps({"type": "edit", "prompt_version": version,
                                                      "prompt": screened.prompt}))
        except Exception:  # noqa: BLE001 - the stream just ended
            session.prompt_requested -= 1
            raise HTTPException(status_code=409, detail="the stream closed; open it again")
        session.touch()
        return {"prompt_version": version, "status": "requested",
                "prompt": {"effective": screened.prompt, "original": screened.original,
                           "enhancement": screened.enhancement}}

    @app.post("/api/sessions/{session_id}/reset")
    async def reset(session_id: str, request: Request):
        _, session = owned(request, session_id)
        session.stop.set()  # ends the stream, if one is open
        for _ in range(50):
            if not session.streaming:
                break
            await asyncio.sleep(0.1)
        session.stop = asyncio.Event()
        old = session.world_id
        if old:
            await rt.delete_world(old)
        last = "busy"
        for _ in range(20):  # the runtime clears its streaming flag a moment after the socket closes
            try:
                world = await rt.create_world(session.base_png_b64, session.seed, session.scene_prompt)
                break
            except RuntimeBusy:
                await asyncio.sleep(0.25)
            except RuntimeUnavailable as exc:
                last = str(exc)
                break
        else:
            world = None
        if world is None:
            await release(session, "reset_failed")
            raise HTTPException(status_code=503, detail=f"could not rebuild the world: {last}")
        session.world_id, session.state = world["world_id"], "READY"
        session.prompt_requested = session.prompt_applied = 0
        session.touch()
        return {**session.public(), "preview_png_b64": world.get("preview_png_b64")}

    @app.post("/api/sessions/{session_id}/client-stats", status_code=204)
    async def client_stats(session_id: str, req: ClientStats, request: Request):
        owned(request, session_id)
        if req.fps is not None:
            metrics.CLIENT_FPS.labels(client_type="browser").observe(req.fps)
        if req.latency_ms is not None:
            metrics.CLIENT_LATENCY.labels(client_type="browser").observe(req.latency_ms / 1000)
        return Response(status_code=204)

    @app.delete("/api/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: str, request: Request):
        caller, session = owned(request, session_id, allow_ops=True)
        await release(session, "released_by_ops" if session.owner_sub != caller.sub else "released")
        return Response(status_code=204)

    # --------------------------------------------------------------------------- the stream
    def origin_allowed(ws: WebSocket) -> bool:
        origin = ws.headers.get("origin")
        if not origin:
            return True  # not a browser
        if settings.allowed_origins:
            return origin in settings.allowed_origins
        host = ws.headers.get("x-forwarded-host") or ws.headers.get("host", "")
        return origin.split("://", 1)[-1] == host

    @app.websocket("/api/sessions/{session_id}/stream")
    async def stream(ws: WebSocket, session_id: str):
        try:
            caller, session = owned(ws, session_id)
        except HTTPException as exc:
            await ws.close(code=4400 + exc.status_code % 100 if exc.status_code < 500 else 4503)
            return
        if not origin_allowed(ws):
            metrics.AUTH_FAILURES.labels(reason="bad_origin").inc()
            await ws.close(code=4403)
            return
        if session.streaming:
            await ws.close(code=4409)
            return
        await ws.accept()
        session.streaming = True
        session.stop = asyncio.Event()
        session.touch()
        try:
            async with rt.stream(session.world_id) as upstream:
                session.runtime_ws = upstream
                await relay(session, ws, upstream)
        except Exception as exc:  # noqa: BLE001 - tell the browser plainly, never freeze the last frame
            logger.warning("stream ended: %s", type(exc).__name__)
            try:
                await ws.send_text(json.dumps({"type": "state", "state": "FAILED", "message": "stream interrupted"}))
            except Exception:  # noqa: BLE001
                pass
        finally:
            session.streaming = False
            session.runtime_ws = None
            session.touch()  # the detached clock starts when the viewer leaves
            if session.state not in ("CLOSED", "FAILED"):
                session.state = "READY"
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

    async def relay(session: Session, ws: WebSocket, upstream) -> None:
        async def up() -> None:  # browser -> runtime: controls only, validated
            while not session.stop.is_set():
                raw = await ws.receive_text()
                if len(raw) > MAX_CONTROL_BYTES:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                kind = msg.get("type") if isinstance(msg, dict) else None
                if kind == "control":
                    keys = msg.get("keys") if isinstance(msg.get("keys"), list) else []
                    keys = [k[:KEY_NAME_MAX] for k in keys if isinstance(k, str)][:8]
                    mouse = msg.get("mouse") if isinstance(msg.get("mouse"), dict) else None
                    out = {"type": "control", "seq": msg.get("seq"), "keys": keys, "mouse": mouse,
                           "scroll": msg.get("scroll", 0)}
                    session.touch()
                    await upstream.send(json.dumps(out))
                elif kind == "keyframe":
                    await upstream.send(json.dumps({"type": "keyframe"}))
                elif kind in ("stop", "ping"):
                    session.touch()
                    if kind == "stop":
                        return
                # "edit" and anything else is dropped: prompts only enter through POST /prompts.

        async def down() -> None:  # runtime -> browser
            async for message in upstream:
                if isinstance(message, bytes):
                    await ws.send_bytes(message)
                    continue
                try:
                    event = json.loads(message)
                    if event.get("type") == "state" and isinstance(event.get("state"), str):
                        session.state = event["state"]
                    elif event.get("type") == "prompt" and event.get("status") == "applied":
                        session.prompt_applied = max(session.prompt_applied, int(event.get("prompt_version", 0)))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
                await ws.send_text(message)

        async def watch_stop() -> None:
            await session.stop.wait()
            await ws.send_text(json.dumps({"type": "state", "state": "CLOSED", "message": "session ended"}))

        tasks = [asyncio.create_task(c()) for c in (up, down, watch_stop)]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    # --------------------------------------------------------------------------- the built UI
    if settings.ui_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(settings.ui_dir), html=True), name="ui")

    @app.exception_handler(WebSocketDisconnect)
    async def _ws_disconnect(request, exc):  # pragma: no cover - raised inside relay tasks, handled there
        return JSONResponse({"detail": "disconnected"}, status_code=499)

    return app
