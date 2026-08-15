"""ADR-0043/ADR-0326 protocol tests for the salesforce MCP server: proves
this server's /mcp endpoint speaks real, standards-compliant MCP
streamable-HTTP (the official `mcp` SDK), exercised with the actual SDK
client against this server's real ASGI app in-process (no real socket) -
same style as `components/mcp-servers/confluence/tests/test_mcp_protocol.py`,
which this file is templated from.

Salesforce itself is mocked (`server._client` is patched to return a fake
`httpx.AsyncClient`-shaped object) - these tests prove the MCP protocol
surface and the three tools' request/response mapping, not a live
Salesforce call.

Also re-proves ADR-0037's workload-identity requirement holds: a request
with no X-Zuno-Gateway-Token is rejected before any MCP protocol handling.

Run from this directory:

    python3 tests/test_mcp_protocol.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock as mock

os.environ.setdefault("MCP_GATEWAY_WORKLOAD_TOKEN", "test-workload-token")
os.environ.setdefault("SALESFORCE_BASE_URL", "https://example.my.salesforce.com")
os.environ.setdefault("SALESFORCE_ACCESS_TOKEN", "test-token")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx2  # noqa: E402
from httpx2 import ASGITransport  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

import server  # noqa: E402

BASE_URL = "http://localhost:8000"
GATEWAY_HEADERS = {"X-Zuno-Gateway-Token": "test-workload-token"}


class _FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (str(payload) if payload is not None else "")

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSalesforceClient:
    """Queue-based fake: each test preloads the exact ordered sequence of
    responses its tool call will consume (server.py's own code decides how
    many/which calls to make - update_opportunity makes PATCH then GET,
    the others make exactly one call)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []  # (method, path, kwargs) - for assertions

    async def get(self, path, **kwargs):
        self.requests.append(("GET", path, kwargs))
        return self._responses.pop(0)

    async def post(self, path, **kwargs):
        self.requests.append(("POST", path, kwargs))
        return self._responses.pop(0)

    async def patch(self, path, **kwargs):
        self.requests.append(("PATCH", path, kwargs))
        return self._responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _patch_client(fake_client: _FakeSalesforceClient):
    return mock.patch.object(server, "_client", lambda: fake_client)


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
    assert names == ["create_opportunity", "read_opportunity", "update_opportunity"], names


async def test_read_opportunity_round_trip(transport) -> None:
    fake_payload = {
        "records": [
            {"Id": "006XX", "Name": "Acme Renewal", "StageName": "Negotiation", "Amount": 42000, "CloseDate": "2026-09-30"},
        ]
    }
    fake_client = _FakeSalesforceClient([_FakeResponse(200, fake_payload)])

    with _patch_client(fake_client):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("read_opportunity", {"query": "Acme Renewal"})

    assert not result.is_error, result.content
    # Verified against the real SDK (mcp==2.0.0), same as confluence's own
    # tests: a tool whose return type annotation is a plain Dict[str, Any]
    # gets its structured content wrapped as {"result": <value>} (MCP
    # requires an object-typed top-level schema; a bare dict has none) -
    # the gateway's own downstream.py unwraps this single-key envelope,
    # but this test talks to the MCP SDK client directly, so it must
    # expect the wrapped form.
    payload = result.structured_content["result"]
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "006XX"
    assert payload["results"][0]["title"] == "Acme Renewal"
    assert payload["results"][0]["stage"] == "Negotiation"
    assert payload["results"][0]["amount"] == 42000
    assert "Negotiation" in payload["results"][0]["excerpt"]
    method, path, kwargs = fake_client.requests[0]
    assert method == "GET" and path == "/query"
    assert "LIKE '%Acme Renewal%'" in kwargs["params"]["q"]


async def test_read_opportunity_escapes_a_single_quote_in_the_query(transport) -> None:
    # ADR-0326/WP-33: no SOQL query-parameter binding over REST - the
    # server must escape the one metacharacter that would otherwise break
    # out of the string literal, rather than interpolate the raw turn
    # message straight into the query.
    fake_client = _FakeSalesforceClient([_FakeResponse(200, {"records": []})])

    with _patch_client(fake_client):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("read_opportunity", {"query": "O'Brien"})

    assert not result.is_error, result.content
    _, _, kwargs = fake_client.requests[0]
    assert "O\\'Brien" in kwargs["params"]["q"]


async def test_create_opportunity_round_trip(transport) -> None:
    fake_client = _FakeSalesforceClient([_FakeResponse(200, {"id": "006NEW"})])

    with _patch_client(fake_client):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "create_opportunity",
                    {"name": "New Deal", "stage": "Prospecting", "close_date": "2026-12-31"},
                )

    assert not result.is_error, result.content
    payload = result.structured_content["result"]  # see read_opportunity test for why
    assert payload["created"] is True
    assert payload["opportunity"]["id"] == "006NEW"
    method, path, kwargs = fake_client.requests[0]
    assert method == "POST" and path == "/sobjects/Opportunity"
    assert kwargs["json"]["Name"] == "New Deal"
    assert kwargs["json"]["StageName"] == "Prospecting"


async def test_update_opportunity_patches_then_reads_back_the_current_state(transport) -> None:
    updated = {"Name": "Acme Renewal", "StageName": "Closed Won", "Amount": 50000, "CloseDate": "2026-09-30"}
    fake_client = _FakeSalesforceClient([_FakeResponse(204), _FakeResponse(200, updated)])

    with _patch_client(fake_client):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "update_opportunity", {"opportunity_id": "006XX", "stage": "Closed Won", "amount": 50000}
                )

    assert not result.is_error, result.content
    payload = result.structured_content["result"]  # see read_opportunity test for why
    assert payload["updated"] is True
    assert payload["opportunity"]["stage"] == "Closed Won"
    assert payload["opportunity"]["amount"] == 50000
    assert len(fake_client.requests) == 2
    patch_method, patch_path, patch_kwargs = fake_client.requests[0]
    get_method, get_path, _ = fake_client.requests[1]
    assert patch_method == "PATCH" and patch_path == "/sobjects/Opportunity/006XX"
    assert patch_kwargs["json"] == {"StageName": "Closed Won", "Amount": 50000}
    assert get_method == "GET" and get_path == "/sobjects/Opportunity/006XX"


async def test_update_opportunity_with_no_fields_is_a_tool_error_not_a_no_op_call(transport) -> None:
    fake_client = _FakeSalesforceClient([])

    with _patch_client(fake_client):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("update_opportunity", {"opportunity_id": "006XX"})

    assert result.is_error, "expected a tool-level error for an empty update"
    assert not fake_client.requests, "must not call Salesforce at all when there is nothing to update"


TESTS = [
    test_unauthenticated_call_rejected_before_any_protocol_handling,
    test_tools_list_reports_exactly_the_three_declared_tools,
    test_read_opportunity_round_trip,
    test_read_opportunity_escapes_a_single_quote_in_the_query,
    test_create_opportunity_round_trip,
    test_update_opportunity_patches_then_reads_back_the_current_state,
    test_update_opportunity_with_no_fields_is_a_tool_error_not_a_no_op_call,
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
