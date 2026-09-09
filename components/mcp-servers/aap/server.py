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

import hmac
import os
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

# The Gateway's public Route (e.g. https://aap.apps.demo333.startx.fr) -
# deliberately a SEPARATE value from AAP_BASE_URL above, never the same
# one: AAP_BASE_URL is the in-cluster Service this pod's own API calls use
# and is meaningless in a browser. Empty by default (no link surfaced)
# rather than guessing a hostname - a wrong link is worse than no link.
AAP_CONTROLLER_UI_URL = os.getenv("AAP_CONTROLLER_UI_URL", "")

HTTP_TIMEOUT_SECONDS = float(os.getenv("AAP_HTTP_TIMEOUT_SECONDS", "20"))

# ADR-0355 clause 2 authorizes launching this template and no other. Not a
# tool argument - see the module docstring.
JOB_TEMPLATE_NAME = os.getenv("AAP_JOB_TEMPLATE_NAME", "zuno-day0-check")
PROJECT_NAME = os.getenv("AAP_PROJECT_NAME", "zuno-demo")

# ADR-0037: required, not optional - this server has no purpose other than
# serving the gateway (same reasoning as confluence/server.py).
GATEWAY_WORKLOAD_TOKEN = os.getenv("MCP_GATEWAY_WORKLOAD_TOKEN", "")


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


def _job_url(job_id: Any) -> Optional[str]:
    """Human-facing link to this job's output page in the AAP Controller
    UI - None when AAP_CONTROLLER_UI_URL isn't configured, so callers must
    treat it as optional. The `#/jobs/playbook/<id>/output` shape mirrors
    the `#/jobs/project/<id>` link ansible/roles/aap_config/tasks/
    install.yml already uses for a project update; `playbook` is the UI's
    sibling route for a Job Template run (job type `job`, not
    `project_update`)."""
    if not AAP_CONTROLLER_UI_URL:
        return None
    return f"{AAP_CONTROLLER_UI_URL.rstrip('/')}/#/jobs/playbook/{job_id}/output"


def _summarize_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": job.get("id"),
        "status": job.get("status"),
        "failed": job.get("failed"),
        "started": job.get("started"),
        "finished": job.get("finished"),
        "elapsed_seconds": job.get("elapsed"),
        "url": _job_url(job.get("id")),
    }


async def _job_log_tail(client: httpx.AsyncClient, job_id: Any, lines: int = 5) -> List[str]:
    """The last few lines of this job's output, via job_events (paginated,
    ordered by -counter) rather than the full stdout blob (`/jobs/<id>/
    stdout/?format=txt`, used elsewhere in this repo e.g. ansible/
    playbooks/aap_launch.yml) - cheap even for a long or noisy playbook.
    Not every event carries stdout (play/task start markers are often
    blank), so this over-fetches one page and keeps only the most recent
    `lines` non-empty ones, restored to chronological order for display.
    """
    events = await _request(
        client,
        "GET",
        f"/api/controller/v2/jobs/{job_id}/job_events/",
        params={"order_by": "-counter", "page_size": max(lines * 5, 25)},
    )
    non_empty = [
        row["stdout"].rstrip("\n")
        for row in (events.get("results") or [])
        if row.get("stdout")
    ]
    return list(reversed(non_empty[:lines]))


mcp_server = MCPServer(
    name="aap",
    version="0.1.0",
    instructions=(
        "Ansible Automation Platform (AAP) audits for this OpenShift cluster. "
        "Use platform_audit to report how the automation platform itself is "
        "doing - component health, whether its Git project is in sync, and how "
        "recent runs went (this also shows the outcome of any cluster_audit run, "
        "once it has finished). Use cluster_audit to launch the cluster's "
        f"'{JOB_TEMPLATE_NAME}' health check; it takes no arguments, runs real "
        "automation, and returns immediately with a job id rather than waiting - "
        "the run itself takes a few minutes. Call it only when the user asks for "
        "a fresh cluster check rather than a status summary, and call "
        "platform_audit afterwards (on the user's next relevant question) to "
        "report whether it passed. Both tools return a `url` link to the run "
        "in the AAP Controller UI and (for the most recent run) a `log_tail` "
        "of its last output lines - always surface the url, and the log_tail "
        "when the run failed."
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

    Every job in the response includes a `url` field - a link to that run
    in the AAP Controller UI - and the most recent run also carries a
    `log_tail` field with its last few output lines. Include both when
    reporting a run's outcome to the user, not just its pass/fail status.

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

        recent_runs = [_summarize_job(job) for job in history.get("results") or []]
        # Only the most recent run gets its log fetched - one extra call,
        # not `recent_jobs` of them. This is what answers "how did my last
        # cluster_audit go", the common follow-up after launching one.
        if recent_runs:
            recent_runs[0]["log_tail"] = await _job_log_tail(client, recent_runs[0]["id"])

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
        "recent_runs": recent_runs,
    }


@mcp_server.tool()
async def cluster_audit() -> Dict[str, Any]:
    """Launch this cluster's Day 0 health check through Ansible Automation
    Platform and return immediately with the job id - it does NOT wait for
    the run to finish (the underlying playbook takes a few minutes). Takes
    no arguments and always launches the same read-mostly check playbook.
    Call platform_audit afterwards to see whether the run passed.

    The response's `job` includes a `url` field - a link to this run in the
    AAP Controller UI - and a `log_tail` field with its output so far (likely
    empty this soon after launch). Include the url when telling the user
    the job was launched.
    """
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

        # ADR-0524 (2026-09-09, live-caught): this used to poll here until the
        # job reached a terminal status (up to 10 minutes) before returning.
        # OpenShift Lightspeed's console plugin has its own client-side
        # request timeout well under that - the job kept running and
        # completing correctly, but the console always showed "network
        # error" first. One immediate status read (never a wait loop) keeps
        # this call fast for every caller, not just Lightspeed.
        job = await _request(client, "GET", f"/api/controller/v2/jobs/{job_id}/")
        summary = _summarize_job(job)
        summary["log_tail"] = await _job_log_tail(client, job_id)

    return {
        "job_template": JOB_TEMPLATE_NAME,
        "launched": True,
        "job": summary,
        "message": (
            f"Launched '{JOB_TEMPLATE_NAME}' as AAP job {job_id} (status: "
            f"{job.get('status')}). It typically takes a few minutes to finish - "
            "ask for a platform audit afterwards to see whether it passed. "
            + (f"Job link: {summary['url']}" if summary["url"] else f"Job id: {job_id}.")
        ),
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
