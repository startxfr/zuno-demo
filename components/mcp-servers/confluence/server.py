"""confluence MCP server (ADR-0117, protocol per ADR-0043).

Zuno's first real external MCP integration: a real, standards-compliant
MCP server (the `mcp` SDK's `MCPServer`, streamable-HTTP transport,
mounted at /mcp - same shape as `components/mcp-servers/sales-db`)
fronting the real Confluence Cloud REST API, replacing
`components/mcp-gateway/app/handlers/confluence.py`'s demo-mode handler.

Exposes exactly the four capabilities ADR-0116 already named for
Confluence: `confluence.page.search`, `confluence.page.read`,
`confluence.page.create`, `confluence.page.update` (tool functions below:
`search_pages`, `read_page`, `create_page`, `update_page` - the MCP
Gateway's binding registry maps the logical capability ID to whichever
`provider_tool` name this server actually exposes, per ADR-0116).

Authentication mode is `service-identity` (ADR-0208): every call uses the
same technical Confluence identity (email + API token, HTTP Basic Auth -
the standard Atlassian Cloud REST API convention, matching
`components/rag-ingestion/src/rag_ingestion.py`'s own `_confluence_auth`
for consistency), sourced from an `ExternalSecret` resolving
`zuno/confluence/technical` (seeded by
`ansible/roles/vault/tasks/install.yml`, keys `url`/`email`/`token`) -
never hardcoded, per ADR-0024. The MCP Gateway's `policy.evaluate()`
authorizes the caller's agent/task/role/classification *before* this
shared service identity is ever used, satisfying ADR-0208's requirement
that a service-identity binding enforce Zuno subject/role scope itself
rather than relying on the downstream credential to do so - this server
has no per-user identity to check, by design.

ADR-0037: the gateway is still the trust boundary. This server does not
re-validate the caller's end-user JWT; every /mcp call must carry
X-Zuno-Gateway-Token, a shared secret only the gateway holds - same
Starlette-middleware pattern as sales-db.

    POST /mcp    - real MCP streamable-HTTP transport (initialize,
                   tools/list, tools/call)
    GET /healthz -> 200 once CONFLUENCE_BASE_URL/EMAIL/API_TOKEN are
                   configured. Deliberately does NOT make a live
                   Confluence call on every probe (unlike sales-db's
                   healthz, which does a free local DB round-trip) - a
                   Kubernetes liveness/readiness probe firing every
                   ~10-15s against a real external SaaS API would be a
                   needless, avoidable load/quota cost.
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

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL", "")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL", "")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN", "")
HTTP_TIMEOUT_SECONDS = float(os.getenv("CONFLUENCE_HTTP_TIMEOUT_SECONDS", "20"))

# ADR-0037: required, not optional - this server has no purpose other than
# serving the gateway (same reasoning as sales-db/server.py).
GATEWAY_WORKLOAD_TOKEN = os.getenv("MCP_GATEWAY_WORKLOAD_TOKEN", "")


class ConfluenceConfigError(RuntimeError):
    pass


def _require_config() -> None:
    if not (CONFLUENCE_BASE_URL and CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN):
        raise ConfluenceConfigError(
            "CONFLUENCE_BASE_URL/CONFLUENCE_EMAIL/CONFLUENCE_API_TOKEN are required "
            "(sourced from an ExternalSecret against secret/zuno/confluence/technical "
            "- never hardcoded, ADR-0024)"
        )


def _client() -> httpx.AsyncClient:
    _require_config()
    return httpx.AsyncClient(
        base_url=f"{CONFLUENCE_BASE_URL.rstrip('/')}/wiki/rest/api",
        auth=(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN),
        timeout=HTTP_TIMEOUT_SECONDS,
    )


def _summarize(content: Dict[str, Any]) -> Dict[str, Any]:
    """Common projection of a Confluence `content` object into the shape
    every tool below returns - `id`, `title`, `space`, `url`, `version`,
    plus a `body` excerpt when the response expanded it. Mirrors the demo
    handler's field names (`id`, `title`, `space`, `url`) it replaces, so
    existing callers/tests reading those fields keep working."""
    space_key = (content.get("space") or {}).get("key", "")
    webui = ((content.get("_links") or {}).get("webui")) or ""
    base = (content.get("_links") or {}).get("base", CONFLUENCE_BASE_URL)
    body = ((content.get("body") or {}).get("storage") or {}).get("value")
    return {
        "id": content.get("id"),
        "title": content.get("title"),
        "space": space_key,
        "url": f"{base}{webui}" if webui else None,
        "version": (content.get("version") or {}).get("number"),
        **({"body": body} if body is not None else {}),
    }


mcp_server = MCPServer(
    name="confluence",
    version="0.1.0",
    instructions=(
        "Live Confluence Cloud access: search/read pages for current state, "
        "create/update pages for writes. Indexed knowledge.tech (ADR-0330) "
        "is the normal read path (ADR-0205) - use these tools only for "
        "freshness-sensitive reads or any write."
    ),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Same requirement as sales-db/server.py: the mounted MCP sub-app's
    # session manager needs the parent app's lifespan to run its task group.
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="confluence MCP server", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    _require_config()
    return {"status": "ok"}


@mcp_server.tool()
async def search_pages(query: str, space: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """Search Confluence pages by text (CQL), optionally scoped to a space key."""
    cql = f'type=page and text~"{query}"'
    if space:
        cql = f'space="{space}" and {cql}'
    async with _client() as client:
        resp = await client.get(
            "/content/search",
            params={"cql": cql, "limit": limit, "expand": "space,version"},
        )
        resp.raise_for_status()
        payload = resp.json()

    results = [_summarize(item) for item in payload.get("results", [])]
    return {"query": query, "results": results, "count": len(results)}


@mcp_server.tool()
async def read_page(page_id: str) -> Dict[str, Any]:
    """Read a Confluence page's current content and metadata by id."""
    async with _client() as client:
        resp = await client.get(
            f"/content/{page_id}",
            params={"expand": "space,version,body.storage"},
        )
        if resp.status_code == 404:
            raise ValueError(f"no Confluence page with id {page_id}")
        resp.raise_for_status()
        payload = resp.json()

    return {"page": _summarize(payload)}


