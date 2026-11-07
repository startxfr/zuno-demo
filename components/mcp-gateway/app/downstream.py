"""Routes an authorized tool invocation to the physical backend its
ADR-0116 binding names.

Routing is no longer keyed by hard-coded tool-name sets: main.py resolves
the caller's tool name (canonical capability ID or migration alias) through
app/bindings.py's registry BEFORE calling ``invoke()``, and this module
dispatches purely on the resolved ``Binding`` - its transport, endpoint and
the backend's own ``provider_tool`` name. An unresolved binding fails
closed here with the same ``DownstreamError`` contract callers already
depend on; no name ever falls through to a default backend.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
import httpx2  # the mcp SDK's own httpx fork/client type, required by streamable_http_client
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from app import caller_context
from app.bindings import Binding
from app.handlers import diagram_gen, drive, email_report, gmail, image_gen, rag_query, web_search

logger = logging.getLogger("mcp_gateway.downstream")

# Matches app/clients/mcp_client.py's MCP_TIMEOUT_SECONDS on the
# agent-runtime side (also bumped from 20s) - live-cluster-confirmed
# 2026-08-23: git.repository.list against the real "openshift" GitHub org
# (500+ repos, server-side paginated) still timed out here even after that
# other hop was widened, since this is a second, independent timeout on
# the gateway's own call to the downstream MCP server.
DOWNSTREAM_TIMEOUT_SECONDS = float(os.getenv("DOWNSTREAM_TIMEOUT_SECONDS", "40"))

# ADR-0037: a shared secret (vault-generated,
# ansible/roles/vault/tasks/configure.yml,
# secret/zuno/mcp/gateway-workload-token) proving this call actually came
# from the MCP Gateway, not merely from a pod that happens to be
# network-adjacent - NetworkPolicy is the first layer (gitops/charts/
# mcp-each downstream server's NetworkPolicy restricts ingress to this service's pods
# specifically); this is the "validate the gateway workload identity in
# addition to relying on network location" second layer this ADR requires
# for sensitive MCP servers. Not enforced as a hard startup requirement
# here (unlike the downstream server's own validation) so this gateway still starts and
# serves every other tool if the secret hasn't landed yet - the MCP call
# itself degrades to a clear 502 from the missing/rejected header.
MCP_GATEWAY_WORKLOAD_TOKEN = os.getenv("MCP_GATEWAY_WORKLOAD_TOKEN", "")

# The in-process demo-mode backends themselves (ADR-0116: this is the
# physical-backend catalog the `in-process` transport dispatches into, keyed
# by the binding's `handler` field - not a per-tool routing set; which tool
# reaches which handler is the registry's decision, not this module's).
IN_PROCESS_HANDLERS = {
    "drive": drive.handle,
    # ADR-0326 (WP-31): Arkos's delegated Drive/Docs write - same module,
    # two more single-purpose handler names (see app/handlers/drive.py's
    # own docstring for why one name maps to one function here rather than
    # branching inside a shared handle()).
    "drive_create": drive.handle_create,
    "drive_update": drive.handle_update,
    "gmail": gmail.handle,
    "web_search": web_search.handle,
    "email_report": email_report.handle,
    # ADR-0415: not a demo-mode stub like the rest of this dict - calls
    # the real, already-deployed components/ai-gateway in-cluster.
    "image_gen": image_gen.handle,
    # ADR-0516: same posture - calls the real, in-cluster diagram-render
    # service (never an external SaaS call, unlike image_gen above).
    "diagram_gen": diagram_gen.handle,
    # ADR-0524 clause 3 extension (2026-09-09): calls UnifAI's RAG server over
    # the knowledge.tech sources with the caller's own token - see
    # app/handlers/rag_query.py's own docstring.
    "rag_query": rag_query.handle,
}


class DownstreamError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


async def invoke(
    binding: Optional[Binding],
    tool_name: str,
    arguments: Dict[str, Any],
    caller_sub: str,
    bearer_token: str,
    delegated_token: Optional[str] = None,
    caller_groups: Optional[List[str]] = None,
    caller_claims: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if binding is None:
        # Fail closed (ADR-0116): deterministic error, no backend contacted.
        raise DownstreamError(502, f"no backend binding registered for tool '{tool_name}'")

    if binding.transport == "streamable-http":
        return await _invoke_streamable_http(
            binding,
            arguments,
            bearer_token,
            caller_sub=caller_sub,
            caller_groups=caller_groups,
            caller_claims=caller_claims,
        )

    if binding.transport == "in-process":
        handler = IN_PROCESS_HANDLERS.get(binding.handler or "")
        if handler is None:
            raise DownstreamError(
                502,
                f"binding '{binding.capability}' names unknown in-process handler "
                f"'{binding.handler}'",
            )
        # ADR-0208: delegated_token is None for every non-delegated-user
        # binding (app/main.py only resolves one when auth_mode requires
        # it) - handlers that don't need it simply ignore the kwarg.
        # ADR-0415: bearer_token is forwarded the same way, for the one
        # handler (image_gen) that makes a real in-cluster call and needs
        # the caller's own identity to reach it - every other handler
        # ignores it, same as delegated_token above. caller_groups follows
        # the identical pattern, added for rag_query (ADR-0524 clause 3
        # extension); rag_query now forwards the bearer token to UnifAI,
        # which resolves the groups itself, and ignores caller_groups.
        return await handler(
            arguments,
            caller_sub,
            delegated_token=delegated_token,
            bearer_token=bearer_token,
            caller_groups=caller_groups,
        )

    raise DownstreamError(
        502, f"binding '{binding.capability}' has unsupported transport '{binding.transport}'"
    )


async def _invoke_streamable_http(
    binding: Binding,
    arguments: Dict[str, Any],
    bearer_token: str,
    *,
    caller_sub: str = "",
    caller_groups: Optional[List[str]] = None,
    caller_claims: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # ADR-0043: real, standards-compliant MCP servers (streamable-HTTP
    # transport, e.g. components/mcp-servers/salesforce/server.py mounted at
    # /mcp) reached via the official `mcp` SDK's ClientSession. The endpoint
    # comes from the binding's registry entry (environment-resolved at call
    # time), and the tool actually called is the binding's `provider_tool` -
    # the backend's own name, which callers using canonical capability IDs
    # never see.
    #
    # Authorization is still forwarded for audit/observability even though
    # downstream servers don't themselves re-validate it (the gateway's
    # ADR-0011 policy intersection already happened);
    # X-Zuno-Gateway-Token is the one that's actually enforced (ADR-0037).
    endpoint = binding.endpoint_url()
    headers = {"Authorization": f"Bearer {bearer_token}", "X-Zuno-Gateway-Token": MCP_GATEWAY_WORKLOAD_TOKEN}
    # ADR-0603 M12 (WP-225 lot B): who the call is for, signed, from the validated
    # identity only (app/caller_context.py). A shared-credential server scopes its
    # technical identity with it (space, repository, owner allowlists; AAP launch
    # rate limit). A server that does not read it ignores it.
    headers.update(
        caller_context.build(
            sub=caller_sub,
            groups=caller_groups,
            claims=caller_claims,
            tool=binding.provider_tool or "",
            workload_token=MCP_GATEWAY_WORKLOAD_TOKEN,
        )
    )
    try:
        http_client = httpx2.AsyncClient(timeout=DOWNSTREAM_TIMEOUT_SECONDS, headers=headers)
        async with streamable_http_client(endpoint, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(binding.provider_tool, arguments)
    except MCPError as exc:
        logger.error(
            "%s MCP server returned a protocol-level error for tool '%s': %s",
            binding.backend, binding.provider_tool, exc,
        )
        raise DownstreamError(502, f"{binding.backend} MCP server returned an error: {exc}") from exc
    except (httpx.HTTPError, httpx2.HTTPError, OSError) as exc:
        logger.error(
            "%s MCP server call failed for tool '%s': %s", binding.backend, binding.provider_tool, exc
        )
        raise DownstreamError(502, f"{binding.backend} MCP server unreachable or errored: {exc}") from exc
    except ExceptionGroup as excgroup:
        # streamable_http_client opens its own anyio TaskGroup for the
        # duration of the `async with` block (read/write tasks) - a real
        # connection failure (e.g. the backend not being deployed, as with
        # salesforce-mcp/WP-101) surfaces as an httpx2.ConnectError raised
        # from INSIDE that TaskGroup, which anyio re-wraps in an
        # ExceptionGroup rather than letting it propagate directly, so it
        # never reached the except clause above (live-caught 2026-09-09:
        # this bug returns an unhandled 500 instead of the clean 502 every
        # other failure path here uses). split() only reclassifies it as
        # that same clean 502 if EVERY leaf is itself one of this
        # function's own connectivity-error types, so an unrelated bug
        # inside the SDK's own tasks is never silently masked as "backend
        # unreachable".
        connectivity, other = excgroup.split((httpx.HTTPError, httpx2.HTTPError, OSError))
        if other is not None:
            raise
        exc = connectivity.exceptions[0]
        logger.error(
            "%s MCP server call failed for tool '%s': %s", binding.backend, binding.provider_tool, exc
        )
        raise DownstreamError(502, f"{binding.backend} MCP server unreachable or errored: {exc}") from excgroup

    if result.is_error:
        detail = "; ".join(block.text for block in result.content if hasattr(block, "text"))
        raise DownstreamError(502, f"{binding.backend} MCP server returned a tool error: {detail}")

    if result.structured_content is not None:
        # Verified against the real SDK (mcp==2.0.0): a tool whose return
        # type annotation is a plain dict (every confluence tool) gets its
        # structured content wrapped as {"result": <value>} - MCP requires
        # structured content to have an object-typed top-level schema, and
        # a bare dict return has none, so the SDK wraps it. Unwrap that
        # single-key envelope rather than leaking SDK plumbing into the
        # gateway's own response shape, which callers expect to match the
        # pre-migration `{"customer": ..., "contacts": ...}` shape exactly.
        if set(result.structured_content.keys()) == {"result"}:
            return result.structured_content["result"]
        return result.structured_content
    text_blocks = [block.text for block in result.content if hasattr(block, "text")]
    return {"raw": "\n".join(text_blocks)}


# The schema a backend publishes for its own tools, advertised to the model on tools/list so that it knows
# the required arguments (a tool listed with an open schema made the model omit them: git-forge's
# list_repositories got 502 "Field required" for provider/owner/owner_type, WP-174 traces of 2026-11-03).
# The backend stays the only contract: nothing is restated here, it is read from the backend itself, cached,
# and any failure falls back to the open schema (listing must never fail or wait on a backend).
SCHEMA_TTL_SECONDS = float(os.getenv("DOWNSTREAM_SCHEMA_TTL_SECONDS", "300"))
SCHEMA_FAILURE_TTL_SECONDS = float(os.getenv("DOWNSTREAM_SCHEMA_FAILURE_TTL_SECONDS", "30"))
SCHEMA_TIMEOUT_SECONDS = float(os.getenv("DOWNSTREAM_SCHEMA_TIMEOUT_SECONDS", "3"))

# endpoint -> (expires_at, {backend tool name: {"inputSchema", "description"}})
_SCHEMA_CACHE: Dict[str, Tuple[float, Dict[str, Dict[str, Any]]]] = {}


def _tool_input_schema(tool: Any) -> Optional[Dict[str, Any]]:
    """The SDK names the field `input_schema` (mcp 2.x); `inputSchema` is the wire name."""
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
    return schema if isinstance(schema, dict) else None


async def _fetch_endpoint_schemas(endpoint: str) -> Dict[str, Dict[str, Any]]:
    headers = {"X-Zuno-Gateway-Token": MCP_GATEWAY_WORKLOAD_TOKEN}
    http_client = httpx2.AsyncClient(timeout=SCHEMA_TIMEOUT_SECONDS, headers=headers)
    async with streamable_http_client(endpoint, http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    return {
        tool.name: {"inputSchema": _tool_input_schema(tool), "description": getattr(tool, "description", None)}
        for tool in listed.tools
    }


async def _endpoint_schemas(endpoint: str) -> Dict[str, Dict[str, Any]]:
    cached = _SCHEMA_CACHE.get(endpoint)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        schemas = await asyncio.wait_for(_fetch_endpoint_schemas(endpoint), SCHEMA_TIMEOUT_SECONDS + 1)
        _SCHEMA_CACHE[endpoint] = (time.monotonic() + SCHEMA_TTL_SECONDS, schemas)
    except BaseException as exc:  # noqa: BLE001 - includes the SDK's ExceptionGroup; never break a listing
        if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
            raise
        logger.warning("could not read the tool schemas of %s: %s", endpoint, exc)
        schemas = {}
        _SCHEMA_CACHE[endpoint] = (time.monotonic() + SCHEMA_FAILURE_TTL_SECONDS, schemas)
    return schemas


async def schemas_for(bindings: List[Binding]) -> Dict[str, Dict[str, Any]]:
    """capability -> {"inputSchema", "description"} published by its streamable-http backend; capabilities
    whose backend cannot be read, or that are not backed by one, are absent (the caller keeps its default)."""
    wanted: Dict[str, List[Binding]] = {}
    for binding in bindings:
        if binding is None or binding.transport != "streamable-http" or not binding.provider_tool:
            continue
        try:
            wanted.setdefault(binding.endpoint_url(), []).append(binding)
        except ValueError:
            continue
    fetched = await asyncio.gather(*(_endpoint_schemas(endpoint) for endpoint in wanted))
    out: Dict[str, Dict[str, Any]] = {}
    for (endpoint, group), schemas in zip(wanted.items(), fetched):
        for binding in group:
            found = schemas.get(binding.provider_tool)
            if found:
                out[binding.capability] = found
    return out
