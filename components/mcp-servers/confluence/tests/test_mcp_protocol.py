"""ADR-0043/ADR-0117 protocol tests for the confluence MCP server: proves
this server's /mcp endpoint speaks real, standards-compliant MCP
streamable-HTTP (the official `mcp` SDK), exercised with the actual SDK
client against this server's real ASGI app in-process (no real socket) -
same style as `components/mcp-servers/sales-db/tests/test_mcp_protocol.py`.

Confluence Cloud itself is mocked (`server._client` is patched to return a
fake `httpx.AsyncClient`-shaped object) - these tests prove the MCP
protocol surface and the four tools' request/response mapping, not a live
Confluence call.

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
os.environ.setdefault("CONFLUENCE_BASE_URL", "https://example.atlassian.net")
os.environ.setdefault("CONFLUENCE_EMAIL", "technical@example.com")
os.environ.setdefault("CONFLUENCE_API_TOKEN", "test-token")

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


class _FakeConfluenceClient:
    """Queue-based fake: each test preloads the exact ordered sequence of
    responses its tool call will consume (server.py's own code decides how
    many/which calls to make - update_page makes GET then PUT, the others
    make exactly one call)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []  # (method, path, kwargs) - for assertions

    async def get(self, path, **kwargs):
        self.requests.append(("GET", path, kwargs))
        return self._responses.pop(0)

    async def post(self, path, **kwargs):
        self.requests.append(("POST", path, kwargs))
        return self._responses.pop(0)

    async def put(self, path, **kwargs):
        self.requests.append(("PUT", path, kwargs))
        return self._responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _patch_client(fake_client: _FakeConfluenceClient):
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


async def test_tools_list_reports_exactly_the_four_declared_tools(transport) -> None:
    async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    names = sorted(t.name for t in result.tools)
    assert names == ["create_page", "read_page", "search_pages", "update_page"], names


async def test_search_pages_round_trip(transport) -> None:
    fake_search_payload = {
        "results": [
            {
                "id": "123",
                "title": "OpenShift AI 3.5 EA2 - Model Serving Runbook",
                "space": {"key": "TECH"},
                "version": {"number": 3},
                "_links": {"webui": "/spaces/TECH/pages/123", "base": "https://example.atlassian.net"},
            }
        ]
    }
    fake_client = _FakeConfluenceClient([_FakeResponse(200, fake_search_payload)])

    with _patch_client(fake_client):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("search_pages", {"query": "model serving"})

    assert not result.is_error, result.content
    # Verified against the real SDK (mcp==2.0.0), same as
    # components/mcp-servers/sales-db's own tests: a tool whose return type
    # annotation is a plain Dict[str, Any] gets its structured content
    # wrapped as {"result": <value>} (MCP requires an object-typed
    # top-level schema; a bare dict has none) - the gateway's own
    # downstream.py unwraps this single-key envelope, but this test talks
    # to the MCP SDK client directly, so it must expect the wrapped form.
    payload = result.structured_content["result"]
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "123"
    assert payload["results"][0]["space"] == "TECH"
    assert payload["results"][0]["url"] == "https://example.atlassian.net/spaces/TECH/pages/123"
    method, path, kwargs = fake_client.requests[0]
    assert method == "GET" and path == "/content/search"
    assert 'text~"model serving"' in kwargs["params"]["cql"]


