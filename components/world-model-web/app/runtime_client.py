"""Client of world-model-runtime's internal API (ADR-0604 §4, §6).

REST through httpx, the video stream through a WebSocket. Every call carries
X-World-Runtime-Token when one is configured (defence in depth: the
NetworkPolicy already limits who can reach the runtime).
"""
from __future__ import annotations

from typing import Optional

import httpx
import websockets

from app.config import Settings


class RuntimeBusy(Exception):
    """The runtime already serves a streaming world (HTTP 409)."""


class RuntimeUnavailable(Exception):
    """The runtime is down, still loading its models, or answered something unusable."""


class RuntimeClient:
    def __init__(self, settings: Settings, client: Optional[httpx.AsyncClient] = None):
        self.settings = settings
        self._headers = {"X-World-Runtime-Token": settings.runtime_token} if settings.runtime_token else {}
        self.client = client or httpx.AsyncClient(
            base_url=settings.runtime_url, timeout=settings.runtime_timeout, headers=self._headers)

    async def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise RuntimeUnavailable(f"{type(exc).__name__}") from exc
        if response.status_code == 409:
            raise RuntimeBusy()
        if response.status_code == 503:
            raise RuntimeUnavailable("warming up")
        if response.status_code >= 400:
            raise RuntimeUnavailable(f"runtime answered {response.status_code}: {response.text[:200]}")
        return response

    async def status(self) -> dict:
        return (await self._call("GET", "/internal/status")).json()

    async def ready(self) -> bool:
        try:
            response = await self.client.get("/readyz", timeout=5.0)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def image(self, prompt: str, seed: int) -> str:
        """A new image from the prompt, as base64 PNG."""
        return (await self._call("POST", "/internal/image", json={"prompt": prompt, "seed": seed})).json()["image_png_b64"]

    async def create_world(self, image_png_b64: str, seed: int, prompt: str = "") -> dict:
        """`prompt` is the text the image came from: the runtime re-anchors the scene on it (drift control)."""
        body = {"image_png_b64": image_png_b64, "seed": seed}
        if prompt:
            body["prompt"] = prompt[:500]
        return (await self._call("POST", "/internal/worlds", json=body)).json()

    async def delete_world(self, world_id: str) -> None:
        try:
            await self.client.delete(f"/internal/worlds/{world_id}")
        except httpx.HTTPError:
            pass  # best effort: a missing world is what we want

    def stream(self, world_id: str):
        """An async context manager yielding the runtime WebSocket of this world."""
        url = self.settings.runtime_url.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        return websockets.connect(
            f"{url}/internal/worlds/{world_id}/stream",
            additional_headers=self._headers,
            max_size=8 * 1024 * 1024,
            open_timeout=10,
            ping_interval=20,
        )

    async def aclose(self) -> None:
        await self.client.aclose()
