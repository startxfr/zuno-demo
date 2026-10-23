#!/usr/bin/env python3
"""WP-155 wave 0: offline tests for the shared UnifAI evaluation target and for the per-agent
`--target unifai` selection. No network: HTTP is served by httpx.MockTransport, and each agent's
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
            handlers = {**rs.HANDLERS, **rs.UNIFAI_HANDLERS}
            missing = types - set(handlers)
            # chat-shaped types must be served by the UnifAI transport, not the BFF one
            for t in types & {"chat_basic_qa","chat_first_token_latency","chat_streaming_sse","chat_triggers_tool","chat_register_conformance","chat_blocked_for_placeholder_agent","rag_retrieval_has_citation"}:
                assert handlers[t] is rs.UNIFAI_HANDLERS[t], t
            print("missing=" + ",".join(sorted(missing)))
            """,
        )
        assert out.endswith("missing="), (agent, out)


def test_every_agent_security_checks_swaps_in_unifai_replacements():
    for agent in AGENTS:
        out = _probe(
            agent,
            """
            sc = load_security_checks()
            assert sc.TARGET == "unifai"
            if hasattr(sc, "unifai_checks"):
                names = [c.__name__ for c in sc.unifai_checks.select(sc.CHECKS, sc._UNIFAI_REPLACEMENTS, sc.TARGET)]
            else:
                names = [(sc._UNIFAI_REPLACEMENTS.get(c, c)).__name__ for c in sc.CHECKS]
            assert "bff_forwards_identity_to_runtime" not in names
            assert "business_role_without_entitlement_denied_by_bff" not in names
            assert any("unifai" in n for n in names)
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
            c = sc._UNIFAI_REPLACEMENTS[sc.bff_forwards_identity_to_runtime]()
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
