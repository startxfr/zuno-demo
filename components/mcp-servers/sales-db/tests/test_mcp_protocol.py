"""ADR-0043 compatibility tests: this server's `/mcp` endpoint speaks a
real, standards-compliant MCP streamable-HTTP transport (the official
`mcp` SDK), not a hand-rolled JSON-RPC-shaped endpoint. Exercises the
actual SDK client (mcp.client.session.ClientSession +
mcp.client.streamable_http.streamable_http_client) against this server's
real ASGI app in-process (httpx2's ASGITransport - no real socket), so
these tests prove genuine protocol compatibility, not just that our own
code agrees with itself.

Also re-proves ADR-0037's workload-identity requirement still holds after
the protocol migration: a request with no X-Zuno-Gateway-Token is
rejected before any MCP protocol handling runs.

The server's streamable-HTTP session manager can only be started once per
process (an `mcp` SDK constraint, verified directly), so - unlike this
repository's usual one-function-per-test style - all tests here share one
server lifespan started once at the top of `main()`, the same way one
real server instance serves many requests over its lifetime.

Run from this directory:

    python3 tests/test_mcp_protocol.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock as mock

os.environ.setdefault("MCP_GATEWAY_WORKLOAD_TOKEN", "test-workload-token")
os.environ.setdefault("PGUSER", "test")
os.environ.setdefault("PGPASSWORD", "test")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx2  # noqa: E402
from httpx2 import ASGITransport  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

import server  # noqa: E402

BASE_URL = "http://localhost:8000"
GATEWAY_HEADERS = {"X-Zuno-Gateway-Token": "test-workload-token"}


class _FakeCursor:
    def __init__(self, one, many):
        self._one = one
        self._many = many

    async def execute(self, *_args, **_kwargs):
        return None

    async def fetchone(self):
        return self._one

    async def fetchall(self):
        return self._many

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _FakeConn:
    def __init__(self, one, many):
        self._one = one
        self._many = many

    def cursor(self):
        return _FakeCursor(self._one, self._many)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


async def _open_session(transport, headers):
    http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers)
    return streamable_http_client(f"{BASE_URL}/mcp", http_client=http_client)


async def test_unauthenticated_call_rejected_before_any_protocol_handling(transport) -> None:
    async with httpx2.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0"},
            headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        )
    assert resp.status_code == 401, f"expected 401 with no gateway token, got {resp.status_code}"


async def test_tools_list_reports_exactly_the_three_declared_tools(transport) -> None:
    async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    names = sorted(t.name for t in result.tools)
    assert names == ["get_customer", "get_quote", "list_open_opportunities"], names


async def test_get_customer_round_trip_with_a_real_authenticated_call(transport) -> None:
    fake_customer = {"id": 42, "name": "Acme Corp"}
    fake_contacts = [{"id": 1, "first_name": "Jane", "last_name": "Doe"}]

    async def fake_connect():
        return _FakeConn(fake_customer, fake_contacts)

    with mock.patch.object(server, "_connect", fake_connect):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("get_customer", {"customer_id": 42})

    assert not result.is_error, result.content
    assert result.structured_content == {"result": {"customer": fake_customer, "contacts": fake_contacts}}, (
        result.structured_content
    )


async def test_get_customer_not_found_reports_as_a_tool_error_not_a_crash(transport) -> None:
    async def fake_connect():
        return _FakeConn(None, [])

    with mock.patch.object(server, "_connect", fake_connect):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("get_customer", {"customer_id": 999})

    assert result.is_error, "expected an MCP tool-level error, got a normal result"
    assert any("no customer with id 999" in block.text for block in result.content if hasattr(block, "text"))


TESTS = [
    test_unauthenticated_call_rejected_before_any_protocol_handling,
    test_tools_list_reports_exactly_the_three_declared_tools,
    test_get_customer_round_trip_with_a_real_authenticated_call,
    test_get_customer_not_found_reports_as_a_tool_error_not_a_crash,
]


async def _run_all() -> int:
    transport = ASGITransport(app=server.app)
    lifespan_cm = server.app.router.lifespan_context(server.app)
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
