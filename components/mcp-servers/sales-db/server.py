"""sales-db MCP server (ADR-0017).

Exposes exactly three deterministic, read-only tools over the SXA-derived
sales-operations schema (data/sxa/schema/001_init.sql): get_customer,
list_open_opportunities, get_quote. Every query is parameterized and
read-only - there is no path from an LLM-constructed string to SQL here,
which is the entire point of ADR-0017 ("no direct LLM-to-DB freedom").

Wire contract (matched exactly against components/mcp-gateway/app/downstream.py,
the only caller - the gateway is the trust boundary; this server does not
re-validate the caller's end-user JWT, it trusts the gateway's ADR-0011
policy intersection already happened). ADR-0037: network location alone
(gitops/charts/mcp-sales-db's NetworkPolicy, restricting ingress to the
gateway's pods specifically) is not trusted as the sole boundary - every
call must also carry X-Zuno-Gateway-Token, a shared secret only the
gateway holds (vault-generated, ansible/roles/vault/tasks/configure.yml,
secret/zuno/mcp/gateway-workload-token):

    POST /mcp
    headers: X-Zuno-Gateway-Token: <shared secret>
    {"jsonrpc": "2.0", "id": <any>, "method": "tools/call",
     "params": {"name": "<tool>", "arguments": {...}}}
    -> {"jsonrpc": "2.0", "id": <same>, "result": {...}}
       or {"jsonrpc": "2.0", "id": <same>, "error": {"code": int, "message": str}}

    GET /healthz -> 200 once a DB connection can be acquired.
"""
from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# zuno-postgresql-rw is CNPG's own auto-created, failover-aware
# read-write Service for the zuno-postgresql Cluster - there is no plain
# "postgresql" Service (see ansible/roles/postgresql/README.md).
DB_HOST = os.getenv("PGHOST", "zuno-postgresql-rw.zuno-data.svc.cluster.local")
DB_PORT = os.getenv("PGPORT", "5432")
DB_NAME = os.getenv("PGDATABASE", "zuno")
DB_USER = os.getenv("PGUSER")
DB_PASSWORD = os.getenv("PGPASSWORD")

# ADR-0037: required, not optional - unlike the gateway's own copy of this
# value (which degrades a single tool call to a 502 if unset), this server
# has no other purpose than serving the gateway, so a missing token is a
# deployment/configuration error worth failing loudly on every request
# rather than silently accepting unauthenticated callers.
GATEWAY_WORKLOAD_TOKEN = os.getenv("MCP_GATEWAY_WORKLOAD_TOKEN", "")


def _conninfo() -> str:
    if not DB_USER or not DB_PASSWORD:
        raise RuntimeError(
            "PGUSER/PGPASSWORD are required (sourced from an ExternalSecret "
            "against secret/zuno/postgresql/app - never hardcoded, ADR-0024)"
        )
    return (
        f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} "
        f"user={DB_USER} password={DB_PASSWORD}"
    )


_pool: Optional[psycopg.AsyncConnection] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="sales-db MCP server", lifespan=lifespan)


async def _connect() -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(_conninfo(), row_factory=dict_row)


class ToolError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


async def get_customer(arguments: Dict[str, Any]) -> Dict[str, Any]:
    customer_id = arguments.get("customer_id")
    if not isinstance(customer_id, int):
        raise ToolError(-32602, "customer_id (integer) is required")

    async with await _connect() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, name, legal_name, industry, city, country, website, phone
                FROM customers
                WHERE id = %(customer_id)s
                """,
                {"customer_id": customer_id},
            )
            customer = await cur.fetchone()
            if customer is None:
                raise ToolError(-32001, f"no customer with id {customer_id}")

            await cur.execute(
                """
                SELECT id, first_name, last_name, email, phone, title, is_primary
                FROM contacts
                WHERE customer_id = %(customer_id)s
                ORDER BY is_primary DESC, last_name
                """,
                {"customer_id": customer_id},
            )
            contacts = await cur.fetchall()

    return {"customer": customer, "contacts": contacts}


async def list_open_opportunities(arguments: Dict[str, Any]) -> Dict[str, Any]:
    owner_username = arguments.get("owner")

    query = """
        SELECT o.id, o.reference, o.name, o.customer_id, c.name AS customer_name,
               s.code AS status, o.owner_username, o.due_on, o.budget_amount
        FROM opportunities o
        JOIN customers c ON c.id = o.customer_id
        JOIN opportunity_statuses s ON s.id = o.status_id
        WHERE s.is_closed = false
    """
    params: Dict[str, Any] = {}
    if owner_username:
        query += " AND o.owner_username = %(owner_username)s"
        params["owner_username"] = owner_username
    query += " ORDER BY o.due_on NULLS LAST, o.id"

    async with await _connect() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            rows = await cur.fetchall()

    return {"opportunities": rows, "count": len(rows)}


async def get_quote(arguments: Dict[str, Any]) -> Dict[str, Any]:
    quote_id = arguments.get("quote_id")
    if not isinstance(quote_id, int):
        raise ToolError(-32602, "quote_id (integer) is required")

    async with await _connect() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT q.id, q.reference, q.opportunity_id, q.customer_id,
                       c.name AS customer_name, s.code AS status, q.owner_username,
                       q.total_amount, q.client_po_reference, q.issued_at
                FROM quotes q
                JOIN customers c ON c.id = q.customer_id
                JOIN quote_statuses s ON s.id = q.status_id
                WHERE q.id = %(quote_id)s
                """,
                {"quote_id": quote_id},
            )
            quote = await cur.fetchone()
            if quote is None:
                raise ToolError(-32001, f"no quote with id {quote_id}")

            await cur.execute(
                """
                SELECT id, product_id, description, quantity, unit_price, line_total
                FROM quote_lines
                WHERE quote_id = %(quote_id)s
                ORDER BY id
                """,
                {"quote_id": quote_id},
            )
            lines = await cur.fetchall()

    return {"quote": quote, "lines": lines}


TOOLS = {
    "get_customer": get_customer,
    "list_open_opportunities": list_open_opportunities,
    "get_quote": get_quote,
}


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    async with await _connect() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
            await cur.fetchone()
    return {"status": "ok"}


@app.post("/mcp")
async def mcp(request: Request) -> JSONResponse:
    # ADR-0037: workload identity check, independent of and in addition to
    # the NetworkPolicy boundary - a missing/wrong token is an
    # authentication failure (401), not a JSON-RPC-level error, since it's
    # about who is calling, not what they asked for.
    caller_token = request.headers.get("x-zuno-gateway-token", "")
    if not GATEWAY_WORKLOAD_TOKEN or not hmac.compare_digest(caller_token, GATEWAY_WORKLOAD_TOKEN):
        return JSONResponse({"detail": "missing or invalid X-Zuno-Gateway-Token"}, status_code=401)

    body = await request.json()
    request_id = body.get("id")

    def _error(code: int, message: str) -> JSONResponse:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
        )

    if body.get("method") != "tools/call":
        return _error(-32601, f"unsupported method '{body.get('method')}'")

    params = body.get("params") or {}
    tool_name = params.get("name")
    arguments = params.get("arguments") or {}

    handler = TOOLS.get(tool_name)
    if handler is None:
        return _error(-32601, f"unknown tool '{tool_name}'")

    try:
        result = await handler(arguments)
    except ToolError as exc:
        return _error(exc.code, exc.message)
    except Exception as exc:  # noqa: BLE001 - surface as a JSON-RPC error, not a 500
        return _error(-32000, f"internal error: {exc}")

    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})
