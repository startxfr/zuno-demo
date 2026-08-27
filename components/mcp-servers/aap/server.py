"""aap MCP server (ADR-0355): Ansible Automation Platform audits.

Scaffolded by platform/scaffolding/new_mcp_server.py (ADR-0119) from the
components/mcp-servers/confluence template: a real, standards-compliant
MCP server (the `mcp` SDK's `MCPServer`, streamable-HTTP transport,
mounted at /mcp), gateway-token-authenticated (ADR-0037).

Two capabilities, deliberately narrow (ADR-0355 clause 2):

    aap.platform.audit -> platform_audit()  - read-only. No POST, ever.
    aap.cluster.audit  -> cluster_audit()   - launches ONE Job Template.

`cluster_audit` is this repository's first agent-reachable capability that
runs automation rather than reading state. It therefore takes NO arguments:
the template is resolved by the module-level `JOB_TEMPLATE_NAME` constant,
so no caller - agent, gateway, or prompt-injected instruction - can point
it at a different Job Template. That is the server-construction half of
ADR-0355's defence in depth; the other halves are the AAP-side token (an
object-scoped `awx.execute_jobtemplate` grant on this template alone) and
the agent OKF declaration (only Tekos declares this capability).

Authentication mode: `service-identity` (ADR-0208) - one technical
credential (AAP_API_TOKEN + AAP_BASE_URL), sourced from an `ExternalSecret`
resolving `zuno/aap/mcp-token` (never hardcoded, ADR-0024). That path holds
a token belonging to the least-privilege `zuno-mcp` AAP user minted by
ansible/roles/aap_config - never `zuno/aap/admin`, and never WP-073's
unscoped `zuno/aap/controller-token`.

    POST /mcp    - real MCP streamable-HTTP transport (initialize,
                   tools/list, tools/call)
    GET /healthz -> 200 once AAP_API_TOKEN is configured. Deliberately
                   does NOT call the Controller on every probe: ADR-0355's
                   Operational considerations require a Controller outage
                   to degrade these two tools only, never this pod's own
                   liveness (ADR-0037's pattern).
"""
from __future__ import annotations

import asyncio
import hmac
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

AAP_API_TOKEN = os.getenv("AAP_API_TOKEN", "")

# The AAP *Gateway* service, not aap-controller-service. On AAP 2.5+ the
# controller service has no token auth of its own and answers 401 to a
# gateway-minted token (proven live in WP-073, see
# gitops/charts/aap-config/values.yaml). Everything under
# /api/controller/v2/... must be reached *through* the gateway.
AAP_BASE_URL = os.getenv("AAP_BASE_URL", "http://aap.zuno-aap.svc")

HTTP_TIMEOUT_SECONDS = float(os.getenv("AAP_HTTP_TIMEOUT_SECONDS", "20"))

# Upper bound on cluster_audit's poll loop. day0_check.yml takes a few
# minutes; the bound exists so a wedged job surfaces as an explicit,
# job-id-carrying error rather than hanging the calling agent's turn.
JOB_TIMEOUT_SECONDS = float(os.getenv("AAP_JOB_TIMEOUT_SECONDS", "600"))
JOB_POLL_SECONDS = float(os.getenv("AAP_JOB_POLL_SECONDS", "5"))

# ADR-0355 clause 2 authorizes launching this template and no other. Not a
# tool argument - see the module docstring.
JOB_TEMPLATE_NAME = os.getenv("AAP_JOB_TEMPLATE_NAME", "zuno-day0-check")
PROJECT_NAME = os.getenv("AAP_PROJECT_NAME", "zuno-demo")

# ADR-0037: required, not optional - this server has no purpose other than
# serving the gateway (same reasoning as confluence/server.py).
GATEWAY_WORKLOAD_TOKEN = os.getenv("MCP_GATEWAY_WORKLOAD_TOKEN", "")

_TERMINAL_JOB_STATUSES = frozenset({"successful", "failed", "error", "canceled"})


class AapConfigError(RuntimeError):
    """A required credential/configuration value is missing on this pod."""


def _require_config() -> None:
    if not AAP_API_TOKEN:
        raise AapConfigError(
            "AAP_API_TOKEN is required (sourced from an ExternalSecret "
            "against secret/zuno/aap/mcp-token - never hardcoded, ADR-0024)"
        )
    if not AAP_BASE_URL:
        raise AapConfigError(
            "AAP_BASE_URL is required (the AAP Gateway service, e.g. "
            "http://aap.zuno-aap.svc - never aap-controller-service)"
        )


