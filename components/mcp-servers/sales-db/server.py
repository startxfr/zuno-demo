"""sales-db MCP server (ADR-0017, protocol per ADR-0043).

Exposes five deterministic, read-only tools over the SXA-derived legacy
sales-operations schema (data/sxa/schema/001_init.sql): get_customer,
list_open_opportunities, get_quote (per-record reads, `sxa.*` capabilities
per ADR-0206/WP-23 - this data is legacy SXA, never current Salesforce),
plus aggregate_revenue_by_year and lookup_record (deterministic structured
queries added by WP-23, narrower policy: Sales + Direction/`board` only,
C3 by default). Every query is parameterized and read-only - there is no
path from an LLM-constructed string to SQL here, which is the entire
point of ADR-0017 ("no direct LLM-to-DB freedom"); the aggregation tools
exist precisely so an exact number is never something a RAG chunk has to
approximate.

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

# ADR-0216/WP-065: engine-select, default "postgres" (this component's
# original, still-tested fixture path - ADR-0016, superseded for the live
# target only). Mirrors ADR-0352's embeddedMariaDB/externalMySQL
# mode-switch precedent exactly: same tool set, same parameterized-query
# posture (ADR-0017), same allowed_groups/min_classification gates in
# policies/tools/tool-policy.yaml - only the connection target changes,
# and only once WP-065 Part B confirms real MariaDB data is loaded.
DB_ENGINE = os.getenv("SXA_DB_ENGINE", "postgres").strip().lower()
MARIADB_HOST = os.getenv("SXA_MARIADB_HOST", "mariadb.zuno-data.svc.cluster.local")
MARIADB_PORT = int(os.getenv("SXA_MARIADB_PORT", "3306"))
MARIADB_DATABASE = os.getenv("SXA_MARIADB_DATABASE", "sxa")
MARIADB_USER = os.getenv("SXA_MARIADB_USER")
MARIADB_PASSWORD = os.getenv("SXA_MARIADB_PASSWORD")

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


async def _connect():
    """Engine-select (ADR-0216/WP-065). Every tool below uses the same
    `async with await _connect() as conn: async with conn.cursor() as cur:`
    shape regardless of engine - aiomysql's Connection/Cursor both support
    the same async-context-manager protocol psycopg's AsyncConnection
    does, and aiomysql.DictCursor gives the same dict-row shape
    `row_factory=dict_row` does, so no tool body needs an engine-specific
    branch."""
    if DB_ENGINE == "mariadb":
        import aiomysql

        if not MARIADB_USER or not MARIADB_PASSWORD:
            raise RuntimeError(
                "SXA_MARIADB_USER/SXA_MARIADB_PASSWORD are required when "
                "SXA_DB_ENGINE=mariadb (sourced from an ExternalSecret "
                "against secret/zuno/sxa/mariadb-db, ADR-0216)"
            )
        return await aiomysql.connect(
            host=MARIADB_HOST,
            port=MARIADB_PORT,
            db=MARIADB_DATABASE,
            user=MARIADB_USER,
            password=MARIADB_PASSWORD,
            cursorclass=aiomysql.DictCursor,
        )
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


_VALID_INVOICE_STATUSES = {"draft", "sent", "paid", "overdue", "cancelled"}


@mcp_server.tool()
async def aggregate_revenue_by_year(year: int, status: Optional[str] = None) -> Dict[str, Any]:
    """Deterministic revenue aggregation (sum of invoice totals) for a
    single calendar year, derived from `sent_on` - the year the invoice
    was issued to the customer, not `paid_on` (unpaid/overdue invoices
    still count as billed revenue for the year). Optional `status` narrows
    to one invoice_statuses code (paid, sent, ...); an unrecognized status
    is a caller error, not silently ignored - ADR-0206's "exact numbers,
    never approximated" applies to the filter as much as the sum."""
    if status is not None and status not in _VALID_INVOICE_STATUSES:
        raise ValueError(
            f"unknown status '{status}' - must be one of {sorted(_VALID_INVOICE_STATUSES)}"
        )
    query = """
        SELECT coalesce(sum(i.total_amount), 0) AS total_revenue, count(*) AS invoice_count
        FROM invoices i
        JOIN invoice_statuses s ON s.id = i.status_id
        WHERE extract(year FROM i.sent_on) = %(year)s
    """
    params: Dict[str, Any] = {"year": year}
    if status:
        query += " AND s.code = %(status)s"
        params["status"] = status

    async with await _connect() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            row = await cur.fetchone()

    return {
        "year": year,
        "status_filter": status,
        "total_revenue": row["total_revenue"],
        "invoice_count": row["invoice_count"],
    }


_LOOKUP_TABLES = {
    "customer": ("customers", "id, name, legal_name, industry, city, country"),
    "opportunity": ("opportunities", "id, reference, name, customer_id, budget_amount, due_on"),
    "quote": ("quotes", "id, reference, opportunity_id, customer_id, total_amount, issued_at"),
    "order": ("orders", "id, reference, customer_id, total_amount, created_at"),
    "invoice": ("invoices", "id, reference, order_id, customer_id, total_amount, sent_on, paid_on"),
}


@mcp_server.tool()
async def lookup_record(record_type: str, record_id: int) -> Dict[str, Any]:
    """Deterministic single-row lookup by numeric id across a fixed,
    allow-listed set of legacy SXA tables (customer/opportunity/quote/
    order/invoice) - a generalization of get_customer/get_quote for the
    other legacy record types, still with no path from caller input to
    SQL text: record_type only ever selects a column list from
    _LOOKUP_TABLES above, never gets interpolated into the query itself."""
    if record_type not in _LOOKUP_TABLES:
        raise ValueError(
            f"unknown record_type '{record_type}' - must be one of {sorted(_LOOKUP_TABLES)}"
        )
    table, columns = _LOOKUP_TABLES[record_type]

    async with await _connect() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"SELECT {columns} FROM {table} WHERE id = %(record_id)s",
                {"record_id": record_id},
            )
            record = await cur.fetchone()
            if record is None:
                raise ValueError(f"no {record_type} with id {record_id}")

    return {"record_type": record_type, "record": record}


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
