#!/usr/bin/env python3
"""WP-155 wave 0: offline tests for the shared UnifAI evaluation target and for the per-agent
scripts that use it (UnifAI is the only target since WP-156). No network: HTTP is served by httpx.MockTransport, and each agent's
scripts are imported in a subprocess (their modules share names, and AGENT is read at import).

    cd evaluations && python3 -m pytest tests/test_unifai_target.py -q
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import textwrap

import httpx

EVAL = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVAL / "common"))

import unifai_target as ut  # noqa: E402

UI = "https://ui.test"
KC = "https://kc.test/auth"


def _ndjson(*chunks):
    return "\n".join(json.dumps(c) for c in chunks) + "\n"


class Recorder:
    def __init__(self):
        self.requests = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.url.host == "ui.test" and path == "/api3/auth/login":
            return httpx.Response(200, text=f'<form id="kc-form-login" action="{KC}/login?x=1&amp;y=2">')
        if request.url.host == "kc.test":
            body = request.content.decode()
            assert "username=eval-consultant-01" in body and "password=pw" in body
            return httpx.Response(302, headers={"location": f"{UI}/", "set-cookie": "session=abc; Path=/"})
        if path == "/":
            return httpx.Response(200, text="ui")
        if path == "/api2/blueprints/available.blueprints.summary.get":
            assert request.url.params.get("teamId") == "team-1"
            return httpx.Response(200, json=[{"name": "other", "blueprint_id": "b0"}, {"name": "arkos", "blueprint_id": "b1"}])
        if path == "/api2/sessions/user.session.create":
            return httpx.Response(200, json="sess-1")
        if path == "/api2/sessions/user.session.execute":
            return httpx.Response(
                200,
                text=_ndjson(
                    {"type": "heartbeat"},
                    {"type": "tool_calling", "tool": "confluence.page.search"},
                    {"type": "llm_token", "token": "x"},
                    {"type": "complete", "state": {"output": "the answer"}},
                ),
            )
        if path == "/api2/sessions/session.delete":
            return httpx.Response(200, json=True)
        if path == "/api3/teams/teams.list":
            return httpx.Response(200, json={"teams": [{"team_id": "t-other", "name": "x"}, {"team_id": "t-arkos", "name": "agent-arkos"}]})
        if path == "/api3/teams/team.create":
            body = json.loads(request.content)
            if body["name"] == "taken":
                return httpx.Response(400, json={"error": "Team with name 'taken' already exists"})
            return httpx.Response(201, json={"team_id": "t-new", "name": body["name"], "members": body["members"]})
        return httpx.Response(404)


def _target(monkeypatch, agent="arkos"):
    rec = Recorder()
    real_client = httpx.Client

    def factory(*a, **kw):
        kw.pop("verify", None)
        return real_client(*a, transport=httpx.MockTransport(rec.handler), **kw)

    monkeypatch.setattr(ut.httpx, "Client", factory)
    return ut.UnifaiTarget("pw", ui_url=UI, agent=agent, team_id="team-1"), rec


def test_login_session_stream_and_cleanup(monkeypatch):
    t, rec = _target(monkeypatch)
    r = t.run("consultant-01", "hello")
    assert r.status == 200 and r.reply == "the answer" and r.session_id == "sess-1"
    assert r.raw["tool_calls"] == ["confluence.page.search"]
    create = next(q for q in rec.requests if q.url.path.endswith("user.session.create"))
    body = json.loads(create.content)
    assert body["blueprintId"] == "b1" and body["teamId"] == "team-1"  # the agent's workflow, in the team workspace
    execute = next(q for q in rec.requests if q.url.path.endswith("user.session.execute"))
    ebody = json.loads(execute.content)
    assert ebody["sessionId"] == "sess-1" and ebody["stream"] is True and ebody["teamId"] == "team-1"
    assert t.cleanup() == (1, 0)


def test_team_name_is_resolved_at_sign_in(monkeypatch):
    # WP-156: in-cluster Jobs name the team (agent-<name>), its id changes when the operator recreates it.
    rec = Recorder()
    real_client = httpx.Client

    def factory(*a, **kw):
        kw.pop("verify", None)
        return real_client(*a, transport=httpx.MockTransport(rec.handler), **kw)

    monkeypatch.setattr(ut.httpx, "Client", factory)
    monkeypatch.delenv("UNIFAI_TEAM_ID", raising=False)
    t = ut.UnifaiTarget("pw", ui_url=UI, agent="arkos", team_name="agent-arkos")
    assert t.team_id == ""
    t.client("consultant-01")
    assert t.team_id == "t-arkos"
    unknown = ut.UnifaiTarget("pw", ui_url=UI, agent="arkos", team_name="agent-nope")
    unknown.client("consultant-01")
    assert unknown.team_id == ""  # not a member: stays in the personal workspace


def test_create_team_sends_group_members_and_reports_a_taken_name(monkeypatch):
    t, rec = _target(monkeypatch)
    team = t.create_team("consultant-01", "webinar-public", ["consultant", "sales"])
    assert team["team_id"] == "t-new"
    body = json.loads(next(q for q in rec.requests if q.url.path.endswith("team.create")).content)
    assert [m["id"] for m in body["members"]] == ["consultant", "sales"] and {m["type"] for m in body["members"]} == {"group"}
    try:
        t.create_team("consultant-01", "taken", ["sales"])
    except ut.UnifaiError as exc:
        assert "400" in str(exc)
    else:
        raise AssertionError("a taken team name must raise")


def test_routing_of_reads_the_last_assistant_message():
    routing = {"provider": "local-wesh", "model": "qwen", "kind": "local", "classification": "C2", "fallback_used": False}
    state = {
        "messages": [
            {"role": "assistant", "content": "older", "metadata": {"llm_response": {"routing": {"provider": "old"}}}},
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a", "metadata": {"llm_response": {"request_id": "r", "routing": routing}}},
        ]
    }
    assert ut.routing_of(state) == routing
    assert ut.routing_of({"messages": [{"role": "assistant", "content": "a", "metadata": {}}]}) is None
    assert ut.routing_of({}) is None


def test_run_exposes_the_routing_decision(monkeypatch):
    t, rec = _target(monkeypatch)
    routing = {"provider": "ovhcloud-gpt-oss-120b", "model": "gpt-oss-120b"}
    orig = rec.handler

    def handler(request):
        if request.url.path == "/api2/sessions/user.session.execute":
            state = {"output": "ok", "messages": [{"role": "assistant", "content": "ok", "metadata": {"llm_response": {"routing": routing}}}]}
            return httpx.Response(200, text=_ndjson({"type": "complete", "state": state}))
        return orig(request)

    rec.handler = handler
    r = t.run("consultant-01", "hello")
    assert r.raw["routing"] == routing


def test_workflow_defaults_to_agent_and_env_override(monkeypatch):
    t, _ = _target(monkeypatch, agent="arkos")
    assert t.workflow_id("consultant-01") == "b1"
    monkeypatch.setenv("UNIFAI_WORKFLOW", "other")
    assert t.workflow_id("consultant-01") == "b0"
    try:
        t.workflow_id("consultant-01", "missing")
    except ut.UnifaiError:
        pass
    else:
        raise AssertionError("an invisible workflow must raise")


def test_collect_stops_on_wanted_tool_and_builds_summary(monkeypatch):
    t, _ = _target(monkeypatch)
    got = t.collect("consultant-01", "q", stop_on=ut.wanted_tools("search_confluence"))
    assert got["tools"] == ["confluence.page.search"] and got["stopped"] and not got["timed_out"]
    full = t.collect("consultant-01", "q")
    assert full["reply"] == "the answer" and "llm_token" in full["blob"]


def test_tool_aliases_accept_the_retriever():
    assert "docs_rag_retriever_tool" in ut.wanted_tools("search_confluence")
    assert ut.wanted_tools("something.else") == ("something.else",)


def test_tekos_import_path_is_a_thin_reexport():
    code = (
        "import sys; sys.path.insert(0, %r); import unifai_target as u; "
        "assert u.UnifaiTarget.__module__ == 'zuno_eval_common_unifai_target'; print('ok')" % str(EVAL / "tekos")
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "ok", out.stderr


def test_skip_is_never_a_pass():
    import unifai_checks
    from dataclasses import dataclass

    @dataclass
    class CheckResult:
        name: str
        passed: bool
        detail: str = ""
        skipped: bool = False

    r = unifai_checks.skip(CheckResult, "n", "because")()
    assert r.skipped and not r.passed and "because" in r.detail


AGENTS = ["tekos", "comage", "arkos", "advantage", "finage", "naveo"]
PLACEHOLDERS = {"advantage", "finage", "naveo"}


def _probe(agent: str, code: str) -> str:
    script = textwrap.dedent(
        f"""
        import os, sys
        sys.argv = ["x", "--target", "unifai"]
        os.environ["AGENT"] = {agent!r}
        sys.path.insert(0, {str(EVAL / "tekos")!r})
        os.environ.setdefault("DEMO_PERSONA_PASSWORD", "pw")
        import importlib.util
        def load_security_checks():
            # by path, as run_acceptance_gate.py does: several agents ship a module of that name
            spec = importlib.util.spec_from_file_location("security_checks", {str(EVAL / agent / "security_checks.py")!r})
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            return mod
        """
    ) + textwrap.dedent(code)
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=EVAL / agent)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_every_agent_run_scenarios_selects_unifai_and_covers_every_scenario_type():
    for agent in AGENTS:
        out = _probe(
            agent,
            """
            import yaml, pathlib
            import run_scenarios as rs
            assert rs.TARGET == "unifai" and rs.AGENT == os.environ["AGENT"]
            types = {s["type"] for s in yaml.safe_load(pathlib.Path(rs.__file__).resolve().parent.parent.joinpath(rs.AGENT, "scenarios.yaml").read_text())["scenarios"]}
            missing = types - set(rs.HANDLERS)
            # chat-shaped types must be served by the UnifAI transport (the u_ handlers)
            for t in types & {"chat_basic_qa","chat_first_token_latency","chat_streaming_sse","chat_triggers_tool","chat_register_conformance","chat_blocked_for_placeholder_agent","rag_retrieval_has_citation","health_endpoints_all_ok"}:
                assert rs.HANDLERS[t].__name__.startswith("u_"), t
            # every `services:` list names a service the health handler knows
            known = {"unifai-ui", "mcp-gateway", "ai-gateway"}
            for s in yaml.safe_load(pathlib.Path(rs.__file__).resolve().parent.parent.joinpath(rs.AGENT, "scenarios.yaml").read_text())["scenarios"]:
                assert set(s.get("services", [])) <= known, s.get("services")
                assert "via" not in s, s["id"]
            print("missing=" + ",".join(sorted(missing)))
            """,
        )
        assert out.endswith("missing="), (agent, out)


def test_any_other_target_is_refused():
    script = textwrap.dedent(
        f"""
        import os, sys
        os.environ["EVAL_TARGET"] = "legacy"
        sys.path.insert(0, {str(EVAL / "tekos")!r})
        import run_scenarios
        """
    )
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=EVAL / "tekos")
    assert out.returncode != 0 and "only target" in out.stderr, out.stderr


def test_every_agent_security_checks_run_only_unifai_checks():
    for agent in AGENTS:
        out = _probe(
            agent,
            """
            sc = load_security_checks()
            names = [c.__name__ for c in sc.CHECKS]
            assert not any("bff" in n or "runtime" in n for n in names), names
            assert "unifai_forwards_identity_to_the_gateways" in names
            assert "unifai_ignores_a_client_supplied_identity_header" in names
            assert "business_role_without_entitlement_denied_by_unifai" in names
            assert not hasattr(sc, "_UNIFAI_REPLACEMENTS")
            print("ok")
            """,
        )
        assert out == "ok", (agent, out)


def test_placeholder_agents_skip_chat_scenarios_and_identity_check():
    for agent in PLACEHOLDERS:
        out = _probe(
            agent,
            """
            import run_scenarios as rs
            sc = load_security_checks()
            assert rs._agent_status() == "placeholder"
            r = rs.u_chat_basic_qa({"id": 1, "title": "t", "persona": "p", "message": "m"})
            assert r.skipped and not r.passed
            c = sc.unifai_forwards_identity_to_the_gateways()
            assert c.skipped and not c.passed and "placeholder" in c.detail
            print("ok")
            """,
        )
        assert out == "ok", (agent, out)


def test_active_agents_do_not_skip():
    for agent in ["tekos", "arkos", "comage"]:
        out = _probe(agent, "import run_scenarios as rs\nassert rs._agent_status() == 'active'\nprint('ok')")
        assert out == "ok", (agent, out)


def test_login_name_uses_the_evaluation_twin_for_business_personas(monkeypatch):
    from common.unifai_target import login_name

    monkeypatch.delenv("EVAL_PERSONAS", raising=False)
    for p in ("consultant-01", "sale-01", "adv-01", "finance-01", "board-01"):
        assert login_name(p) == f"eval-{p}"
    # negative personas and other users keep their own account
    assert login_name("consultant-role-only-user-01") == "consultant-role-only-user-01"
    assert login_name("consultant-02") == "consultant-02"


def test_login_name_can_be_switched_off(monkeypatch):
    from common.unifai_target import login_name

    monkeypatch.setenv("EVAL_PERSONAS", "0")
    assert login_name("consultant-01") == "consultant-01"


def test_tekos_reexport_exposes_login_name():
    """evaluations/tekos puts its own directory first on sys.path, so its shim is what the gate imports."""
    import importlib.util
    import pathlib

    shim = pathlib.Path(__file__).resolve().parents[1] / "tekos" / "unifai_target.py"
    spec = importlib.util.spec_from_file_location("tekos_unifai_target_shim", shim)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.login_name("sale-01") == "eval-sale-01"


# --- comage scenario 11 (WP-155): the retrieval proven by the run's trace -----------------------------

TEMPO = "https://tempo.test"


def _tempo_client(traces, spans):
    """A Tempo that answers /api/search with `traces` and /api/traces/<id> with a trace holding `spans`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search":
            assert 'span.mas.run.id = "run-1"' in request.url.params["q"]
            return httpx.Response(200, json={"traces": traces})
        if request.url.path == "/api/traces/t1":
            return httpx.Response(200, json={"batches": [{"scopeSpans": [{"spans": spans}]}]})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _rag_span(count, source="CONFLUENCE"):
    return {
        "name": "rag.search",
        "attributes": [
            {"key": "rag.source_type", "value": {"stringValue": source}},
            {"key": "rag.results.count", "value": {"intValue": str(count)}},
        ],
    }


