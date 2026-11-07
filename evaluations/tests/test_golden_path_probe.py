"""golden_path_probe: the judgement of each moment (ADR-0605 clause 1, WP-238).

The probes themselves make live calls; these cases feed the pure judgement functions the shapes the live calls
return, so a change in the gateway's routing decision or a proxy's answer is caught here first.

Run from the repository root:
    python3 evaluations/tests/test_golden_path_probe.py
"""
from __future__ import annotations

import pathlib
import sys
import json
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import golden_path_probe as g  # noqa: E402


def call(agent, status=200, kind="local", classification="C3", provider="local-gptoss"):
    return {"agent": agent, "status": status,
            "routing": {"provider": provider, "model": "m", "kind": kind, "classification": classification}}


class Sovereignty(unittest.TestCase):
    def test_arkos_local_at_c3_passes(self):
        r = g.judge_sovereignty([call("arkos"), call("tekos", kind="saas", classification="C1", provider="mistral")])
        self.assertEqual(r.status, g.PASS)
        self.assertIn("raised to C3", r.detail)

    def test_arkos_sent_to_saas_fails(self):
        r = g.judge_sovereignty([call("arkos", kind="saas"), call("tekos")])
        self.assertEqual(r.status, g.FAIL)

    def test_arkos_left_at_c1_fails(self):
        r = g.judge_sovereignty([call("arkos", classification="C1"), call("tekos")])
        self.assertEqual(r.status, g.FAIL)

    def test_no_routing_decision_fails(self):
        r = g.judge_sovereignty([{"agent": "arkos", "status": 200, "routing": None}, call("tekos")])
        self.assertEqual(r.status, g.FAIL)

    def test_failed_control_call_fails(self):
        r = g.judge_sovereignty([call("arkos"), {"agent": "tekos", "status": 503}])
        self.assertEqual(r.status, g.FAIL)


class Proxy(unittest.TestCase):
    def test_answer_passes(self):
        self.assertEqual(g.judge_proxy("dify", {"status": 200, "chars": 42, "model": "auto"}).status, g.PASS)

    def test_empty_answer_fails(self):
        self.assertEqual(g.judge_proxy("dify", {"status": 200, "chars": 0}).status, g.FAIL)

    def test_quota_refusal_fails(self):
        r = g.judge_proxy("kagent", {"status": 429, "error": "quota"})
        self.assertEqual(r.status, g.FAIL)
        self.assertIn("429", r.detail)

    def test_no_output_fails(self):
        self.assertEqual(g.judge_proxy("dify", {}, "exec failed").status, g.FAIL)


class Models(unittest.TestCase):
    def test_pick_default_and_code(self):
        ids = ["zuno-code", "auto"]
        self.assertEqual(g.pick_model(ids, "chat"), "auto")
        self.assertEqual(g.pick_model(ids, "code"), "zuno-code")

    def test_prefixed_ids(self):
        ids = ["zuno.auto", "zuno.zuno-code"]
        self.assertEqual(g.pick_model(ids, "chat"), "zuno.auto")
        self.assertEqual(g.pick_model(ids, "code"), "zuno.zuno-code")

    def test_missing_code_model(self):
        self.assertIsNone(g.pick_model(["auto"], "code"))


class Lightspeed(unittest.TestCase):
    def test_unused_features_do_not_fail(self):
        conds = [{"type": "ApiReady", "status": "True"}, {"type": "ConsolePluginReady", "status": "True"},
                 {"type": "AlertsAdapterReady", "status": "False"}]
        r = g.judge_lightspeed(conds)
        self.assertEqual(r.status, g.PASS)
        self.assertIn("AlertsAdapterReady", r.detail)

    def test_answer(self):
        self.assertEqual(g.judge_lightspeed_answer(200, {"response": "A Pod is ...", "output_tokens": 40}).status, g.PASS)
        self.assertEqual(g.judge_lightspeed_answer(200, {"response": ""}).status, g.FAIL)
        self.assertEqual(g.judge_lightspeed_answer(401, {"detail": "unauthorized"}).status, g.FAIL)