async def test_search_pages_strips_stopwords_from_a_long_question(transport) -> None:
    """A question-shaped query (ADR-0513 gate investigation: the acceptance
    gate's own "What does the latest internal Confluence doc say about the
    RHOAI 3.5 EA2 rollout?" scenario) must not reach CQL verbatim - the
    interrogative/meta words dilute text~'s fuzzy match below the point
    it ever matches a real page. A short query (test above) is untouched."""
    fake_client = _FakeConfluenceClient([_FakeResponse(200, {"results": []})])

    with _patch_client(fake_client):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "search_pages",
                    {"query": "What does the latest internal Confluence doc say about the RHOAI 3.5 EA2 rollout?"},
                )

    assert not result.is_error, result.content
    _, _, kwargs = fake_client.requests[0]
    cql = kwargs["params"]["cql"]
    for stopword in ("What", "does", "the", "latest", "internal", "Confluence", "doc", "say", "about"):
        assert stopword not in cql.split('"')[1].split(), f"{stopword!r} should have been stripped from {cql!r}"
    for keyword in ("RHOAI", "3.5", "EA2", "rollout"):
        assert keyword in cql, f"{keyword!r} missing from {cql!r}"
    # The original caller-supplied query is still reported back verbatim -
    # only the CQL search text itself is reduced.
    assert result.structured_content["result"]["query"] == (
        "What does the latest internal Confluence doc say about the RHOAI 3.5 EA2 rollout?"
    )


async def test_read_page_not_found_reports_as_a_tool_error_not_a_crash(transport) -> None:
    fake_client = _FakeConfluenceClient([_FakeResponse(404)])

    with _patch_client(fake_client):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("read_page", {"page_id": "999"})

    assert result.is_error, "expected an MCP tool-level error, got a normal result"
    assert any("no Confluence page with id 999" in block.text for block in result.content if hasattr(block, "text"))


async def test_create_page_round_trip(transport) -> None:
    fake_created = {
        "id": "555",
        "title": "New Page",
        "space": {"key": "TECH"},
        "version": {"number": 1},
        "_links": {"webui": "/spaces/TECH/pages/555", "base": "https://example.atlassian.net"},
    }
    fake_client = _FakeConfluenceClient([_FakeResponse(200, fake_created)])

    with _patch_client(fake_client):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "create_page",
                    {"space_key": "TECH", "title": "New Page", "body_html": "<p>hello</p>"},
                )

    assert not result.is_error, result.content
    payload = result.structured_content["result"]  # see search_pages test for why
    assert payload["created"] is True
    assert payload["page"]["id"] == "555"
    method, path, kwargs = fake_client.requests[0]
    assert method == "POST" and path == "/content"
    assert kwargs["json"]["space"] == {"key": "TECH"}


async def test_update_page_reads_current_version_then_increments_it(transport) -> None:
    current = {
        "id": "555",
        "title": "New Page",
        "space": {"key": "TECH"},
        "version": {"number": 4},
    }
    updated = {
        "id": "555",
        "title": "New Page",
        "space": {"key": "TECH"},
        "version": {"number": 5},
        "_links": {"webui": "/spaces/TECH/pages/555", "base": "https://example.atlassian.net"},
    }
    fake_client = _FakeConfluenceClient([_FakeResponse(200, current), _FakeResponse(200, updated)])

    with _patch_client(fake_client):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "update_page", {"page_id": "555", "body_html": "<p>updated</p>"}
                )

    assert not result.is_error, result.content
    payload = result.structured_content["result"]  # see search_pages test for why
    assert payload["updated"] is True
    assert payload["page"]["version"] == 5
    assert len(fake_client.requests) == 2
    get_method, get_path, _ = fake_client.requests[0]
    put_method, put_path, put_kwargs = fake_client.requests[1]
    assert get_method == "GET" and get_path == "/content/555"
    assert put_method == "PUT" and put_path == "/content/555"
    assert put_kwargs["json"]["version"]["number"] == 5, (
        "must PUT current version (4) + 1, not blindly resend the old version"
    )


TESTS = [
    test_unauthenticated_call_rejected_before_any_protocol_handling,
    test_tools_list_reports_exactly_the_four_declared_tools,
    test_search_pages_round_trip,
    test_search_pages_strips_stopwords_from_a_long_question,
    test_read_page_not_found_reports_as_a_tool_error_not_a_crash,
    test_create_page_round_trip,
    test_update_page_reads_current_version_then_increments_it,
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