def test_tempo_rag_searches_returns_the_spans_of_the_run():
    spans = [_rag_span(5), _rag_span(0, "WEB"), {"name": "mas.session", "attributes": []}]
    got = ut.tempo_rag_searches("run-1", TEMPO, wait_seconds=0, client=_tempo_client([{"traceID": "t1"}], spans))
    assert got == [{"source_type": "CONFLUENCE", "results": 5}, {"source_type": "WEB", "results": 0}]


def test_tempo_rag_searches_is_empty_when_the_trace_has_no_retrieval_span():
    spans = [{"name": "mas.session", "attributes": []}]
    assert ut.tempo_rag_searches("run-1", TEMPO, wait_seconds=0, client=_tempo_client([{"traceID": "t1"}], spans)) == []


def test_tempo_rag_searches_is_empty_when_no_trace_matches_the_run():
    assert ut.tempo_rag_searches("run-1", TEMPO, wait_seconds=0, client=_tempo_client([], [])) == []


def test_tempo_rag_searches_raises_when_tempo_is_unreachable():
    def boom(request):
        raise httpx.ConnectError("down")

    client = httpx.Client(transport=httpx.MockTransport(boom))
    try:
        ut.tempo_rag_searches("run-1", TEMPO, wait_seconds=0, client=client)
    except ut.UnifaiError as exc:
        assert "unreachable" in str(exc)
    else:
        raise AssertionError("an unreachable Tempo must raise")