class OpenClaw(unittest.TestCase):
    def test_answer_through_the_proxy(self):
        ok = '{"model": "qwen", "choices": [{"message": {"content": "OK"}}]}\nhttp=200\n'
        self.assertIsNone(g.judge_openclaw_call("zuno-claw-sale-01", ok))

    def test_refusals(self):
        self.assertIn("HTTP 401", g.judge_openclaw_call("ns", '{"detail":"no token"}\nhttp=401\n'))
        self.assertIn("empty answer", g.judge_openclaw_call("ns", '{"choices": [{"message": {"content": ""}}]}\nhttp=200\n'))
        self.assertIn("no JSON", g.judge_openclaw_call("ns", "<html>\nhttp=200\n"))
        self.assertIn("HTTP ?", g.judge_openclaw_call("ns", ""))

    def test_api_not_ready_fails(self):
        r = g.judge_lightspeed([{"type": "ApiReady", "status": "False"}, {"type": "ConsolePluginReady", "status": "True"}])
        self.assertEqual(r.status, g.FAIL)


A2A_200 = '10.0.0.1 - - "POST /agents/tekos/ HTTP/1.1" 200 -\n'
A2A_404 = '10.0.0.1 - - "POST /agents/tekos/ HTTP/1.1" 404 -\n'


class Delegation(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "platform" / "testing"))

    def test_served_call_to_tekos_passes(self):
        r = g.judge_delegation(A2A_404 + A2A_200)
        self.assertEqual(r.status, g.PASS)
        self.assertIn("served 1 call", r.detail)

    def test_no_served_call_fails(self):
        self.assertEqual(g.judge_delegation(A2A_404).status, g.FAIL)
        self.assertEqual(g.judge_delegation("").status, g.FAIL)


class Tools(unittest.TestCase):
    def test_pages_pass(self):
        r = g.judge_tool({"status": 200, "server": "confluence", "ms": 472.5, "results": 5})
        self.assertEqual(r.status, g.PASS)
        self.assertIn("5 page(s)", r.detail)

    def test_empty_or_refused_fail(self):
        self.assertEqual(g.judge_tool({"status": 200, "server": "confluence", "results": 0}).status, g.FAIL)
        self.assertEqual(g.judge_tool({"status": 403, "error": "denied"}).status, g.FAIL)


class GuardrailsAndTrace(unittest.TestCase):
    def test_detection_line_for_dify_passes(self):
        log = ("INFO ai_gateway.guardrails guardrails clean (mode=observe): run_id= agent=open-webui contents=2\n"
               "WARNING ai_gateway.guardrails guardrails DETECTED (mode=observe): run_id= agent=dify detections=['x']\n")
        r = g.judge_guardrails(log)
        self.assertEqual(r.status, g.PASS)
        self.assertIn("mode=observe", r.detail)

    def test_detection_for_another_client_does_not_count(self):
        log = "guardrails DETECTED (mode=observe): run_id= agent=open-webui detections=['x']\n"
        self.assertEqual(g.judge_guardrails(log).status, g.FAIL)

    def test_trace(self):
        self.assertEqual(g.judge_trace("", []).status, g.FAIL)
        r = g.judge_trace("0" * 32, [{"name": "ai-gateway chat"}, {"name": "rag.search"}])
        self.assertEqual(r.status, g.PASS)
        self.assertIn("2 span(s)", r.detail)


