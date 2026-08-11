"""ADR-0043 compatibility test for app/downstream.py's `_invoke_sales_db`:
exercises the real `mcp` SDK client against a small local MCP server (not
a cross-import of components/mcp-servers/sales-db - each component's
tests stay self-contained, matching this repository's convention) that
mimics the same shape: one tool that succeeds with a plain-dict return,
one that raises (an MCP tool-level error), plus the ADR-0037
workload-identity check as Starlette middleware ahead of the mount.

Proves `_invoke_sales_db` correctly:
  - unwraps the SDK's {"result": <value>} structured-content envelope
    (verified against the real SDK - a tool with a plain `dict` return
    type gets wrapped this way, since MCP requires an object-typed
    top-level schema for structured content) back into the gateway's
    pre-migration response shape;
  - maps an MCP tool-level error (`CallToolResult.is_error`) to a
    `DownstreamError(502, ...)`, preserving the exact contract
    app/main.py already depends on;
  - maps an unknown-tool call to the same `DownstreamError(502, ...)`
    contract.

Run from this directory:

    python3 tests/test_downstream_sales_db.py
"""
from __future__ import annotations

import asyncio
import os
import sys

os.environ.setdefault("MCP_GATEWAY_WORKLOAD_TOKEN", "test-workload-token")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hmac  # noqa: E402
from typing import Any, Dict  # noqa: E402

import httpx2  # noqa: E402
from httpx2 import ASGITransport  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402

from app import downstream  # noqa: E402

BASE_URL = "http://localhost:8000"


def _build_fake_sales_db_app() -> Starlette:
    mcp_server = MCPServer(name="fake-sales-db", version="0.1.0")

    # The `-> Dict[str, Any]` return annotation is required, not
    # decorative - verified directly, twice: a bare `-> dict` annotation
    # was NOT enough to make the SDK derive a structured-content schema
    # (it still fell back to text-only content); matching
    # components/mcp-servers/sales-db/server.py's real tools' exact
    # `typing.Dict[str, Any]` annotation is what actually works.
    @mcp_server.tool()
    async def get_customer(customer_id: int) -> Dict[str, Any]:
        if customer_id == 999:
            raise ValueError(f"no customer with id {customer_id}")
        return {"customer": {"id": customer_id, "name": "Acme Corp"}}

    class GatewayTokenMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            token = request.headers.get("x-zuno-gateway-token", "")
            if not hmac.compare_digest(token, "test-workload-token"):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
            return await call_next(request)

    asgi_app = mcp_server.streamable_http_app(streamable_http_path="/mcp")
    asgi_app.add_middleware(GatewayTokenMiddleware)
    return asgi_app


async def test_successful_call_unwraps_structured_content_envelope(transport) -> None:
    downstream.SALES_DB_MCP_ENDPOINT = f"{BASE_URL}/mcp"
    downstream.MCP_GATEWAY_WORKLOAD_TOKEN = "test-workload-token"

    orig_client_cls = httpx2.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = transport
        return orig_client_cls(*args, **kwargs)

    httpx2.AsyncClient = patched
    try:
        result = await downstream._invoke_sales_db("get_customer", {"customer_id": 42}, "fake-bearer")
    finally:
        httpx2.AsyncClient = orig_client_cls

    assert result == {"customer": {"id": 42, "name": "Acme Corp"}}, result


async def test_tool_error_becomes_downstream_error_502(transport) -> None:
    downstream.SALES_DB_MCP_ENDPOINT = f"{BASE_URL}/mcp"
    downstream.MCP_GATEWAY_WORKLOAD_TOKEN = "test-workload-token"

    orig_client_cls = httpx2.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = transport
        return orig_client_cls(*args, **kwargs)

    httpx2.AsyncClient = patched
    try:
        try:
            await downstream._invoke_sales_db("get_customer", {"customer_id": 999}, "fake-bearer")
            raise AssertionError("expected DownstreamError")
        except downstream.DownstreamError as exc:
            assert exc.status_code == 502
            assert "no customer with id 999" in exc.message
    finally:
        httpx2.AsyncClient = orig_client_cls


async def test_unknown_tool_becomes_downstream_error_502(transport) -> None:
    downstream.SALES_DB_MCP_ENDPOINT = f"{BASE_URL}/mcp"
    downstream.MCP_GATEWAY_WORKLOAD_TOKEN = "test-workload-token"

    orig_client_cls = httpx2.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = transport
        return orig_client_cls(*args, **kwargs)

    httpx2.AsyncClient = patched
    try:
        try:
            await downstream._invoke_sales_db("no_such_tool", {}, "fake-bearer")
            raise AssertionError("expected DownstreamError")
        except downstream.DownstreamError as exc:
            assert exc.status_code == 502
    finally:
        httpx2.AsyncClient = orig_client_cls


TESTS = [
    test_successful_call_unwraps_structured_content_envelope,
    test_tool_error_becomes_downstream_error_502,
    test_unknown_tool_becomes_downstream_error_502,
]


async def _run_all() -> int:
    fake_app = _build_fake_sales_db_app()
    transport = ASGITransport(app=fake_app)
    lifespan_cm = fake_app.router.lifespan_context(fake_app)
    await lifespan_cm.__aenter__()

    failures = 0
    try:
        for test in TESTS:
            try:
                await test(transport)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {test.__name__}: {exc}")
            else:
                print(f"PASS {test.__name__}")
    finally:
        await lifespan_cm.__aexit__(None, None, None)
    return failures


def main() -> int:
    failures = asyncio.run(_run_all())
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