def _rag_executed(tempo_url: str, collect_result: str, searches: str) -> str:
    """Runs comage's u_rag_retrieval_executed with a stubbed turn and a stubbed Tempo helper."""
    return _probe(
        "comage",
        f"""
        import run_scenarios as rs
        os.environ["TEMPO_URL"] = {tempo_url!r}
        class FakeTarget:
            def collect(self, *a, **k):
                return {collect_result}
        rs._unifai_target = FakeTarget()
        def fake_searches(run_id, url):
            r = {searches}
            if isinstance(r, Exception):
                raise r
            return r
        rs._unifai_tempo_rag_searches = fake_searches
        res = rs.u_rag_retrieval_executed({{"id": 11, "title": "t", "query": "q"}})
        print(res.passed, res.skipped, res.detail)
        """,
    )


def test_rag_retrieval_executed_passes_on_a_rag_search_span():
    out = _rag_executed(
        "http://tempo", '{"session_id": "s1", "reply": "ok", "tools": []}', '[{"source_type": "CONFLUENCE", "results": 5}]'
    )
    assert out.startswith("True False") and "spans=1" in out and "results=[5]" in out, out


def test_rag_retrieval_executed_fails_without_any_span():
    out = _rag_executed("http://tempo", '{"session_id": "s1", "reply": "ok", "tools": []}', "[]")
    assert out.startswith("False False") and "spans=0" in out, out


def test_rag_retrieval_executed_fails_without_a_reply_or_when_tempo_is_down():
    out = _rag_executed("http://tempo", '{"session_id": "s1", "reply": "", "tools": []}', '[{"source_type": "WEB", "results": 1}]')
    assert out.startswith("False False"), out
    out = _rag_executed("http://tempo", '{"session_id": "s1", "reply": "ok", "tools": []}', "RuntimeError('down')")
    assert out.startswith("False False") and "trace backend" in out, out


def test_rag_retrieval_executed_is_skipped_not_passed_without_a_trace_backend():
    out = _rag_executed("", '{"session_id": "s1", "reply": "ok", "tools": []}', '[{"source_type": "WEB", "results": 1}]')
    assert out.startswith("False True") and "TEMPO_URL" in out, out