class WorldModel(unittest.TestCase):
    OK = {"runtime_ready": True, "engine": "waypoint-1.5-1b", "encoder": "nvenc", "create_status": 201, "frames": 30,
          "first_keyframe": True, "edit_status": 202, "edit_result": "applied", "edit_ms": 1800, "released": True}

    def with_(self, **kw):
        return g.judge_world({**self.OK, **kw})

    def test_a_full_run_passes_and_says_what_ran(self):
        r = g.judge_world(self.OK)
        self.assertEqual(r.status, g.PASS)
        self.assertIn("waypoint-1.5-1b, nvenc", r.detail)
        self.assertIn("1.8 s", r.detail)

    def test_every_broken_link_fails(self):
        for kw, text in (
            ({"runtime_ready": False}, "not ready"),
            ({"create_status": 409}, "another world"),
            ({"create_status": 503}, "refused"),
            ({"released": False}, "released"),
            ({"frames": 3}, "only 3"),
            ({"first_keyframe": False}, "keyframe"),
            ({"edit_status": 422}, "HTTP 422"),
            ({"edit_result": "failed"}, "failed"),
            ({"edit_result": None}, "without an answer"),
        ):
            with self.subTest(kw=kw):
                r = self.with_(**kw)
                self.assertEqual(r.status, g.FAIL)
                self.assertIn(text, r.detail)

    def test_nothing_printed_fails(self):
        self.assertEqual(g.judge_world({}).status, g.FAIL)

    def probe_with(self, fake):
        saved = g.oc
        g.oc = fake
        try:
            return g.probe_world_model(types.SimpleNamespace(persona_token=lambda u: "t"))
        finally:
            g.oc = saved

    def test_positively_absent_is_roadmap_and_it_asks_argo_by_its_full_name(self):
        calls = []

        def fake(*args, **kw):
            calls.append(args)
            return types.SimpleNamespace(returncode=1, stdout="", stderr='Error from server (NotFound): applications.argoproj.io "x" not found')

        r = self.probe_with(fake)
        self.assertEqual((r.status, r.required), (g.ROADMAP, False))
        self.assertIn("not installed", r.detail)
        self.assertIn("applications.argoproj.io", calls[0])
        self.assertNotIn("application", calls[0])

    def test_a_lookup_that_cannot_be_confirmed_is_roadmap_never_a_required_failure(self):
        import subprocess

        def timeout(*args, **kw):
            raise subprocess.TimeoutExpired("oc", 120)

        def unreachable(*args, **kw):
            return types.SimpleNamespace(returncode=1, stdout="", stderr="Unable to connect to the server: dial tcp: i/o timeout")

        def silent(*args, **kw):
            return types.SimpleNamespace(returncode=1, stdout="", stderr="")

        for name, fake in (("timeout", timeout), ("unreachable", unreachable), ("silent", silent)):
            with self.subTest(name):
                r = self.probe_with(fake)
                self.assertEqual((r.status, r.required), (g.ROADMAP, False))
                self.assertIn("could not look the Application up", r.detail)
        # and through run_one, which turns any exception into FAIL: the verdict must still not be required
        saved = g.PROBES["world-model"]
        g.PROBES["world-model"] = lambda ctx: self.probe_with(timeout)
        try:
            self.assertFalse(g.run_one("world-model", None).required)
        finally:
            g.PROBES["world-model"] = saved

    def test_positively_found_runs_the_probe_and_is_then_required(self):
        calls = []
        summary = dict(self.OK)

        def fake(*args, **kw):
            calls.append(args)
            if args[0] == "get":
                return types.SimpleNamespace(returncode=0, stdout="application.argoproj.io/zuno-world-model-d1\n", stderr="")
            return types.SimpleNamespace(returncode=0, stdout=json.dumps(summary) + "\n", stderr="")

        self.assertEqual(self.probe_with(fake).status, g.PASS)
        self.assertEqual(calls[1][0], "exec")
        summary["frames"] = 2
        r = self.probe_with(fake)
        self.assertEqual(r.status, g.FAIL)
        saved = g.PROBES["world-model"]
        g.PROBES["world-model"] = lambda ctx: r
        try:
            self.assertTrue(g.run_one("world-model", None).required)
        finally:
            g.PROBES["world-model"] = saved

    def test_a_held_gpu_is_never_called_a_pass(self):
        self.assertEqual(self.with_(released=False, frames=40).status, g.FAIL)

    def test_the_in_pod_script_is_valid_python_and_takes_its_config_from_one_place(self):
        script = g.WORLD_PROBE_SCRIPT.replace("__CFG__", json.dumps({"base": "http://x", "token": "t", "frames": 1,
                                                                    "edit": "e", "seconds": 1}))
        compile(script, "world_probe", "exec")
        self.assertEqual(g.WORLD_PROBE_SCRIPT.count("__CFG__"), 1)
        self.assertNotIn("print(token", g.WORLD_PROBE_SCRIPT)


class Aggregate(unittest.TestCase):
    def test_last_json_line(self):
        self.assertEqual(g.last_json_line("noise\n{\"a\": 1}\ntrailing"), {"a": 1})
        self.assertEqual(g.last_json_line("no json here"), {})

    def test_optional_failures_do_not_fail_the_run(self):
        results = [g.Result("dify", g.PASS, ""), g.Result("lightspeed", g.MANUAL, "", required=False),
                   g.Result("world-model", g.ROADMAP, "", required=False)]
        self.assertEqual(g.exit_code(results), 0)

    def test_the_world_model_row_becomes_required_once_it_has_a_verdict(self):
        for status, required in ((g.ROADMAP, False), (g.PASS, True), (g.FAIL, True)):
            g.PROBES["world-model"], saved = (lambda ctx, s=status: g.Result("world-model", s, "")), g.PROBES["world-model"]
            try:
                self.assertEqual(g.run_one("world-model", None).required, required, status)
            finally:
                g.PROBES["world-model"] = saved

    def test_a_required_failure_fails_the_run(self):
        results = [g.Result("dify", g.FAIL, ""), g.Result("world-model", g.ROADMAP, "", required=False)]
        self.assertEqual(g.exit_code(results), 1)
        self.assertIn("FAIL (dify)", g.render(results))

    def test_every_moment_has_a_probe(self):
        self.assertEqual(set(g.PROBES), {"unifai-tekos", "sovereignty", "open-webui", "zuno-code", "dify", "kagent",
                                         "openclaw", "lightspeed", "tools", "guardrails", "trace", "delegation-approval",
                                         "world-model", "blender"})
        self.assertLess(list(g.PROBES).index("unifai-tekos"), list(g.PROBES).index("trace"))


