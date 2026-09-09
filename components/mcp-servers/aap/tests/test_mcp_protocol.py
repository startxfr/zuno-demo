"""ADR-0043/ADR-0119 protocol tests plus ADR-0355 behavioural tests for the
aap MCP server.

Two layers, same style as components/mcp-servers/git-forge/tests/:

  - protocol: the /mcp endpoint speaks real, standards-compliant MCP
    streamable-HTTP, and rejects a caller with no gateway token before any
    protocol handling (ADR-0037).
  - behaviour: AAP itself is mocked at the transport boundary
    (`server._client` is replaced with an httpx.AsyncClient over an
    httpx.MockTransport), so every Controller response shape - healthy,
    401, unreachable, still-running - is exercised without a live cluster.

The security-relevant assertions here are the ones proving `cluster_audit`
cannot be retargeted: it exposes no template parameter in its MCP input
schema, and it POSTs to the id resolved from JOB_TEMPLATE_NAME with an
empty body. The complementary end-to-end check that an *unauthorized group*
cannot reach the capability through the gateway lives in
evaluations/tekos/security_checks.py (it needs a live gateway + Keycloak).

Run from this directory:

    python3 tests/test_mcp_protocol.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

os.environ.setdefault("MCP_GATEWAY_WORKLOAD_TOKEN", "test-workload-token")
os.environ.setdefault("AAP_API_TOKEN", "test-token")
os.environ.setdefault("AAP_BASE_URL", "http://aap.zuno-aap.svc")
os.environ.setdefault("AAP_CONTROLLER_UI_URL", "https://aap.apps.demo333.startx.fr")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
import httpx2  # noqa: E402
from httpx2 import ASGITransport  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

import server  # noqa: E402

BASE_URL = "http://localhost:8000"
GATEWAY_HEADERS = {"X-Zuno-Gateway-Token": "test-workload-token"}

JOB_TEMPLATE_ID = 8
OTHER_TEMPLATE_ID = 99


class _Recorder:
    """Captures every request the server makes to AAP, so a test can assert
    on the method/path/body actually sent - not just on the tool's return."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bytes]] = []

    def paths(self) -> list[str]:
        return [path for _, path, _ in self.calls]

    def methods(self) -> set[str]:
        return {method for method, _, _ in self.calls}


def _install_mock(handler, recorder: _Recorder):
    """Replace server._client with one wired to `handler`, keeping the real
    _require_config() check so credential tests still bite."""

    def _factory() -> httpx.AsyncClient:
        server._require_config()

        def _wrapped(request: httpx.Request) -> httpx.Response:
            recorder.calls.append((request.method, request.url.path, request.content))
            return handler(request)

        return httpx.AsyncClient(
            transport=httpx.MockTransport(_wrapped),
            base_url=server.AAP_BASE_URL,
            timeout=5.0,
        )

    return _factory


