"""aap MCP server (ADR-0355): Ansible Automation Platform audits.

Scaffolded by platform/scaffolding/new_mcp_server.py (ADR-0119) from the
components/mcp-servers/confluence template: a real, standards-compliant
MCP server (the `mcp` SDK's `MCPServer`, streamable-HTTP transport,
mounted at /mcp), call-assertion-authenticated (ADR-0037, WP-250).

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

import base64
import collections
import hashlib
import hmac
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Deque, Dict, List, Mapping, Optional

import httpx
from fastapi import FastAPI
from mcp.server.mcpserver import Context, MCPServer
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
CALLER_CONTEXT_AUDIENCE = "aap"


def _verified_caller(headers: Optional[Mapping[str, str]], tool: str) -> Optional[Dict[str, Any]]:
    # WP-250: the caller is read from the verified call assertion only (`ctx`, see the
    # call-assertion verifier block). No shared secret is involved any more.
    return _assertion_caller(headers, tool)


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
# ADR-0603 M15 (WP-225 lot B): a per-caller limit on cluster_audit launches.
#
# At most AAP_CLUSTER_AUDIT_RATE_LIMIT launches per caller in any
# AAP_CLUSTER_AUDIT_RATE_WINDOW_SECONDS (chart values clusterAudit.rateLimit.*),
# 0 meaning no limit. The caller is the `sub` of the signed caller context.
#
# The unverified bucket, deliberately: every call WITHOUT a verified context (an
# mcp-gateway that does not send one yet, a forged or stale header) counts against
# ONE shared bucket, UNVERIFIED_CALLER, so changing a header never buys a fresh
# allowance. Consequence: until the mcp-gateway that signs the context is rolled,
# every caller shares that one bucket (2 launches per 15 minutes for the whole
# platform by default). Roll the mcp-gateway first, then this server.
#
# The count lives in this pod (replicas: 1); a restart resets it. A launch whose
# POST AAP refused (or that never reached AAP) does not count; once the POST has
# succeeded the launch counts, whatever happens after it. Buckets whose stamps
# have all expired are dropped, so the map holds only callers of the last window.
# --------------------------------------------------------------------------

UNVERIFIED_CALLER = "<unverified>"
_launches: Dict[str, Deque[float]] = {}


def _rate_limit() -> int:
    try:
        return max(0, int(os.getenv("AAP_CLUSTER_AUDIT_RATE_LIMIT", "2")))
    except ValueError:
        return 2


def _rate_window_seconds() -> float:
    try:
        return max(1.0, float(os.getenv("AAP_CLUSTER_AUDIT_RATE_WINDOW_SECONDS", "900")))
    except ValueError:
        return 900.0


class RateLimited(PermissionError):
    pass


def _reserve_launch(caller_key: str, now: Optional[float] = None) -> Optional[float]:
    """Counts one launch for `caller_key` and returns its timestamp, or raises
    RateLimited (with the wait in seconds) when the caller is at the limit."""
    limit = _rate_limit()
    if not limit:
        return None
    now = time.monotonic() if now is None else now
    window = _rate_window_seconds()
    for key in list(_launches):
        bucket = _launches[key]
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        if not bucket:
            del _launches[key]
    stamps = _launches.setdefault(caller_key, collections.deque())
    if len(stamps) >= limit:
        retry_after = int(window - (now - stamps[0])) + 1
        raise RateLimited(
            f"cluster_audit is rate limited: {limit} launch(es) per {int(window)}s per caller "
            f"(ADR-0603 M15); retry in {retry_after}s, or call platform_audit for the last run"
        )
    stamps.append(now)
    return now


def _release_launch(caller_key: str, stamp: Optional[float]) -> None:
    if stamp is None:
        return
    bucket = _launches.get(caller_key)
    if bucket is None:
        return
    try:
        bucket.remove(stamp)
    except ValueError:
        pass
    if not bucket:
        del _launches[caller_key]


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
async def cluster_audit(ctx: Optional[Context] = None) -> Dict[str, Any]:
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
    caller = _caller(ctx, "cluster_audit")
    caller_key = (caller or {}).get("sub") or UNVERIFIED_CALLER
    stamp = _reserve_launch(caller_key)
    progress = {"posted": False}
    try:
        return await _launch_cluster_audit(progress)
    except Exception:
        # Only a launch AAP never accepted gives its slot back: after a successful
        # POST the job exists, so a failing follow-up read still counts.
        if not progress["posted"]:
            _release_launch(caller_key, stamp)
        raise


async def _launch_cluster_audit(progress: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    progress = progress if progress is not None else {}
    async with _client() as client:
        template = await _lookup_by_name(client, "job_templates", JOB_TEMPLATE_NAME)

        # Bare launch, no payload: the template sets
        # ask_variables_on_launch/ask_inventory_on_launch false (WP-073), so
        # extra_vars would be rejected - and passing any would reopen exactly
        # the injection surface ADR-0355's Security considerations closes.
        launched = await _request(
            client, "POST", f"/api/controller/v2/job_templates/{template['id']}/launch/"
        )
        progress["posted"] = True
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


# --------------------------------------------------------------------------
# BEGIN call-assertion verifier (WP-225 lot C)
#
# ADR-0602 clause 10 / ADR-0603 M14: the per-call assertion. With
# MCP_OUTBOUND_IDENTITY=assertion the gateway sends, instead of the caller's
# bearer, a JWT it signs with a key only it holds (EdDSA, typ zuno-call+jwt; see
# components/mcp-gateway/app/call_assertion.py): iss mcp-gateway, aud this
# server's backend name, sub the caller, act the gateway, tool the backend tool
# name, exp at most 60 s after iat, jti. This server holds the public key
# (MCP_CALL_ASSERTION_PUBLIC_KEY, PEM) and verifies it here, before any MCP
# handling. A forged, expired, too long-lived or misaddressed assertion is
# refused (401). A tools/call whose name is not the assertion's tool, whose
# arguments do not match its `args` hash, or whose jti was already consumed, is
# refused (403); a body that is not JSON 400, one past the size cap 413. With
# A request without a valid assertion is always refused (WP-250 lot 2: the env switch
# MCP_CALL_ASSERTION_REQUIRED is no longer read).
# WP-250: the assertion may carry `ctx` (groups, email, email_verified, username), the
# caller context signed with the assertion. After verification the middleware hands it to
# the tool code as the header X-Zuno-Assertion-Caller; any such header sent by a client
# is removed first, so only a verified assertion can set it (`_assertion_caller`).
# This block is byte-identical in confluence, git-forge, salesforce and aap
# (each image is built from its own directory, ADR-0119); the lot C tests
# compare the copies.
# --------------------------------------------------------------------------

import logging as _assertion_logging  # noqa: E402 - part of the self-contained block

import jwt as _assertion_jwt  # noqa: E402
from cryptography.hazmat.primitives import serialization as _assertion_serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey as _AssertionPublicKey  # noqa: E402

_ASSERTION_LOG = _assertion_logging.getLogger("zuno.call_assertion")
CALL_ASSERTION_TYPE = "zuno-call+jwt"
CALL_ASSERTION_ISSUER = "mcp-gateway"
CALL_ASSERTION_MAX_TTL_SECONDS = 60
CALL_ASSERTION_LEEWAY_SECONDS = 5
# The largest request body read to check a tools/call (git.file.write carries a whole
# file): MCP_CALL_ASSERTION_MAX_BODY_BYTES, chart callAssertion.maxBodyBytes. A larger
# body is refused with 413.
CALL_ASSERTION_DEFAULT_MAX_BODY_BYTES = 16 * 1024 * 1024
_CALL_ASSERTION_KEYS: Dict[str, Any] = {}
_CALL_ASSERTION_SEEN: Dict[str, float] = {}


class CallAssertionError(ValueError):
    """The assertion is not acceptable; the message is safe to return."""


def _call_assertion_required() -> bool:
    # WP-250 lot 2: always. The assertion is the only way in (the shared workload token is
    # gone); without a configured public key every request is refused (fail closed).
    return True


def _call_assertion_max_body_bytes() -> int:
    raw = os.getenv("MCP_CALL_ASSERTION_MAX_BODY_BYTES", "").strip()
    try:
        value = int(raw) if raw else CALL_ASSERTION_DEFAULT_MAX_BODY_BYTES
    except ValueError:
        value = CALL_ASSERTION_DEFAULT_MAX_BODY_BYTES
    return value if value > 0 else CALL_ASSERTION_DEFAULT_MAX_BODY_BYTES


def _call_assertion_args_hash(arguments: Any) -> str:
    """sha256 of the canonical JSON of tools/call params.arguments (the `args` claim)."""
    canonical = json.dumps(arguments if arguments is not None else {}, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _call_assertion_public_key() -> Any:
    pem = os.getenv("MCP_CALL_ASSERTION_PUBLIC_KEY", "").strip()
    if not pem:
        return None
    if pem not in _CALL_ASSERTION_KEYS:
        try:
            key = _assertion_serialization.load_pem_public_key(pem.encode("utf-8"))
        except ValueError:
            key = None
        if not isinstance(key, _AssertionPublicKey):
            _ASSERTION_LOG.error("MCP_CALL_ASSERTION_PUBLIC_KEY is not an Ed25519 public key; every assertion is refused")
            key = None
        _CALL_ASSERTION_KEYS[pem] = key
    return _CALL_ASSERTION_KEYS[pem]


ASSERTION_CALLER_HEADER = "x-zuno-assertion-caller"


def _strip_assertion_caller(scope: Any) -> Any:
    """The scope without any client-sent X-Zuno-Assertion-Caller header."""
    headers = scope.get("headers") or []
    wanted = ASSERTION_CALLER_HEADER.encode("latin-1")
    if not any(k.lower() == wanted for k, _ in headers):
        return scope
    cleaned = dict(scope)
    cleaned["headers"] = [(k, v) for k, v in headers if k.lower() != wanted]
    return cleaned


def _with_assertion_caller(scope: Any, claims: Dict[str, Any]) -> Any:
    """The scope carrying the caller context of a VERIFIED assertion, if it has one."""
    ctx = claims.get("ctx")
    if not isinstance(ctx, dict):
        return scope
    payload = {
        "sub": claims.get("sub", ""),
        "tool": claims.get("tool", ""),
        "groups": ctx.get("groups", []),
        "email": ctx.get("email", ""),
        "email_verified": ctx.get("email_verified") is True,
        "username": ctx.get("username", ""),
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
    carried = dict(scope)
    carried["headers"] = list(scope.get("headers") or []) + [(ASSERTION_CALLER_HEADER.encode("latin-1"), raw.encode("ascii"))]
    return carried


def _assertion_caller(headers: Optional[Mapping[str, str]], tool: str) -> Optional[Dict[str, Any]]:
    """The caller of a call that arrived with a verified assertion carrying `ctx`, or None."""
    raw = (headers.get(ASSERTION_CALLER_HEADER) if headers else "") or ""
    if not raw:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("tool") != tool:
        return None
    groups = payload.get("groups")
    return {
        "sub": str(payload.get("sub") or ""),
        "groups": [str(g) for g in groups] if isinstance(groups, list) else [],
        "email": str(payload.get("email") or "").lower(),
        "email_verified": payload.get("email_verified") is True,
        "username": str(payload.get("username") or ""),
    }


def _call_assertion_type(token: str) -> str:
    try:
        return str(_assertion_jwt.get_unverified_header(token).get("typ") or "")
    except _assertion_jwt.PyJWTError:
        return ""


def _verify_call_assertion(token: str, key: Any, now: Optional[float] = None) -> Dict[str, Any]:
    if key is None:
        raise CallAssertionError("no call-assertion public key is configured")
    try:
        claims = _assertion_jwt.decode(
            token,
            key,
            algorithms=["EdDSA"],
            audience=CALLER_CONTEXT_AUDIENCE,
            issuer=CALL_ASSERTION_ISSUER,
            options={"require": ["exp", "iat", "aud", "iss", "sub", "jti"], "verify_exp": False, "verify_iat": False},
        )
    except _assertion_jwt.PyJWTError as exc:
        raise CallAssertionError(f"invalid call assertion: {exc}") from exc
    current = time.time() if now is None else now
    iat, exp = claims.get("iat"), claims.get("exp")
    if not isinstance(iat, int) or not isinstance(exp, int) or exp < iat or exp - iat > CALL_ASSERTION_MAX_TTL_SECONDS:
        raise CallAssertionError("call assertion lifetime is not within 60 seconds")
    if iat > current + CALL_ASSERTION_LEEWAY_SECONDS or current > exp + CALL_ASSERTION_LEEWAY_SECONDS:
        raise CallAssertionError("call assertion expired or not yet valid")
    act = claims.get("act")
    if not isinstance(act, dict) or act.get("sub") != CALL_ASSERTION_ISSUER:
        raise CallAssertionError("call assertion has no gateway actor")
    if not isinstance(claims.get("tool"), str) or not isinstance(claims.get("jti"), str):
        raise CallAssertionError("call assertion has no tool or jti")
    if "args" in claims and not isinstance(claims["args"], str):
        raise CallAssertionError("call assertion has a malformed args hash")
    ctx = claims.get("ctx")
    if ctx is not None and (
        not isinstance(ctx, dict)
        or not isinstance(ctx.get("groups", []), list)
        or not all(isinstance(g, str) for g in ctx.get("groups", []))
    ):
        raise CallAssertionError("call assertion has a malformed caller context")
    return claims


def _consume_call_assertion(jti: str, exp: int, now: Optional[float] = None) -> bool:
    """True the first time a jti is used for a tools/call; False on a replay."""
    current = time.time() if now is None else now
    for seen, until in list(_CALL_ASSERTION_SEEN.items()):
        if until < current:
            del _CALL_ASSERTION_SEEN[seen]
    if jti in _CALL_ASSERTION_SEEN:
        return False
    _CALL_ASSERTION_SEEN[jti] = exp + CALL_ASSERTION_LEEWAY_SECONDS
    return True


def _called_tools(body: bytes) -> Optional[List[Any]]:
    """The tools/call messages of a body: [(name, arguments)]; None when the body is not JSON."""
    if not body:
        return []
    try:
        message = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    messages = message if isinstance(message, list) else [message]
    calls = []
    for item in messages:
        if isinstance(item, dict) and item.get("method") == "tools/call":
            params = item.get("params") if isinstance(item.get("params"), dict) else {}
            calls.append((str(params.get("name") or ""), params.get("arguments")))
    return calls


class CallAssertionMiddleware:
    """Pure ASGI, so the body read for a tools/call is replayed to the MCP app intact."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        scope = _strip_assertion_caller(scope)
        key, required = _call_assertion_public_key(), _call_assertion_required()
        if not required and not os.getenv("MCP_CALL_ASSERTION_PUBLIC_KEY", "").strip():
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        auth = headers.get("authorization", "")
        token = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
        if not token or _call_assertion_type(token) != CALL_ASSERTION_TYPE:
            if required:
                await JSONResponse({"detail": "a gateway call assertion is required"}, status_code=401)(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return
        try:
            claims = _verify_call_assertion(token, key)
        except CallAssertionError as exc:
            _ASSERTION_LOG.warning("call assertion refused: %s", exc)
            await JSONResponse({"detail": str(exc)}, status_code=401)(scope, receive, send)
            return
        chunks, size, more, limit = [], 0, True, _call_assertion_max_body_bytes()
        while more:
            message = await receive()
            if message.get("type") != "http.request":
                break
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                await JSONResponse({"detail": "request body too large"}, status_code=413)(scope, receive, send)
                return
            chunks.append(chunk)
            more = message.get("more_body", False)
        body = b"".join(chunks)
        called = _called_tools(body)
        if called is None:
            await JSONResponse({"detail": "the request body is not JSON"}, status_code=400)(scope, receive, send)
            return
        if called:
            names = [name for name, _ in called]
            if len(called) != 1 or names[0] != claims["tool"]:
                _ASSERTION_LOG.warning("call assertion for tool %r refused for tools/call %s", claims["tool"], names)
                await JSONResponse({"detail": "the call assertion was minted for another tool"}, status_code=403)(scope, receive, send)
                return
            if "args" in claims and claims["args"] != _call_assertion_args_hash(called[0][1]):
                _ASSERTION_LOG.warning("call assertion for tool %r refused: the arguments differ", claims["tool"])
                await JSONResponse({"detail": "the call assertion was minted for other arguments"}, status_code=403)(scope, receive, send)
                return
            if not _consume_call_assertion(claims["jti"], claims["exp"]):
                _ASSERTION_LOG.warning("call assertion replay refused (jti %s)", claims["jti"])
                await JSONResponse({"detail": "the call assertion was already used"}, status_code=403)(scope, receive, send)
                return
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(_with_assertion_caller(scope, claims), replay, send)


# END call-assertion verifier (WP-225 lot C)
# --------------------------------------------------------------------------


mcp_asgi_app: ASGIApp = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(
        allowed_hosts=os.getenv(
            "MCP_ALLOWED_HOSTS",
            "aap-mcp.zuno-ai-run.svc:8000,aap-mcp.zuno-ai-run.svc.cluster.local:8000,aap-mcp:8000,localhost:8000,127.0.0.1:8000",
        ).split(","),
    ),
)
mcp_asgi_app.add_middleware(CallAssertionMiddleware)
app.mount("/", mcp_asgi_app)