def _client() -> httpx.AsyncClient:
    """A fresh client per call - no module-level client, same shape as the
    other servers in components/mcp-servers/."""
    _require_config()
    return httpx.AsyncClient(
        base_url=AAP_BASE_URL.rstrip("/"),
        timeout=HTTP_TIMEOUT_SECONDS,
        headers={
            "Authorization": f"Bearer {AAP_API_TOKEN}",
            "Content-Type": "application/json",
        },
        follow_redirects=True,
    )


async def _request(client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> Any:
    """One place mapping every backend failure onto a clear tool error.

    ADR-0355's Operational considerations: a Controller outage or an expired
    token must reach the calling agent as an actionable message, never as a
    silent timeout or an opaque stack trace.
    """
    try:
        response = await client.request(method, path, **kwargs)
    except httpx.TimeoutException as exc:
        raise ValueError(
            f"AAP Controller did not answer within {HTTP_TIMEOUT_SECONDS}s "
            f"({method} {path}) - the platform may be degraded: {exc}"
        ) from exc
    except httpx.RequestError as exc:
        raise ValueError(
            f"AAP Controller is unreachable at {AAP_BASE_URL} "
            f"({method} {path}) - check the zuno-aap NetworkPolicy and that "
            f"the aap component is running: {exc}"
        ) from exc

    if response.status_code in (401, 403):
        raise ValueError(
            f"AAP rejected this server's token ({response.status_code} on "
            f"{method} {path}) - it has expired, been revoked, or lacks the "
            f"required grant. Re-run `make d1 install aap-config` to re-mint "
            f"secret/zuno/aap/mcp-token."
        )
    if response.status_code == 404:
        raise ValueError(f"no such AAP resource: {method} {path}")
    if response.status_code >= 400:
        raise ValueError(
            f"AAP returned {response.status_code} on {method} {path}: "
            f"{response.text[:500]}"
        )

    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        raise ValueError(
            f"AAP returned a non-JSON body on {method} {path} "
            f"(is AAP_BASE_URL pointing at the Gateway?): {response.text[:200]}"
        ) from exc


async def _lookup_by_name(client: httpx.AsyncClient, collection: str, name: str) -> Dict[str, Any]:
    """Resolve a named Controller object to its record. Names, never
    hardcoded ids - the ids differ per cluster and per reinstall."""
    payload = await _request(
        client, "GET", f"/api/controller/v2/{collection}/", params={"name": name}
    )
    results = payload.get("results") or []
    if not results:
        raise ValueError(
            f"no {collection[:-1]} named '{name}' in AAP - is aap-config "
            f"installed and its Project synced?"
        )
    return results[0]


def _summarize_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": job.get("id"),
        "status": job.get("status"),
        "failed": job.get("failed"),
        "started": job.get("started"),
        "finished": job.get("finished"),
        "elapsed_seconds": job.get("elapsed"),
    }


