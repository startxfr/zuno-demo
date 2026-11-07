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

import base64
import hashlib
import hmac
import json
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Mapping, Optional

import httpx
from fastapi import FastAPI
from mcp.server.mcpserver import Context, MCPServer
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


# --------------------------------------------------------------------------
# ADR-0603 M12 (WP-225 lot B): the signed caller context.
#
# The gateway signs who a call is for (sub, groups, email, username, the tool,
# a timestamp, this server's name) from the token it has validated, and sends it as
# X-Zuno-Caller-Context / X-Zuno-Caller-Signature (components/mcp-gateway/app/
# caller_context.py), only to backends whose binding declares caller_context.
# The key is derived per backend from the workload token this server already holds. Duplicated in each server: an image is built from its own
# directory only (ADR-0119). A missing, forged, stale or other-tool context
# verifies as None; a server that needs it then refuses (fail closed).
# --------------------------------------------------------------------------

# The audience of the caller context: this server's backend name in
# platform/bindings/tools/tool-bindings.yaml.
CALLER_CONTEXT_AUDIENCE = "salesforce"
CALLER_CONTEXT_HEADER = "x-zuno-caller-context"
CALLER_SIGNATURE_HEADER = "x-zuno-caller-signature"
CALLER_CONTEXT_MAX_AGE_SECONDS = int(os.getenv("CALLER_CONTEXT_MAX_AGE_SECONDS", "300"))
# A context dated in the future beyond clock skew is refused, so a signed context
# cannot be minted to stay valid for longer than its age bound.
CALLER_CONTEXT_MAX_SKEW_SECONDS = 30


def _caller_context_key() -> bytes:
    # Per backend: HMAC(token, label + ":" + this server's name). A context signed
    # for another backend does not verify here.
    label = b"zuno-caller-context-v1:" + CALLER_CONTEXT_AUDIENCE.encode("utf-8")
    return hmac.new(GATEWAY_WORKLOAD_TOKEN.encode("utf-8"), label, hashlib.sha256).digest()


