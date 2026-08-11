"""sales-db MCP server (ADR-0017, protocol per ADR-0043).

Exposes exactly three deterministic, read-only tools over the SXA-derived
sales-operations schema (data/sxa/schema/001_init.sql): get_customer,
list_open_opportunities, get_quote. Every query is parameterized and
read-only - there is no path from an LLM-constructed string to SQL here,
which is the entire point of ADR-0017 ("no direct LLM-to-DB freedom").

ADR-0043: the tool-call surface is a real, standards-compliant MCP server
(the `mcp` SDK's MCPServer, streamable-HTTP transport, mounted at /mcp),
not the hand-rolled JSON-RPC-shaped endpoint this file used before. The
gateway is still the trust boundary - this server does not re-validate
the caller's end-user JWT, it trusts the gateway's ADR-0011 policy
intersection already happened - and ADR-0037's workload-identity
requirement is unchanged in spirit, only relocated: network location
alone (gitops/charts/mcp-sales-db's NetworkPolicy, restricting ingress to
the gateway's pods specifically) is not trusted as the sole boundary,
every call to /mcp must still carry X-Zuno-Gateway-Token, a shared secret
only the gateway holds (vault-generated, secret/zuno/mcp/gateway-workload-token).
That check now runs as Starlette middleware wrapping the mounted MCP
sub-app, ahead of any MCP protocol handling, rather than as the first
line of a single custom route handler - functionally identical (missing/
wrong token still short-circuits to a 401 before anything else runs).

    POST /mcp   - real MCP streamable-HTTP transport (initialize,
                  tools/list, tools/call - see components/mcp-gateway/
                  app/downstream.py, the only caller)
    GET /healthz -> 200 once a DB connection can be acquired.
"""
from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

# zuno-postgresql-primary is PGO's own auto-created Service for the
# zuno-postgresql PostgresCluster - there is no plain "postgresql"
# Service, and no "-rw"-suffixed one either (that was CloudNativePG's
# convention - see ansible/roles/postgresql/README.md).
DB_HOST = os.getenv("PGHOST", "zuno-postgresql-primary.zuno-data.svc.cluster.local")
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


async def _connect() -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(_conninfo(), row_factory=dict_row)


mcp_server = MCPServer(
    name="sales-db",
    version="0.1.0",
    instructions="Read-only sales-operations lookups: customers, open opportunities, quotes.",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The mounted MCP sub-app's streamable-HTTP session manager runs its own
    # background task group - it must be entered here, in the parent app's
    # lifespan, or every request fails with "Task group is not initialized"
    # (mounting alone does not propagate ASGI lifespan startup to it).
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="sales-db MCP server", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    async with await _connect() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
            await cur.fetchone()
    return {"status": "ok"}


@mcp_server.tool()
async def get_customer(customer_id: int) -> Dict[str, Any]:
    """Look up a customer and its contacts by numeric customer id."""
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
                raise ValueError(f"no customer with id {customer_id}")

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


@mcp_server.tool()
async def list_open_opportunities(owner: Optional[str] = None) -> Dict[str, Any]:
    """List open (not-closed) sales opportunities, optionally filtered by owner username."""
    query = """
        SELECT o.id, o.reference, o.name, o.customer_id, c.name AS customer_name,
               s.code AS status, o.owner_username, o.due_on, o.budget_amount
        FROM opportunities o
        JOIN customers c ON c.id = o.customer_id
        JOIN opportunity_statuses s ON s.id = o.status_id
        WHERE s.is_closed = false
    """
    params: Dict[str, Any] = {}
    if owner:
        query += " AND o.owner_username = %(owner_username)s"
        params["owner_username"] = owner
    query += " ORDER BY o.due_on NULLS LAST, o.id"

    async with await _connect() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            rows = await cur.fetchall()

    return {"opportunities": rows, "count": len(rows)}


@mcp_server.tool()
async def get_quote(quote_id: int) -> Dict[str, Any]:
    """Look up a quote and its line items by numeric quote id."""
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
                raise ValueError(f"no quote with id {quote_id}")

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


class GatewayTokenMiddleware(BaseHTTPMiddleware):
    """ADR-0037 workload-identity check, ahead of any MCP protocol handling.

    Constant-time comparison, same as before - this is a 401 authentication
    failure (who is calling), not an MCP/JSON-RPC-level error (what they asked).
    """

    async def dispatch(self, request: Request, call_next):
        caller_token = request.headers.get("x-zuno-gateway-token", "")
        if not GATEWAY_WORKLOAD_TOKEN or not hmac.compare_digest(caller_token, GATEWAY_WORKLOAD_TOKEN):
            return JSONResponse({"detail": "missing or invalid X-Zuno-Gateway-Token"}, status_code=401)
        return await call_next(request)


mcp_asgi_app: ASGIApp = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    # DNS-rebinding protection (on by default) checks the Host header
    # against this allow-list - the Service DNS names the gateway
    # actually reaches this pod through (gitops/charts/mcp-sales-db's
    # Service "sales-db-mcp" in zuno-ai-run, port 8000, matching
    # components/mcp-gateway/app/downstream.py's SALES_DB_MCP_URL
    # default), plus localhost for direct in-pod debugging. Extend via
    # MCP_ALLOWED_HOSTS (comma-separated) if the Service/namespace name
    # ever changes rather than hardcoding a second place.
    transport_security=TransportSecuritySettings(
        allowed_hosts=os.getenv(
            "MCP_ALLOWED_HOSTS",
            "sales-db-mcp.zuno-ai-run.svc:8000,"
            "sales-db-mcp.zuno-ai-run.svc.cluster.local:8000,"
            "sales-db-mcp:8000,localhost:8000,127.0.0.1:8000",
        ).split(","),
    ),
)
mcp_asgi_app.add_middleware(GatewayTokenMiddleware)
app.mount("/", mcp_asgi_app)
