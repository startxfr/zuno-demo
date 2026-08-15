"""Zuno MCP Gateway (ADR-0010, ADR-0011).

Central entry point for every MCP tool call in the platform: validates the
caller's Keycloak JWT, computes the policy-intersection authorization
decision, and proxies to the right downstream MCP server or demo-mode
handler. See README.md for the exact HTTP API contract.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.agent_declarations import AgentDeclarationStore
from app.auth import CallerIdentity, validate_token
from app.bindings import BindingRegistry
from app.delegation import get_delegated_token
from app.downstream import DownstreamError
from app.downstream import invoke as invoke_downstream
from app.policy import PolicyDecision, PolicyStore, evaluate
from app.telemetry import init_telemetry, tool_invoke_span

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mcp_gateway")

init_telemetry("mcp-gateway")  # ADR-0029: traces/metrics to the shared OTel Collector

app = FastAPI(
    title="Zuno MCP Gateway",
    version="0.1.0",
    description=(
        "Central MCP Gateway (ADR-0010): authorizes and proxies every MCP "
        "tool call behind a single ADR-0011 policy-intersection decision."
    ),
)

policy_store = PolicyStore()
agent_declarations = AgentDeclarationStore()  # ADR-0036/0038: agents/<name>/agent.okf.md bundles
binding_registry = BindingRegistry()  # ADR-0116: capability -> physical backend


def _binding_coverage_error() -> Optional[str]:
    """ADR-0116 startup/health validation: every name the policy answers to
    (legacy tool + canonical capability) must resolve to exactly one active
    binding. Logged loudly at startup and re-checked on reload; surfaced via
    /readyz so a gap fails readiness rather than silently failing calls."""
    if not policy_store.loaded or not binding_registry.loaded:
        return None  # the underlying load errors are already reported
    problems = binding_registry.validate_policy_coverage(policy_store.policy_names())
    if problems:
        msg = "; ".join(problems)
        logger.error("binding coverage validation failed (ADR-0116): %s", msg)
        return msg
    return None


binding_coverage_error = _binding_coverage_error()


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    if (
        policy_store.loaded
        and agent_declarations.loaded
        and binding_registry.loaded
        and not binding_coverage_error
    ):
        return JSONResponse({"status": "ready"})
    reasons = [
        r
        for r in (
            policy_store.load_error,
            agent_declarations.load_error,
            binding_registry.load_error,
            binding_coverage_error,
        )
        if r
    ]
    return JSONResponse(
        {"status": "not-ready", "reason": "; ".join(reasons) or "policy not loaded"},
        status_code=503,
    )


@app.post("/admin/reload-policy")
async def reload_policy() -> Dict[str, Any]:
    """Operational escape hatch: re-reads tool-policy.yaml,
    classification.yaml, the agents/ OKF bundles and the ADR-0116 tool
    bindings from disk without a pod restart, for the case where Track B's
    policy files, an agent definition or a binding change land after this
    pod already started.
    """
    global binding_coverage_error
    policy_store.reload()
    agent_declarations.reload()
    binding_registry.reload()
    binding_coverage_error = _binding_coverage_error()
    return {
        "loaded": (
            policy_store.loaded
            and agent_declarations.loaded
            and binding_registry.loaded
            and not binding_coverage_error
        ),
        "error": (
            policy_store.load_error
            or agent_declarations.load_error
            or binding_registry.load_error
            or binding_coverage_error
        ),
        "tools": policy_store.known_tools(),
        "capabilities": binding_registry.capabilities(),
    }


def _self_scope_denial_reason(
    decision: PolicyDecision, arguments: Dict[str, Any], caller_sub: str
) -> Optional[str]:
    """ADR-0340 (WP-32): *.self.* ownership check, server-side from the
    validated JWT subject - never from prompt-influenced request content.
    Returns a denial detail string when `decision.subject_field` is set
    and the matching request argument doesn't equal the caller's own
    subject; None (no denial) when the capability has no self/any
    distinction (subject_field unset) or the argument matches. A pure
    function so it's directly unit-testable without an HTTP round trip or
    a real agent bundle declaring a workday.* capability (none does yet -
    see tests/test_workday_ownership.py).
    """
    if not decision.subject_field:
        return None
    if arguments.get(decision.subject_field) != caller_sub:
        return (
            f"self-scoped: argument '{decision.subject_field}' must equal the caller's own subject"
        )
    return None


@app.post("/v1/tools/{tool_name}/invoke")
async def invoke_tool(
    tool_name: str,
    request: Request,
    identity: CallerIdentity = Depends(validate_token),
    x_zuno_data_classification: str = Header(default="C1", alias="X-Zuno-Data-Classification"),
    x_zuno_agent: str = Header(default="", alias="X-Zuno-Agent"),
    x_zuno_task: str = Header(default="", alias="X-Zuno-Task"),
) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    classification = x_zuno_data_classification.upper()

    with tool_invoke_span(tool_name, classification) as call:
        # ADR-0116: the binding registry is the single source of known tool
        # names (canonical capability IDs + migration aliases) - an unknown
        # name fails closed here, before any policy or backend work.
        binding = binding_registry.resolve(tool_name)
        if binding is None:
            call.outcome = "unknown_tool"
            raise HTTPException(status_code=404, detail=f"unknown tool '{tool_name}'")
        call.capability = binding.capability
        call.binding = binding.backend

        raw_body = await request.body()
        if raw_body:
            try:
                arguments = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                call.outcome = "bad_request"
                raise HTTPException(status_code=400, detail=f"request body is not valid JSON: {exc}") from exc
        else:
            arguments = {}
        if not isinstance(arguments, dict):
            call.outcome = "bad_request"
            raise HTTPException(status_code=400, detail="request body must be a JSON object of tool arguments")

        decision = evaluate(
            store=policy_store,
            agents=agent_declarations,
            tool_name=tool_name,
            agent_name=x_zuno_agent,
            task_name=x_zuno_task,
            caller_groups=identity.groups,
            request_classification=classification,
            equivalent_names=binding.all_names(),
        )
        call.mcp_server = decision.mcp_server
        call.reason = decision.reason

        logger.info(
            "tool=%s capability=%s binding=%s auth_mode=%s agent=%s task=%s caller=%s groups=%s "
            "classification=%s allowed=%s reason=%s request_id=%s",
            tool_name,
            binding.capability,
            binding.backend,
            binding.auth_mode,
            x_zuno_agent,
            x_zuno_task,
            identity.sub,
            identity.groups,
            x_zuno_data_classification,
            decision.allowed,
            decision.reason,
            request_id,
        )

        if not decision.allowed:
            call.outcome = "denied"
            raise HTTPException(status_code=403, detail=decision.reason)

        # ADR-0340 (WP-32): *.self.* ownership check - runs after the
        # group-level decision above already allowed the call, before any
        # backend is contacted. See _self_scope_denial_reason's own
        # docstring for why this is a separate, directly-unit-testable
        # function rather than inlined here.
        self_scope_denial = _self_scope_denial_reason(decision, arguments, identity.sub)
        if self_scope_denial:
            call.outcome = "denied"
            raise HTTPException(status_code=403, detail=f"'{tool_name}' is {self_scope_denial}")

        # ADR-0208 (WP-26): the credential flow used must match the
        # binding's declared auth_mode - checked here, after the policy
        # decision (so a subject-specific "no" from evaluate() above is
        # still the first word) and before any backend is contacted.
        call.auth_mode = binding.auth_mode
        delegated_token: Optional[str] = None
        if binding.auth_mode == "delegated-user":
            # Never falls back to the gateway's own service identity: a
            # missing delegated credential (including a revoked Google
            # permission - app/delegation.py's own docstring) is a
            # deterministic denial, identical in shape to a policy denial.
            delegated_token = get_delegated_token(binding.backend, identity.sub)
            if not delegated_token:
                call.outcome = "delegated_credential_missing"
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"'{binding.capability}' requires a delegated {binding.backend} "
                        "credential for this user, and none is available"
                    ),
                )
        elif binding.auth_mode == "provider-delegated":
            # Schema-only today (ADR-0208 Out of scope / deferred) - no
            # provider that supports on-behalf-of delegation is bound yet.
            call.outcome = "auth_mode_not_implemented"
            raise HTTPException(
                status_code=501,
                detail=f"'{binding.capability}' declares auth_mode=provider-delegated, which has no implementation yet",
            )
        # service-identity: the policy decision just above already
        # evaluated the specific calling subject before any shared
        # credential is used - no further gate needed here.

        try:
            result = await invoke_downstream(
                binding, tool_name, arguments, identity.sub, identity.token, delegated_token=delegated_token
            )
        except DownstreamError as exc:
            call.outcome = "downstream_error"
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

        call.outcome = "allowed"
        duration_ms = (time.monotonic() - started) * 1000
        return {
            "tool": tool_name,
            # ADR-0116: both the logical capability and the resolved
            # physical binding are reported (and traced) - callers keep the
            # logical view, operators see the actual backend.
            "capability": binding.capability,
            "binding": binding.backend,
            "request_id": request_id,
            "mcp_server": decision.mcp_server,
            "duration_ms": round(duration_ms, 1),
            # ADR-0035: tells the caller (Agent Runtime) whether this
            # result may be processed by an external SaaS model or must
            # stay local, independent of the classification the caller
            # itself declared - the Agent Runtime uses this to set
            # X-Zuno-Local-Only on its own downstream model call.
            "external_model_policy": {"allow_context": decision.allow_external_context},
            "result": result,
        }
