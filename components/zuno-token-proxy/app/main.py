"""zuno-token-proxy: relays an experience client's calls to the gateways with a fresh token (ADR-0601).

    /v1/...   -> ai-gateway  /v1/...   (chat completions, models; streaming passthrough)
    /mcp...   -> mcp-gateway /mcp...   (streamable HTTP, SSE passthrough, session header kept)
    /healthz  liveness, /readyz a valid token is held, /metrics counters

`Authorization` from the client (a dummy key) is dropped and replaced. The configured fixed headers
replace any header of the same name. Without a valid token the proxy answers 503: it never relays a
request without one. Ingress is limited to the namespace by NetworkPolicy; the proxy itself has no auth.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Iterable, Optional, Tuple

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from app import metrics
from app.config import Settings
from app.token import TokenSource, TokenUnavailable

logger = logging.getLogger("zuno_token_proxy")

# RFC 9110 hop-by-hop headers, plus those the proxy owns.
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
    "transfer-encoding", "upgrade", "host", "content-length",
}
_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


def _request_headers(incoming: Iterable[Tuple[str, str]], fixed: Dict[str, str], token: str) -> Dict[str, str]:
    owned = {name.lower() for name in fixed} | {"authorization"}
    headers = {k: v for k, v in incoming if k.lower() not in _HOP_BY_HOP and k.lower() not in owned}
    headers.update(fixed)
    headers["Authorization"] = f"Bearer {token}"
    return headers


def _response_headers(upstream: httpx.Headers) -> Dict[str, str]:
    return {k: v for k, v in upstream.items() if k.lower() not in _HOP_BY_HOP}


def create_app(
    settings: Settings,
    token_transport: Optional[httpx.AsyncBaseTransport] = None,
    upstream_transport: Optional[httpx.AsyncBaseTransport] = None,
    token_source: Optional[TokenSource] = None,
) -> FastAPI:
    verify = settings.ca_bundle or True
    token_client = httpx.AsyncClient(transport=token_transport, verify=verify)
    upstream_client = httpx.AsyncClient(
        transport=upstream_transport,
        timeout=httpx.Timeout(settings.upstream_timeout_s, connect=10.0),
    )
    tokens = token_source or TokenSource(settings, token_client)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await token_client.aclose()
        await upstream_client.aclose()

    app = FastAPI(title="zuno-token-proxy", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.tokens = tokens

    async def relay(request: Request, upstream_name: str, base: str, path: str, fixed: Dict[str, str]) -> Response:
        try:
            token = await tokens.get()
        except TokenUnavailable:
            metrics.inc("zuno_token_proxy_requests_total", upstream=upstream_name, code="503")
            return JSONResponse({"error": "token unavailable"}, status_code=503)
        url = base + path
        if request.url.query:
            url += "?" + request.url.query
        outbound = upstream_client.build_request(
            request.method,
            url,
            headers=_request_headers(request.headers.items(), fixed, token),
            content=await request.body(),
        )
        try:
            upstream = await upstream_client.send(outbound, stream=True)
        except httpx.HTTPError as exc:
            logger.warning("%s unreachable: %s", upstream_name, exc)
            metrics.inc("zuno_token_proxy_requests_total", upstream=upstream_name, code="502")
            return JSONResponse({"error": f"{upstream_name} unreachable"}, status_code=502)
        metrics.inc("zuno_token_proxy_requests_total", upstream=upstream_name, code=str(upstream.status_code))
        return StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers=_response_headers(upstream.headers),
            background=BackgroundTask(upstream.aclose),
        )

    @app.get("/healthz")
    async def healthz() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> Response:
        try:
            await tokens.get()
        except TokenUnavailable:
            return JSONResponse({"status": "no token"}, status_code=503)
        return JSONResponse({"status": "ready"})

    @app.get("/metrics")
    async def prometheus() -> Response:
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    @app.api_route("/v1/{path:path}", methods=_METHODS)
    async def ai_gateway(request: Request, path: str) -> Response:
        return await relay(request, "ai-gateway", settings.ai_gateway_url, "/v1/" + path, settings.ai_headers)

    @app.api_route("/mcp", methods=_METHODS)
    @app.api_route("/mcp/{path:path}", methods=_METHODS)
    async def mcp_gateway(request: Request, path: str = "") -> Response:
        suffix = "/mcp" + ("/" + path if path else "")
        return await relay(request, "mcp-gateway", settings.mcp_gateway_url, suffix, settings.mcp_headers)

    return app


def get_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    return create_app(Settings.from_env())
