"""A2A gateway: serves each admitted zuno agent as an Agent2Agent endpoint (JSON-RPC, A2A 0.3).

    GET  /agents/<agent>/.well-known/agent-card.json   public card
    POST /agents/<agent>/                              message/send, message/stream, tasks/get, tasks/cancel

Every POST needs the caller's Keycloak token and an entitlement to the agent (ADR-0040). An agent
the caller may not use answers exactly like an unknown one (ADR-0583).
"""

from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable, Dict, Optional

import httpx
from a2a.auth.user import User
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.apps.jsonrpc.jsonrpc_app import CallContextBuilder
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app import auth
from app.agent_chain import DelegationLimits
from app.agent_declarations import AgentDeclarationStore
from app.cards import build_card
from app.clients import AiGatewayClient, McpGatewayClient
from app.config import Settings
from app.executor import ZunoAgentExecutor

logger = logging.getLogger("a2a_gateway")

_AGENT_PATH = re.compile(r"^/agents/([a-z][a-z0-9-]*)(/.*)?$")
_NOT_FOUND = {"error": "Agent not found"}


class _CallerUser(User):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def user_name(self) -> str:
        return self._name


class _ContextBuilder(CallContextBuilder):
    """Hands the authenticated caller (set by the middleware) and the request headers to the executor."""

    def build(self, request: Request) -> ServerCallContext:
        caller = request.scope.get("a2a_caller")
        return ServerCallContext(
            state={"caller": caller, "headers": dict(request.headers)},
            user=_CallerUser(caller.sub if caller else ""),
        )


def create_app(
    settings: Optional[Settings] = None,
    *,
    llm_transport: Optional[httpx.AsyncBaseTransport] = None,
    tools_transport: Optional[httpx.AsyncBaseTransport] = None,
    token_validator: Callable[[Optional[str]], auth.CallerIdentity] = auth.validate_token,
) -> FastAPI:
    settings = settings or Settings()
    store = AgentDeclarationStore(settings.agents_dir)
    limits = DelegationLimits(settings.limits_policy_path)
    llm = AiGatewayClient(settings.ai_gateway_url, settings.request_timeout_seconds, llm_transport)
    tools = McpGatewayClient(settings.mcp_gateway_url, settings.request_timeout_seconds, tools_transport)

    app = FastAPI(title="Zuno A2A gateway", docs_url=None, redoc_url=None, openapi_url=None)
    served: Dict[str, bool] = {}

    for name, agent in store._agents.items():  # noqa: SLF001 - same package family as the store
        if agent.status != "active" or not agent.access_groups:
            continue
        executor = ZunoAgentExecutor(agent, store, limits, settings, llm, tools)
        handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
        a2a_app = A2AFastAPIApplication(
            agent_card=build_card(agent, settings), http_handler=handler, context_builder=_ContextBuilder(),
        ).build()
        app.mount(f"/agents/{name}", a2a_app)
        served[name] = True

    @app.middleware("http")
    async def authenticate(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        match = _AGENT_PATH.match(request.url.path)
        if not match:
            if request.url.path.startswith("/agents/"):  # a name no agent can have: same answer as an unknown agent
                return JSONResponse(_NOT_FOUND, status_code=404)
            return await call_next(request)
        name = match.group(1)
        agent = store.get(name) if served.get(name) else None
        if agent is None:
            return JSONResponse(_NOT_FOUND, status_code=404)
        if request.method == "GET":  # the public card
            return await call_next(request)
        try:
            caller = token_validator(request.headers.get("authorization"))
        except auth.AuthError as exc:
            return JSONResponse({"error": str(exc)}, status_code=exc.status)
        if not set(agent.access_groups) & set(caller.groups):
            return JSONResponse(_NOT_FOUND, status_code=404)  # same answer as an unknown agent
        request.scope["a2a_caller"] = caller
        return await call_next(request)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        if not served:
            return JSONResponse({"status": "no active agent", "error": store.load_error}, status_code=503)
        return JSONResponse({"status": "ready", "agents": sorted(served)})

    @app.on_event("shutdown")
    async def close_clients() -> None:
        await llm.aclose()
        await tools.aclose()

    return app


def get_app() -> FastAPI:
    from app.telemetry import init_telemetry

    init_telemetry("a2a-gateway")
    return create_app()
