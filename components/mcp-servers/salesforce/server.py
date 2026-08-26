"""salesforce MCP server (ADR-0326/WP-33, protocol per ADR-0043).

Comage's live Salesforce integration: a real, standards-compliant MCP
server (the `mcp` SDK's `MCPServer`, streamable-HTTP transport, mounted at
/mcp - same shape as `components/mcp-servers/confluence`, which this
module is templated from) fronting the Salesforce REST API.

Exposes the three capabilities ADR-0326/WP-33 name for Comage:
`salesforce.opportunity.read`, `salesforce.opportunity.create`,
`salesforce.opportunity.update` (tool functions below: `read_opportunity`,
`create_opportunity`, `update_opportunity` - the MCP Gateway's binding
registry maps the logical capability ID to whichever `provider_tool` name
this server actually exposes, per ADR-0116).

`read_opportunity` is query/search-shaped (`query` in, `{query, results,
count}` out - the exact contract `components/mcp-servers/confluence`'s
`search_pages` already established), not an exact-id lookup: it is the
live_read_tool `app/graph/nodes.py`'s generic `tool_call_node` binds for
Comage's `check-deal-status` task, and that shared node always calls its
bound tool with `{"query": state["message"]}` - the same free-text turn
message Tekos's own `search_confluence` call receives. Matching
`search_pages`'s result shape (each item carrying `title`/`url`/`excerpt`)
is what lets the shared `_build_context_block`/`respond_node` citation
code in `nodes.py` work unmodified for a second agent - the actual proof
that ADR-0342's shape reuse is genuine, not just topological. SOQL `LIKE`
against Opportunity `Name` stands in for a real fuzzy-search index (no
Salesforce Search API integration in this demo).

Authentication mode is `service-identity` (ADR-0208): every call uses the
same technical Salesforce connected-app identity - a pre-issued OAuth2
bearer access token (the standard Salesforce REST API convention),
sourced from an `ExternalSecret` resolving `zuno/salesforce/technical`
(seeded by `ansible/roles/vault/tasks/install.yml`, keys `url`/
`access_token`) - never hardcoded, per ADR-0024. Refreshing an expired
token is an operator/Vault-rotation concern outside this server's scope
(no real Salesforce org is wired in this demo). The MCP Gateway's
`policy.evaluate()` authorizes the caller's agent/task/role/classification
*before* this shared service identity is ever used, satisfying ADR-0208's
requirement that a service-identity binding enforce Zuno subject/role
scope itself rather than relying on the downstream credential to do so -
this server has no per-user identity to check, by design.

ADR-0037: the gateway is still the trust boundary. This server does not
re-validate the caller's end-user JWT; every /mcp call must carry
X-Zuno-Gateway-Token, a shared secret only the gateway holds - same
Starlette-middleware pattern as confluence.

    POST /mcp    - real MCP streamable-HTTP transport (initialize,
                   tools/list, tools/call)
    GET /healthz -> 200 once SALESFORCE_BASE_URL/ACCESS_TOKEN are
                   configured. Deliberately does NOT make a live
                   Salesforce call on every probe, same reasoning as
                   confluence/server.py's own healthz.
"""
from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

SALESFORCE_BASE_URL = os.getenv("SALESFORCE_BASE_URL", "")
SALESFORCE_ACCESS_TOKEN = os.getenv("SALESFORCE_ACCESS_TOKEN", "")
SALESFORCE_API_VERSION = os.getenv("SALESFORCE_API_VERSION", "v59.0")
HTTP_TIMEOUT_SECONDS = float(os.getenv("SALESFORCE_HTTP_TIMEOUT_SECONDS", "20"))

# ADR-0037: required, not optional - this server has no purpose other than
# serving the gateway (same reasoning as confluence's server.py).
GATEWAY_WORKLOAD_TOKEN = os.getenv("MCP_GATEWAY_WORKLOAD_TOKEN", "")


class SalesforceConfigError(RuntimeError):
    pass


def _require_config() -> None:
    if not (SALESFORCE_BASE_URL and SALESFORCE_ACCESS_TOKEN):
        raise SalesforceConfigError(
            "SALESFORCE_BASE_URL/SALESFORCE_ACCESS_TOKEN are required "
            "(sourced from an ExternalSecret against secret/zuno/salesforce/technical "
            "- never hardcoded, ADR-0024)"
        )


