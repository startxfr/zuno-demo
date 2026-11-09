"""Shared fixtures of the world-model-web tests (ADR-0604 WP-234): real JWTs, a fake GPU runtime.

The fake runtime speaks the contract of components/world-model-runtime over a real socket
(uvicorn in a thread), so the web tier's REST client and WebSocket relay are exercised for real.
No GPU, no Keycloak, no network beyond localhost.
"""
from __future__ import annotations

import base64
import json
import socket
import struct
import threading
import time
import zlib
from typing import Dict, List

import httpx
import jwt
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.testclient import TestClient

from app.auth import Authenticator
from app.config import Settings
from app.main import get_app
from app.prompts import Screener

ISSUER = "https://keycloak.example/realms/zuno"
AUDIENCE = "zuno-admin-api"


def tiny_png(color=(20, 80, 160), size=(8, 8)) -> bytes:
    """A valid PNG without Pillow."""
    w, h = size
    raw = b"".join(b"\x00" + bytes(color) * w for _ in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ------------------------------------------------------------------------------ tokens
class Keys:
    def __init__(self):
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public = self.private.public_key()

    def token(self, sub="u-1", username="presenter-01", groups=("/zuno-world-model-users",), audience=AUDIENCE,
              issuer=ISSUER, ttl=300, key=None) -> str:
        now = int(time.time())
        claims = {"sub": sub, "preferred_username": username, "groups": list(groups), "aud": audience,
                  "iss": issuer, "iat": now, "exp": now + ttl}
        return jwt.encode(claims, key or self.private, algorithm="RS256")


@pytest.fixture(scope="session")
def keys() -> Keys:
    return Keys()


# ------------------------------------------------------------------------------ fake runtime
class FakeRuntime:
    def __init__(self):
        self.ready = True
        self.world = None
        self.streaming = False
        self.created: List[str] = []
        self.world_requests: List[dict] = []
        self.deleted: List[str] = []
        self.controls: List[dict] = []
        self.edits: List[dict] = []
        self.images: List[dict] = []
        self.token = ""
        self.fail_image = False

    def app(self) -> FastAPI:
        app, state = FastAPI(), self

        def check(token):
            if state.token and token != state.token:
                from fastapi import HTTPException
                raise HTTPException(status_code=401)

        @app.get("/readyz")
        async def readyz():
            return Response(status_code=200 if state.ready else 503)

        @app.get("/internal/status")
        async def status(x_world_runtime_token: str = Header(default="")):
            check(x_world_runtime_token)
            return {"engine": "mock", "image": "mock", "precision": "cpu", "encoder": "x264",
                    "streaming": state.streaming, "last_step_ms": 12.5, "world": state.world}

        @app.post("/internal/image")
        async def image(body: dict, x_world_runtime_token: str = Header(default="")):
            check(x_world_runtime_token)
            if state.fail_image:
                return Response(status_code=500, content="boom")
            state.images.append(body)
            return {"image_png_b64": base64.b64encode(tiny_png()).decode()}

        @app.post("/internal/worlds", status_code=201)
        async def create(body: dict, x_world_runtime_token: str = Header(default="")):
            check(x_world_runtime_token)
            if state.streaming:
                return Response(status_code=409)
            state.world = f"w{len(state.created) + 1}"
            state.created.append(state.world)
            state.world_requests.append(body)
            return {"world_id": state.world, "state": "READY",
                    "preview_png_b64": base64.b64encode(tiny_png()).decode()}

        @app.delete("/internal/worlds/{world_id}", status_code=204)
        async def delete(world_id: str):
            state.deleted.append(world_id)
            state.world = None
            return Response(status_code=204)

        @app.websocket("/internal/worlds/{world_id}/stream")
        async def stream(ws: WebSocket, world_id: str):
            await ws.accept()
            state.streaming = True
            try:
                await ws.send_text(json.dumps({"type": "state", "state": "STREAMING", "engine": "mock"}))
                await ws.send_bytes(b"V\x01" + (0).to_bytes(8, "big") + (0xFFFFFFFF).to_bytes(4, "big") + b"\x00\x00\x00\x01frame0")
                while True:
                    msg = json.loads(await ws.receive_text())
                    if msg["type"] == "control":
                        state.controls.append(msg)
                    elif msg["type"] == "edit":
                        state.edits.append(msg)
                        await ws.send_text(json.dumps({"type": "prompt", "prompt_version": msg["prompt_version"],
                                                       "status": "applied", "apply_ms": 5}))
                    elif msg["type"] == "stop":
                        break
            except WebSocketDisconnect:
                pass
            finally:
                state.streaming = False

        return app


class _Server(uvicorn.Server):
    def install_signal_handlers(self):  # not in the main thread
        pass


@pytest.fixture()
def fake_runtime():
    fake = FakeRuntime()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = _Server(uvicorn.Config(fake.app(), log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    fake.url = f"http://127.0.0.1:{port}"
    yield fake
    server.should_exit = True
    thread.join(timeout=5)


# ------------------------------------------------------------------------------ the app
class Gateway:
    """A scripted ai-gateway behind httpx.MockTransport."""

    def __init__(self):
        self.calls: List[httpx.Request] = []
        self.reply = lambda text: {"allowed": True, "reason": "", "prompt": f"vivid: {text}"}
        self.status = 200
        self.raw: str = ""

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.status != 200:
            return httpx.Response(self.status, text="down")
        body = json.loads(request.content)
        user_text = body["messages"][-1]["content"].split("<prompt>")[1].split("</prompt>")[0]
        content = self.raw or json.dumps(self.reply(user_text))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.fixture()
def gateway() -> Gateway:
    return Gateway()


def make_settings(fake_runtime, **overrides) -> Settings:
    base = dict(issuer=ISSUER, audience=AUDIENCE, runtime_url=fake_runtime.url, runtime_timeout=10.0,
                gateway_url="http://ai-gateway.test", max_prompt_chars=200, worlds_per_hour=50,
                presets_file=__import__("pathlib").Path("/nonexistent/presets.yaml"),
                ui_dir=__import__("pathlib").Path("/nonexistent/ui"))
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def make_client(keys, fake_runtime, gateway):
    clients: List[TestClient] = []

    def build(**overrides) -> TestClient:
        settings = make_settings(fake_runtime, **overrides)
        screener = Screener(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(gateway.handler)))
        app = get_app(settings, Authenticator(settings, key_resolver=lambda _t: keys.public), screener=screener)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        client.app_state = app.state
        return client

    yield build
    for client in clients:
        client.__exit__(None, None, None)


def bearer(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