class Blender(unittest.TestCase):
    """ADR-0610 clause 9 (WP-245): the Blender workstation moment."""

    OK = {"persona": "eval-ai-dev-01", "no_token": 401, "unrouted": 404, "login": "ok", "models": 200,
          "generation": 200, "generation_seconds": 8.2, "lines": 50, "problems": [], "floor_logged": True,
          "gpt_oss_called": True, "revoked": True}

    def judge(self, **kw):
        return g.judge_blender({**self.OK, **kw})

    def test_a_full_run_passes_and_says_what_ran(self):
        r = g.judge_blender(self.OK)
        self.assertEqual(r.status, g.PASS)
        self.assertIn("C3 floor", r.detail)
        self.assertNotIn("not revoked", r.detail)

    def test_every_broken_link_fails(self):
        for kw, why in (({"no_token": 200}, "without a token"), ({"unrouted": 200}, "unrouted"),
                        ({"login": "the token endpoint answered access_denied"}, "device sign-in"),
                        ({"models": 403}, "/v1/models"), ({"generation": 0, "generation_error": "ReadTimeout"},
                                                           "generation"),
                        ({"problems": ["line 1: import os"]}, "static check"),
                        ({"floor_logged": False}, "floor"), ({"gpt_oss_called": False}, "gpt-oss-20b")):
            with self.subTest(why):
                r = self.judge(**kw)
                self.assertEqual(r.status, g.FAIL)
                self.assertIn(why, r.detail)

    def test_a_persona_not_created_yet_is_named_and_never_fails(self):
        r = self.judge(login="persona")
        self.assertEqual(r.status, g.SKIPPED)
        self.assertIn("eval-ai-dev-01", r.detail)
        saved = g.PROBES["blender"]
        g.PROBES["blender"] = lambda ctx: r
        try:
            self.assertFalse(g.run_one("blender", None).required)
        finally:
            g.PROBES["blender"] = saved

    def test_the_edge_is_checked_before_any_sign_in(self):
        self.assertEqual(self.judge(no_token=502, login="persona").status, g.FAIL)

    def probe_with(self, fake):
        saved = g.oc
        g.oc = fake
        try:
            return g.probe_blender(types.SimpleNamespace(domain="apps.example.com", password="x"))
        finally:
            g.oc = saved

    def test_positively_absent_entry_is_roadmap_and_it_asks_for_the_httproute(self):
        calls = []

        def fake(*args, **kw):
            calls.append(args)
            return types.SimpleNamespace(returncode=1, stdout="",
                                         stderr='Error from server (NotFound): httproutes "ai-gateway-workstation" not found')

        r = self.probe_with(fake)
        self.assertEqual((r.status, r.required), (g.ROADMAP, False))
        self.assertIn("httproutes.gateway.networking.k8s.io", calls[0])

    def test_an_unconfirmable_lookup_is_skipped_never_a_required_failure(self):
        import subprocess

        def timeout(*args, **kw):
            raise subprocess.TimeoutExpired("oc", 120)

        def unreachable(*args, **kw):
            return types.SimpleNamespace(returncode=1, stdout="", stderr="Unable to connect to the server")

        for name, fake in (("timeout", timeout), ("unreachable", unreachable)):
            with self.subTest(name):
                r = self.probe_with(fake)
                self.assertEqual(r.status, g.SKIPPED)
                saved = g.PROBES["blender"]
                g.PROBES["blender"] = lambda ctx, r=r: r
                try:
                    self.assertFalse(g.run_one("blender", None).required)
                finally:
                    g.PROBES["blender"] = saved

    def test_an_installed_entry_that_fails_is_required(self):
        saved = g.PROBES["blender"]
        g.PROBES["blender"] = lambda ctx: g.Result("blender", g.FAIL, "x")
        try:
            self.assertTrue(g.run_one("blender", None).required)
        finally:
            g.PROBES["blender"] = saved


if __name__ == "__main__":
    unittest.main()