def _json(payload, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def _job_events_page():
    """A page of job_events as the real API would order it (order_by=
    -counter: most recent first). Alternates blank-stdout events (play/task
    start markers) with real output, so tests can prove _job_log_tail keeps
    only the non-empty ones and restores chronological order."""
    return _json({"count": 8, "results": [
        {"counter": 10, "stdout": "PLAY RECAP *********************"},
        {"counter": 9, "stdout": ""},
        {"counter": 8, "stdout": "ok: [localhost]"},
        {"counter": 7, "stdout": ""},
        {"counter": 6, "stdout": "TASK [gather facts] ***"},
        {"counter": 5, "stdout": ""},
        {"counter": 4, "stdout": "PLAY [zuno-day0-check] ***"},
        {"counter": 3, "stdout": ""},
    ]})


def _healthy_handler(job_status: str = "running"):
    """A Controller that answers every path platform_audit/cluster_audit use.

    job_status: what GET /jobs/<id>/ reports. cluster_audit only reads this
    once, immediately after launch (ADR-0524, 2026-09-09: it no longer polls
    to a terminal status - see server.cluster_audit's own docstring), so the
    realistic default is a non-terminal status like 'running'.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/controller/v2/ping/":
            return _json({
                "version": "4.6.0",
                "ha": False,
                "active_node": "aap-controller-task-0",
                "instances": [{
                    "node": "aap-controller-task-0",
                    "node_type": "hybrid",
                    "heartbeat": "2026-08-27T09:00:00Z",
                    "capacity": 42,
                }],
            })
        if path == "/api/controller/v2/projects/":
            return _json({"count": 1, "results": [{
                "name": "zuno-demo", "status": "successful", "scm_branch": "main",
                "scm_revision": "deadbeef", "last_job_run": "2026-08-27T08:00:00Z",
                "last_update_failed": False,
            }]})
        if path == "/api/controller/v2/job_templates/":
            return _json({"count": 1, "results": [{
                "id": JOB_TEMPLATE_ID, "name": "zuno-day0-check",
                "playbook": "ansible/playbooks/day0_check.yml",
                "status": "successful", "last_job_run": "2026-08-27T08:30:00Z",
            }]})
        if path == f"/api/controller/v2/job_templates/{JOB_TEMPLATE_ID}/jobs/":
            return _json({"count": 1, "results": [
                {"id": 41, "status": "successful", "failed": False, "elapsed": 12.0},
            ]})
        if path == f"/api/controller/v2/job_templates/{JOB_TEMPLATE_ID}/launch/":
            return _json({"id": 42, "job": 42}, status=201)
        if path == "/api/controller/v2/jobs/42/":
            return _json({
                "id": 42, "status": job_status, "failed": job_status == "failed",
                "started": "2026-08-27T09:00:00Z",
                "finished": "2026-08-27T09:02:00Z" if job_status == "successful" else None,
                "elapsed": 120.0,
            })
        if path in ("/api/controller/v2/jobs/41/job_events/", "/api/controller/v2/jobs/42/job_events/"):
            return _job_events_page()
        return _json({"detail": f"unexpected path {path}"}, status=418)

    return handler


# --------------------------------------------------------------------------
# protocol layer
# --------------------------------------------------------------------------

async def test_unauthenticated_call_rejected_before_any_protocol_handling(transport) -> None:
    async with httpx2.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0"},
            headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        )
    assert resp.status_code == 401, f"expected 401 with no gateway token, got {resp.status_code}"


async def _open_session(transport, headers):
    http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers)
    return streamable_http_client(f"{BASE_URL}/mcp", http_client=http_client)


async def test_tools_list_reports_both_capabilities(transport) -> None:
    async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    names = {tool.name for tool in result.tools}
    assert names == {"platform_audit", "cluster_audit"}, f"unexpected tool set: {names}"


async def test_cluster_audit_exposes_no_template_parameter(transport) -> None:
    """ADR-0355 Security considerations: the launch capability must not be
    retargetable. If a template/job-template/playbook argument ever appears
    in its schema, the server-construction half of the defence is gone."""
    async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    tool = next(t for t in result.tools if t.name == "cluster_audit")
    properties = (tool.input_schema or {}).get("properties") or {}
    assert properties == {}, f"cluster_audit must take no arguments, got {sorted(properties)}"


# --------------------------------------------------------------------------
# behaviour layer
# --------------------------------------------------------------------------

async def test_platform_audit_summarizes_a_healthy_platform(transport) -> None:
    recorder = _Recorder()
    server._client = _install_mock(_healthy_handler(), recorder)
    result = await server.platform_audit()

    assert result["controller"]["version"] == "4.6.0"
    assert result["controller"]["instances"][0]["node"] == "aap-controller-task-0"
    assert result["project"]["scm_revision"] == "deadbeef"
    assert result["job_template"]["name"] == "zuno-day0-check"
    assert len(result["recent_runs"]) == 1
    assert recorder.methods() == {"GET"}, f"platform_audit must be read-only, saw {recorder.methods()}"


async def test_platform_audit_rejects_an_out_of_range_recent_jobs(transport) -> None:
    recorder = _Recorder()
    server._client = _install_mock(_healthy_handler(), recorder)
    for bad in (0, 26, "5"):
        try:
            await server.platform_audit(recent_jobs=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"recent_jobs={bad!r} should have been rejected")
    assert recorder.calls == [], "argument validation must happen before any backend call"


async def test_cluster_audit_launches_only_the_authorized_template(transport) -> None:
    recorder = _Recorder()
    server._client = _install_mock(_healthy_handler(), recorder)
    result = await server.cluster_audit()

    assert result["launched"] is True
    assert result["job"]["id"] == 42
    assert "42" in result["message"], "the message must name the job id"

    posts = [(path, body) for method, path, body in recorder.calls if method == "POST"]
    assert len(posts) == 1, f"exactly one POST expected, got {posts}"
    path, body = posts[0]
    assert path == f"/api/controller/v2/job_templates/{JOB_TEMPLATE_ID}/launch/", path
    assert f"/job_templates/{OTHER_TEMPLATE_ID}/" not in path
    # Bare launch: ask_variables_on_launch is false on the template, and any
    # extra_vars would reopen the injection surface ADR-0355 closes.
    assert body in (b"", b"null"), f"launch body must be empty, got {body!r}"


async def test_cluster_audit_returns_immediately_without_waiting_for_completion(transport) -> None:
    """ADR-0524 (2026-09-09): a real AAP job takes a few minutes, but
    OpenShift Lightspeed's console plugin times out well before that -
    cluster_audit must launch and return right away, reporting whatever
    status the job has THAT INSTANT (here: still 'running'), never wait for
    a terminal one."""
    recorder = _Recorder()
    server._client = _install_mock(_healthy_handler(job_status="running"), recorder)
    result = await server.cluster_audit()

    assert result["job"]["status"] == "running", "must report the immediate status, not wait for one"
    polls = [p for p in recorder.paths() if p == "/api/controller/v2/jobs/42/"]
    assert len(polls) == 1, f"expected exactly one status read, no poll loop, got {len(polls)}"


async def test_cluster_audit_includes_a_job_url_and_log_tail(transport) -> None:
    recorder = _Recorder()
    server._client = _install_mock(_healthy_handler(), recorder)
    result = await server.cluster_audit()

    assert result["job"]["url"] == "https://aap.apps.demo333.startx.fr/#/jobs/playbook/42/output"
    # _job_events_page has 4 non-empty entries among 8, most-recent-first;
    # log_tail must keep only those, restored to chronological order.
    assert result["job"]["log_tail"] == [
        "PLAY [zuno-day0-check] ***",
        "TASK [gather facts] ***",
        "ok: [localhost]",
        "PLAY RECAP *********************",
    ]
    events_calls = [p for p in recorder.paths() if p == "/api/controller/v2/jobs/42/job_events/"]
    assert len(events_calls) == 1, f"expected exactly one job_events call, got {len(events_calls)}"


async def test_platform_audit_attaches_log_tail_only_to_the_latest_run(transport) -> None:
    recorder = _Recorder()
    server._client = _install_mock(_healthy_handler(), recorder)
    result = await server.platform_audit()

    latest = result["recent_runs"][0]
    assert latest["id"] == 41
    assert latest["url"] == "https://aap.apps.demo333.startx.fr/#/jobs/playbook/41/output"
    assert latest["log_tail"] == [
        "PLAY [zuno-day0-check] ***",
        "TASK [gather facts] ***",
        "ok: [localhost]",
        "PLAY RECAP *********************",
    ]
    events_calls = [p for p in recorder.paths() if p == "/api/controller/v2/jobs/41/job_events/"]
    assert len(events_calls) == 1, (
        f"only the most recent run should trigger a job_events call, got {len(events_calls)}"
    )


async def test_job_url_is_none_without_a_configured_ui_url(transport) -> None:
    original = server.AAP_CONTROLLER_UI_URL
    server.AAP_CONTROLLER_UI_URL = ""
    try:
        assert server._job_url(42) is None
        assert server._summarize_job({"id": 42, "status": "running"})["url"] is None
    finally:
        server.AAP_CONTROLLER_UI_URL = original


async def test_expired_token_surfaces_as_a_clear_error(transport) -> None:
    """ADR-0355 Operational considerations: a 401 must not reach the agent as
    an opaque failure."""
    recorder = _Recorder()
    server._client = _install_mock(lambda request: _json({"detail": "nope"}, status=401), recorder)
    for tool in (server.platform_audit, server.cluster_audit):
        try:
            await tool()
        except ValueError as exc:
            assert "expired" in str(exc), f"{tool.__name__}: {exc}"
            assert "aap-config" in str(exc), f"{tool.__name__} should say how to fix it: {exc}"
        else:
            raise AssertionError(f"{tool.__name__} must raise on 401")


async def test_unreachable_controller_surfaces_as_a_clear_error(transport) -> None:
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    recorder = _Recorder()
    server._client = _install_mock(_boom, recorder)
    for tool in (server.platform_audit, server.cluster_audit):
        try:
            await tool()
        except ValueError as exc:
            assert "unreachable" in str(exc), f"{tool.__name__}: {exc}"
            assert "NetworkPolicy" in str(exc), f"{tool.__name__}: {exc}"
        else:
            raise AssertionError(f"{tool.__name__} must raise when the Controller is down")


async def test_missing_job_template_names_the_likely_cause(transport) -> None:
    recorder = _Recorder()
    server._client = _install_mock(lambda request: _json({"count": 0, "results": []}), recorder)
    try:
        await server.cluster_audit()
    except ValueError as exc:
        assert "zuno-day0-check" in str(exc), str(exc)
        assert "aap-config" in str(exc), str(exc)
    else:
        raise AssertionError("a missing Job Template must raise")


async def test_missing_credentials_are_refused_before_any_call(transport) -> None:
    original_token, original_url = server.AAP_API_TOKEN, server.AAP_BASE_URL
    try:
        server.AAP_API_TOKEN = ""
        for tool in (server.platform_audit, server.cluster_audit):
            try:
                await tool()
            except server.AapConfigError as exc:
                assert "mcp-token" in str(exc), str(exc)
            else:
                raise AssertionError(f"{tool.__name__} must refuse without a token")
        server.AAP_API_TOKEN = original_token
        server.AAP_BASE_URL = ""
        try:
            await server.platform_audit()
        except server.AapConfigError as exc:
            assert "aap-controller-service" in str(exc), str(exc)
        else:
            raise AssertionError("platform_audit must refuse without a base URL")
    finally:
        server.AAP_API_TOKEN, server.AAP_BASE_URL = original_token, original_url


async def test_healthz_never_calls_the_controller(transport) -> None:
    """ADR-0037/ADR-0355: a Controller outage must degrade these two tools,
    never this pod's own liveness."""
    recorder = _Recorder()

    def _boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("/healthz must not call the backend")

    server._client = _install_mock(_boom, recorder)
    async with httpx2.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200, resp.status_code
    assert resp.json() == {"status": "ok"}
    assert recorder.calls == []


TESTS = [
    test_unauthenticated_call_rejected_before_any_protocol_handling,
    test_tools_list_reports_both_capabilities,
    test_cluster_audit_exposes_no_template_parameter,
    test_platform_audit_summarizes_a_healthy_platform,
    test_platform_audit_rejects_an_out_of_range_recent_jobs,
    test_cluster_audit_launches_only_the_authorized_template,
    test_cluster_audit_returns_immediately_without_waiting_for_completion,
    test_cluster_audit_includes_a_job_url_and_log_tail,
    test_platform_audit_attaches_log_tail_only_to_the_latest_run,
    test_job_url_is_none_without_a_configured_ui_url,
    test_expired_token_surfaces_as_a_clear_error,
    test_unreachable_controller_surfaces_as_a_clear_error,
    test_missing_job_template_names_the_likely_cause,
    test_missing_credentials_are_refused_before_any_call,
    test_healthz_never_calls_the_controller,
]


async def _run_all() -> int:
    transport = ASGITransport(app=server.app)
    lifespan_cm = server.app.router.lifespan_context(server.app)
    await lifespan_cm.__aenter__()

    real_client = server._client
    failures = 0
    try:
        for test in TESTS:
            server._client = real_client
            try:
                await test(transport)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {test.__name__}: {exc}")
            else:
                print(f"PASS {test.__name__}")
    finally:
        server._client = real_client
        await lifespan_cm.__aexit__(None, None, None)
    return failures


def main() -> int:
    failures = asyncio.run(_run_all())
    print()
    print(f"{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
