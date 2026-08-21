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


async def test_tools_list_reports_exactly_the_five_declared_tools(transport) -> None:
    async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    names = sorted(t.name for t in result.tools)
    assert names == [
        "aggregate_revenue_by_year",
        "get_customer",
        "get_quote",
        "list_open_opportunities",
        "lookup_record",
    ], names


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


async def test_aggregate_revenue_by_year_round_trip(transport) -> None:
    async def fake_connect():
        return _FakeConn({"total_revenue": 42000, "invoice_count": 3}, [])

    with mock.patch.object(server, "_connect", fake_connect):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "aggregate_revenue_by_year", {"year": 2026, "status": "paid"}
                )

    assert not result.is_error, result.content
    assert result.structured_content == {
        "result": {
            "year": 2026, "status_filter": "paid", "total_revenue": 42000, "invoice_count": 3,
        }
    }, result.structured_content


async def test_aggregate_revenue_by_year_rejects_an_unknown_status(transport) -> None:
    async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "aggregate_revenue_by_year", {"year": 2026, "status": "not-a-real-status"}
            )

    assert result.is_error, "expected an MCP tool-level error for an unknown status"
    assert any(
        "unknown status" in block.text for block in result.content if hasattr(block, "text")
    )


async def test_lookup_record_round_trip_for_an_allow_listed_type(transport) -> None:
    fake_invoice = {"id": 7, "reference": "INV-007", "total_amount": 500}

    async def fake_connect():
        return _FakeConn(fake_invoice, [])

    with mock.patch.object(server, "_connect", fake_connect):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "lookup_record", {"record_type": "invoice", "record_id": 7}
                )

    assert not result.is_error, result.content
    assert result.structured_content == {
        "result": {"record_type": "invoice", "record": fake_invoice}
    }, result.structured_content


async def test_lookup_record_rejects_a_record_type_outside_the_allow_list(transport) -> None:
    # No path from caller input to SQL text: an unrecognized record_type
    # never reaches a query at all (proves the allow-list check runs
    # before any table-name interpolation, not just that a bad table
    # name would fail).
    async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "lookup_record", {"record_type": "users", "record_id": 1}
            )

    assert result.is_error, "expected an MCP tool-level error for a non-allow-listed record_type"
    assert any(
        "unknown record_type" in block.text for block in result.content if hasattr(block, "text")
    )


async def test_connect_dispatches_to_postgres_by_default(transport) -> None:
    """ADR-0216/WP-065: unused `transport` param only for TESTS-list
    uniformity - this is a unit-level check of _connect()'s engine
    dispatch, not a protocol round-trip."""
    with mock.patch.object(server, "DB_ENGINE", "postgres"), \
         mock.patch("psycopg.AsyncConnection.connect", new=mock.AsyncMock(return_value="pg-conn")) as fake_pg:
        result = await server._connect()
    assert result == "pg-conn"
    fake_pg.assert_called_once()


async def test_connect_dispatches_to_mariadb_when_engine_is_mariadb(transport) -> None:
    fake_aiomysql = mock.MagicMock()
    fake_aiomysql.connect = mock.AsyncMock(return_value="mariadb-conn")
    fake_aiomysql.DictCursor = object()
    with mock.patch.object(server, "DB_ENGINE", "mariadb"), \
         mock.patch.object(server, "MARIADB_USER", "sxa"), \
         mock.patch.object(server, "MARIADB_PASSWORD", "secret"), \
         mock.patch.dict(sys.modules, {"aiomysql": fake_aiomysql}):
        result = await server._connect()
    assert result == "mariadb-conn"
    fake_aiomysql.connect.assert_called_once()
    assert fake_aiomysql.connect.call_args.kwargs["db"] == server.MARIADB_DATABASE


async def test_connect_fails_closed_without_mariadb_credentials(transport) -> None:
    with mock.patch.object(server, "DB_ENGINE", "mariadb"), \
         mock.patch.object(server, "MARIADB_USER", None), \
         mock.patch.object(server, "MARIADB_PASSWORD", None):
        try:
            await server._connect()
            raise AssertionError("expected RuntimeError for missing MariaDB credentials")
        except RuntimeError as exc:
            assert "SXA_MARIADB_USER" in str(exc)


TESTS = [
    test_unauthenticated_call_rejected_before_any_protocol_handling,
    test_tools_list_reports_exactly_the_five_declared_tools,
    test_get_customer_round_trip_with_a_real_authenticated_call,
    test_get_customer_not_found_reports_as_a_tool_error_not_a_crash,
    test_aggregate_revenue_by_year_round_trip,
    test_aggregate_revenue_by_year_rejects_an_unknown_status,
    test_lookup_record_round_trip_for_an_allow_listed_type,
    test_lookup_record_rejects_a_record_type_outside_the_allow_list,
    test_connect_dispatches_to_postgres_by_default,
    test_connect_dispatches_to_mariadb_when_engine_is_mariadb,
    test_connect_fails_closed_without_mariadb_credentials,
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