mcp_server = MCPServer(
    name="aap",
    version="0.1.0",
    instructions=(
        "Ansible Automation Platform (AAP) audits for this OpenShift cluster. "
        "Use platform_audit to report how the automation platform itself is "
        "doing - component health, whether its Git project is in sync, and how "
        "recent runs went. Use cluster_audit to actually run the cluster's "
        f"'{JOB_TEMPLATE_NAME}' health check and report the outcome; it takes "
        "no arguments, runs real automation, and can take several minutes, so "
        "call it only when the user asks for a fresh cluster check rather than "
        "a status summary."
    ),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The mounted MCP sub-app's session manager needs the parent app's
    # lifespan to run its task group (same requirement as every other
    # server in components/mcp-servers/).
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="aap MCP server", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    # Config-only, no backend call - see the module docstring.
    _require_config()
    return {"status": "ok"}


@mcp_server.tool()
async def platform_audit(recent_jobs: int = 5) -> Dict[str, Any]:
    """Summarize the Ansible Automation Platform's own state: component/instance
    health, the zuno-demo Project's last Git sync, and recent runs of the
    cluster health-check Job Template. Read-only - changes nothing.

    Args:
        recent_jobs: how many recent Job Template runs to include (1-25).
    """
    if not isinstance(recent_jobs, int) or not 1 <= recent_jobs <= 25:
        raise ValueError("recent_jobs must be an integer between 1 and 25")

    async with _client() as client:
        ping = await _request(client, "GET", "/api/controller/v2/ping/")

        instances: List[Dict[str, Any]] = [
            {
                "node": instance.get("node"),
                "type": instance.get("node_type"),
                "heartbeat": instance.get("heartbeat"),
                "capacity": instance.get("capacity"),
            }
            for instance in ping.get("instances") or []
        ]

        project = await _lookup_by_name(client, "projects", PROJECT_NAME)
        template = await _lookup_by_name(client, "job_templates", JOB_TEMPLATE_NAME)

        history = await _request(
            client,
            "GET",
            f"/api/controller/v2/job_templates/{template['id']}/jobs/",
            params={"order_by": "-id", "page_size": recent_jobs},
        )

    return {
        "controller": {
            "version": ping.get("version"),
            "ha": ping.get("ha"),
            "active_node": ping.get("active_node"),
            "instances": instances,
        },
        "project": {
            "name": project.get("name"),
            "status": project.get("status"),
            "scm_branch": project.get("scm_branch"),
            "scm_revision": project.get("scm_revision"),
            "last_job_run": project.get("last_job_run"),
            "last_update_failed": project.get("last_update_failed"),
        },
        "job_template": {
            "name": template.get("name"),
            "playbook": template.get("playbook"),
            "status": template.get("status"),
            "last_job_run": template.get("last_job_run"),
        },
        "recent_runs": [_summarize_job(job) for job in history.get("results") or []],
    }


@mcp_server.tool()
async def cluster_audit() -> Dict[str, Any]:
    """Run this cluster's Day 0 health check through Ansible Automation
    Platform and report the result. Takes no arguments and always runs the
    same read-mostly check playbook. This launches real automation and
    typically takes a few minutes.
    """
    started_at = time.monotonic()

    async with _client() as client:
        template = await _lookup_by_name(client, "job_templates", JOB_TEMPLATE_NAME)

        # Bare launch, no payload: the template sets
        # ask_variables_on_launch/ask_inventory_on_launch false (WP-073), so
        # extra_vars would be rejected - and passing any would reopen exactly
        # the injection surface ADR-0355's Security considerations closes.
        launched = await _request(
            client, "POST", f"/api/controller/v2/job_templates/{template['id']}/launch/"
        )
        job_id = launched.get("id") or launched.get("job")
        if not job_id:
            raise ValueError(
                f"AAP accepted the launch of '{JOB_TEMPLATE_NAME}' but returned "
                f"no job id: {launched}"
            )

        job: Dict[str, Any] = {}
        while True:
            job = await _request(client, "GET", f"/api/controller/v2/jobs/{job_id}/")
            if job.get("status") in _TERMINAL_JOB_STATUSES:
                break
            if time.monotonic() - started_at > JOB_TIMEOUT_SECONDS:
                # Explicit, job-id-carrying error - never a silent timeout
                # (ADR-0355 Operational considerations).
                raise ValueError(
                    f"AAP job {job_id} ('{JOB_TEMPLATE_NAME}') was still "
                    f"'{job.get('status')}' after {JOB_TIMEOUT_SECONDS:.0f}s and "
                    f"was left running - inspect it in the Controller UI "
                    f"(job {job_id}) rather than relaunching."
                )
            await asyncio.sleep(JOB_POLL_SECONDS)

        summaries = await _request(
            client,
            "GET",
            f"/api/controller/v2/jobs/{job_id}/job_host_summaries/",
            params={"page_size": 25},
        )

    hosts = [
        {
            "host": row.get("host_name"),
            "ok": row.get("ok"),
            "changed": row.get("changed"),
            "failures": row.get("failures"),
            "skipped": row.get("skipped"),
            "unreachable": row.get("dark"),
        }
        for row in summaries.get("results") or []
    ]

    status = job.get("status")
    return {
        "job_template": JOB_TEMPLATE_NAME,
        "passed": status == "successful",
        "job": _summarize_job(job),
        "hosts": hosts,
        "failure_reason": job.get("job_explanation") or job.get("result_traceback") or None,
    }


class GatewayTokenMiddleware(BaseHTTPMiddleware):
    """ADR-0037 workload-identity check, ahead of any MCP protocol handling
    (identical pattern to every other server in components/mcp-servers/)."""

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
            "aap-mcp.zuno-ai-run.svc:8000,aap-mcp.zuno-ai-run.svc.cluster.local:8000,aap-mcp:8000,localhost:8000,127.0.0.1:8000",
        ).split(","),
    ),
)
mcp_asgi_app.add_middleware(GatewayTokenMiddleware)
app.mount("/", mcp_asgi_app)