@mcp_server.tool()
async def create_page(space_key: str, title: str, body_html: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a new Confluence page in the given space, optionally under a parent page."""
    request_body: Dict[str, Any] = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {"storage": {"value": body_html, "representation": "storage"}},
    }
    if parent_id:
        request_body["ancestors"] = [{"id": parent_id}]

    async with _client() as client:
        resp = await client.post("/content", json=request_body)
        if resp.status_code == 400:
            raise ValueError(f"Confluence rejected page creation: {resp.text}")
        resp.raise_for_status()
        payload = resp.json()

    return {"page": _summarize(payload), "created": True}


@mcp_server.tool()
async def update_page(page_id: str, body_html: str, title: Optional[str] = None) -> Dict[str, Any]:
    """Update an existing Confluence page's content (and optionally its title) by id."""
    async with _client() as client:
        current_resp = await client.get(f"/content/{page_id}", params={"expand": "version,space"})
        if current_resp.status_code == 404:
            raise ValueError(f"no Confluence page with id {page_id}")
        current_resp.raise_for_status()
        current = current_resp.json()
        current_version = (current.get("version") or {}).get("number", 0)

        request_body: Dict[str, Any] = {
            "id": page_id,
            "type": "page",
            "title": title or current.get("title"),
            "space": {"key": (current.get("space") or {}).get("key")},
            "body": {"storage": {"value": body_html, "representation": "storage"}},
            "version": {"number": current_version + 1},
        }
        resp = await client.put(f"/content/{page_id}", json=request_body)
        if resp.status_code == 409:
            raise ValueError(
                f"Confluence page {page_id} was modified concurrently (version conflict) - retry"
            )
        resp.raise_for_status()
        payload = resp.json()

    return {"page": _summarize(payload), "updated": True}


class GatewayTokenMiddleware(BaseHTTPMiddleware):
    """ADR-0037 workload-identity check, ahead of any MCP protocol handling
    (identical pattern to sales-db/server.py's own middleware)."""

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
            "confluence-mcp.zuno-ai-run.svc:8000,"
            "confluence-mcp.zuno-ai-run.svc.cluster.local:8000,"
            "confluence-mcp:8000,localhost:8000,127.0.0.1:8000",
        ).split(","),
    ),
)
mcp_asgi_app.add_middleware(GatewayTokenMiddleware)
app.mount("/", mcp_asgi_app)