def _verified_caller(headers: Optional[Mapping[str, str]], tool: str) -> Optional[Dict[str, Any]]:
    if not headers or not GATEWAY_WORKLOAD_TOKEN:
        return None
    raw = headers.get(CALLER_CONTEXT_HEADER) or ""
    signature = headers.get(CALLER_SIGNATURE_HEADER) or ""
    if not raw or not signature:
        return None
    expected = hmac.new(_caller_context_key(), raw.encode("ascii", "replace"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("v") != 1:
        return None
    if payload.get("aud") != CALLER_CONTEXT_AUDIENCE or payload.get("tool") != tool:
        return None
    iat = payload.get("iat")
    now = time.time()
    if not isinstance(iat, int) or iat > now + CALLER_CONTEXT_MAX_SKEW_SECONDS or now - iat > CALLER_CONTEXT_MAX_AGE_SECONDS:
        return None
    groups = payload.get("groups")
    return {
        "sub": str(payload.get("sub") or ""),
        "groups": [str(g) for g in groups] if isinstance(groups, list) else [],
        "email": str(payload.get("email") or "").lower(),
        "email_verified": payload.get("email_verified") is True,
        "username": str(payload.get("username") or ""),
    }


def _caller(ctx: Optional[Context], tool: str) -> Optional[Dict[str, Any]]:
    """The verified caller of this tool call, or None (no context, or not verified)."""
    if ctx is None:
        return None
    try:
        headers = ctx.headers
    except Exception:  # noqa: BLE001 - outside a request (a direct call in a test)
        return None
    return _verified_caller(headers, tool)


# --------------------------------------------------------------------------
# ADR-0603 M12 (WP-225 lot B): owner scoping.
#
# SALESFORCE_OWNER_SCOPING=owner (chart value ownerScoping.enabled) limits every
# tool to the Opportunities the caller owns: the caller is the Salesforce User
# whose Email is the email of the signed caller context (the validated token's
# `email` claim), and only when the token's `email_verified` is true: the realm
# does not verify emails and a user may edit their own, so an unverified address
# names nobody and is refused. A caller in one of SALESFORCE_ALL_RECORDS_GROUPS
# (ownerScoping.allRecordsGroups) is entitled to every record, as before. Off:
# the behaviour before WP-225, every caller sees what the technical identity sees.
# --------------------------------------------------------------------------

# Salesforce record ids: 15 or 18 alphanumeric characters.
_RECORD_ID_RE = re.compile(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?")


def _soql_quote(value: str) -> str:
    """A SOQL string literal (backslash and quote escaped)."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _owner_scoping_enabled() -> bool:
    return os.getenv("SALESFORCE_OWNER_SCOPING", "off").strip().lower() == "owner"


def _all_records_groups() -> List[str]:
    return [g.strip() for g in os.getenv("SALESFORCE_ALL_RECORDS_GROUPS", "").split(",") if g.strip()]


async def _owner_scope(client: httpx.AsyncClient, ctx: Optional[Context], tool: str) -> Optional[str]:
    """None when every record is allowed (scoping off, or an all-records group);
    else the Salesforce User id the call is limited to. Raises PermissionError when
    the caller cannot be identified: no verified context, no email, or no single
    active Salesforce User with that email."""
    if not _owner_scoping_enabled():
        return None
    caller = _caller(ctx, tool)
    if caller is None:
        raise PermissionError(f"{tool} is refused: owner scoping is on and the call carries no verified caller context")
    if set(caller["groups"]) & set(_all_records_groups()):
        return None
    email = caller["email"]
    if not email:
        raise PermissionError(f"{tool} is refused: owner scoping needs the caller's email, and the token carries none")
    if not caller.get("email_verified"):
        raise PermissionError(
            f"{tool} is refused: owner scoping needs a verified email, and the token's email_verified is not true"
        )
    soql = f"SELECT Id FROM User WHERE Email = {_soql_quote(email)} AND IsActive = true LIMIT 2"
    resp = await client.get("/query", params={"q": soql})
    resp.raise_for_status()
    records = resp.json().get("records", [])
    if len(records) != 1:
        raise PermissionError(
            f"{tool} is refused: owner scoping found {len(records)} active Salesforce users for the caller's email"
        )
    user_id = str(records[0].get("Id") or "")
    if not _RECORD_ID_RE.fullmatch(user_id):
        raise PermissionError(f"{tool} is refused: Salesforce returned an invalid user id")
    return user_id


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



# ADR-0603 / WP-222: ceiling for the model-chosen limit.
MAX_OPPORTUNITY_LIMIT = 50

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
async def read_opportunity(query: str, limit: int = 5, ctx: Optional[Context] = None) -> Dict[str, Any]:
    """Read the current state of the Opportunity/Opportunities matching a
    free-text query against their Name (most-recently-modified first) -
    the live current-value verification `check-deal-status` falls back to
    when indexed `knowledge.sales` content could be stale (ADR-0205)."""
    # SOQL has no query-parameter binding over REST: escape the quote that
    # would break out of the string literal (Salesforce's documented SOQL
    # injection mitigation), plus the LIKE wildcards % and _ so a model-chosen
    # query cannot widen the match (ADR-0603 / WP-222).
    escaped_query = (
        query.replace("\\", "\\\\").replace("'", "\\'").replace("%", "\\%").replace("_", "\\_")
    )
    async with _client() as client:
        # ADR-0603 M12: only the caller's own records when owner scoping is on.
        owner_id = await _owner_scope(client, ctx, "read_opportunity")
        owner_clause = f" AND OwnerId = {_soql_quote(owner_id)}" if owner_id else ""
        soql = (
            "SELECT Id,Name,StageName,Amount,CloseDate,AccountId FROM Opportunity "
            f"WHERE Name LIKE '%{escaped_query}%'{owner_clause} ORDER BY LastModifiedDate DESC "
            f"LIMIT {max(1, min(int(limit), MAX_OPPORTUNITY_LIMIT))}"
        )
        resp = await client.get("/query", params={"q": soql})
        resp.raise_for_status()
        payload = resp.json()

    results = [_as_search_result(record) for record in payload.get("records", [])]
    return {"query": query, "results": results, "count": len(results)}


@mcp_server.tool()
async def create_opportunity(
    name: str,
    stage: str,
    close_date: str,
    amount: Optional[float] = None,
    account_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a new Salesforce Opportunity."""
    request_body: Dict[str, Any] = {"Name": name, "StageName": stage, "CloseDate": close_date}
    if amount is not None:
        request_body["Amount"] = amount
    if account_id:
        request_body["AccountId"] = account_id

    async with _client() as client:
        # ADR-0603 M12: a record created for a caller is owned by that caller, so
        # the caller (and not the technical identity) can read and update it.
        owner_id = await _owner_scope(client, ctx, "create_opportunity")
        if owner_id:
            request_body["OwnerId"] = owner_id
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
    ctx: Optional[Context] = None,
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

    # ADR-0603 M12: the id lands in a URL path; checked whether or not owner scoping is on.
    if not _RECORD_ID_RE.fullmatch(str(opportunity_id)):
        raise ValueError("opportunity_id must be a Salesforce record id (15 or 18 letters and digits)")
    async with _client() as client:
        owner_id = await _owner_scope(client, ctx, "update_opportunity")
        if owner_id:
            # ADR-0603 M12: the record must be the caller's before anything is written.
            # A record of someone else answers as a missing one (no existence oracle).
            check = (
                f"SELECT Id FROM Opportunity WHERE Id = {_soql_quote(opportunity_id)} "
                f"AND OwnerId = {_soql_quote(owner_id)} LIMIT 1"
            )
            owned = await client.get("/query", params={"q": check})
            owned.raise_for_status()
            if not owned.json().get("records"):
                raise ValueError(f"no Salesforce opportunity with id {opportunity_id} owned by the caller")
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