def _client() -> httpx.AsyncClient:
    _require_config()
    return httpx.AsyncClient(
        base_url=f"{SALESFORCE_BASE_URL.rstrip('/')}/services/data/{SALESFORCE_API_VERSION}",
        headers={"Authorization": f"Bearer {SALESFORCE_ACCESS_TOKEN}"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )


def _summarize(opportunity_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Common projection of a Salesforce Opportunity record into the shape
    `create_opportunity`/`update_opportunity` return - `id`, `name`,
    `stage`, `amount`, `close_date`, `account_id`."""
    return {
        "id": opportunity_id,
        "name": fields.get("Name"),
        "stage": fields.get("StageName"),
        "amount": fields.get("Amount"),
        "close_date": fields.get("CloseDate"),
        "account_id": fields.get("AccountId"),
    }


def _as_search_result(record: Dict[str, Any]) -> Dict[str, Any]:
    """Projects one Opportunity record into `search_pages`'s own result
    shape (`title`/`url`/`excerpt`) - see the module docstring for why
    this match matters. `url` is synthesized (this demo has no real
    Salesforce org/domain to link into); `excerpt` is a short deterministic
    summary, not an LLM-generated one."""
    opportunity_id = record.get("Id", "")
    stage = record.get("StageName")
    amount = record.get("Amount")
    close_date = record.get("CloseDate")
    return {
        "id": opportunity_id,
        "title": record.get("Name"),
        "url": f"{SALESFORCE_BASE_URL.rstrip('/')}/lightning/r/Opportunity/{opportunity_id}/view"
        if opportunity_id
        else "",
        "excerpt": f"Stage: {stage}; Amount: {amount}; Close date: {close_date}",
        "stage": stage,
        "amount": amount,
        "close_date": close_date,
        "account_id": record.get("AccountId"),
    }


mcp_server = MCPServer(
    name="salesforce",
    version="0.1.0",
    instructions=(
        "Live Salesforce Opportunity access: read for current-state "
        "verification, create/update for writes. Indexed knowledge.sales "
        "(ADR-0205) is the normal read path - use these tools only for "
        "freshness-sensitive reads or any write."
    ),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Same requirement as confluence/server.py: the mounted MCP sub-app's
    # session manager needs the parent app's lifespan to run its task group.
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="salesforce MCP server", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    _require_config()
    return {"status": "ok"}


@mcp_server.tool()
async def read_opportunity(query: str, limit: int = 5) -> Dict[str, Any]:
    """Read the current state of the Opportunity/Opportunities matching a
    free-text query against their Name (most-recently-modified first) -
    the live current-value verification `check-deal-status` falls back to
    when indexed `knowledge.sales` content could be stale (ADR-0205)."""
    # SOQL has no query-parameter binding over REST; escape the one
    # metacharacter that would otherwise break out of the string literal
    # (Salesforce's own documented SOQL injection mitigation).
    escaped_query = query.replace("\\", "\\\\").replace("'", "\\'")
    soql = (
        "SELECT Id,Name,StageName,Amount,CloseDate,AccountId FROM Opportunity "
        f"WHERE Name LIKE '%{escaped_query}%' ORDER BY LastModifiedDate DESC LIMIT {int(limit)}"
    )
    async with _client() as client:
        resp = await client.get("/query", params={"q": soql})
        resp.raise_for_status()
        payload = resp.json()

    results = [_as_search_result(record) for record in payload.get("records", [])]
    return {"query": query, "results": results, "count": len(results)}


@mcp_server.tool()
async def create_opportunity(
    name: str, stage: str, close_date: str, amount: Optional[float] = None, account_id: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new Salesforce Opportunity."""
    request_body: Dict[str, Any] = {"Name": name, "StageName": stage, "CloseDate": close_date}
    if amount is not None:
        request_body["Amount"] = amount
    if account_id:
        request_body["AccountId"] = account_id

    async with _client() as client:
        resp = await client.post("/sobjects/Opportunity", json=request_body)
        if resp.status_code == 400:
            raise ValueError(f"Salesforce rejected opportunity creation: {resp.text}")
        resp.raise_for_status()
        payload = resp.json()

    opportunity_id = payload.get("id", "")
    return {"opportunity": _summarize(opportunity_id, request_body), "created": True}


@mcp_server.tool()
async def update_opportunity(
    opportunity_id: str,
    stage: Optional[str] = None,
    amount: Optional[float] = None,
    close_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Update an existing Salesforce Opportunity's stage/amount/close date by id."""
    request_body: Dict[str, Any] = {}
    if stage is not None:
        request_body["StageName"] = stage
    if amount is not None:
        request_body["Amount"] = amount
    if close_date is not None:
        request_body["CloseDate"] = close_date
    if not request_body:
        raise ValueError("update_opportunity requires at least one of stage/amount/close_date")

    async with _client() as client:
        resp = await client.patch(f"/sobjects/Opportunity/{opportunity_id}", json=request_body)
        if resp.status_code == 404:
            raise ValueError(f"no Salesforce opportunity with id {opportunity_id}")
        resp.raise_for_status()

        current_resp = await client.get(
            f"/sobjects/Opportunity/{opportunity_id}",
            params={"fields": "Name,StageName,Amount,CloseDate,AccountId"},
        )
        current_resp.raise_for_status()
        payload = current_resp.json()

    return {"opportunity": _summarize(opportunity_id, payload), "updated": True}


class GatewayTokenMiddleware(BaseHTTPMiddleware):
    """ADR-0037 workload-identity check, ahead of any MCP protocol handling
    (identical pattern to confluence's own middleware)."""

    async def dispatch(self, request: Request, call_next):
        caller_token = request.headers.get("x-zuno-gateway-token", "")
        if not GATEWAY_WORKLOAD_TOKEN or not hmac.compare_digest(caller_token, GATEWAY_WORKLOAD_TOKEN):
            return JSONResponse({"detail": "missing or invalid X-Zuno-Gateway-Token"}, status_code=401)
        return await call_next(request)


mcp_asgi_app: ASGIApp = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(
        allowed_hosts=os.getenv(
            "MCP_ALLOWED_HOSTS",
            "salesforce-mcp.zuno-ai-run.svc:8000,"
            "salesforce-mcp.zuno-ai-run.svc.cluster.local:8000,"
            "salesforce-mcp:8000,localhost:8000,127.0.0.1:8000",
        ).split(","),
    ),
)
mcp_asgi_app.add_middleware(GatewayTokenMiddleware)
app.mount("/", mcp_asgi_app)
