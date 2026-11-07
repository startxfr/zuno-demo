"""golden_path_probe: the judgement of each moment (ADR-0605 clause 1, WP-238).

The probes themselves make live calls; these cases feed the pure judgement functions the shapes the live calls
return, so a change in the gateway's routing decision or a proxy's answer is caught here first.

Run from the repository root:
    python3 evaluations/tests/test_golden_path_probe.py
"""
from __future__ import annotations

import pathlib
import sys
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
        self.assertEqual(r.status, g.MANUAL)
        self.assertIn("AlertsAdapterReady", r.detail)

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


class Aggregate(unittest.TestCase):
    def test_last_json_line(self):
        self.assertEqual(g.last_json_line("noise\n{\"a\": 1}\ntrailing"), {"a": 1})
        self.assertEqual(g.last_json_line("no json here"), {})

    def test_optional_failures_do_not_fail_the_run(self):
        results = [g.Result("dify", g.PASS, ""), g.Result("openclaw", g.FAIL, "", required=False),
                   g.Result("world-model", g.ROADMAP, "", required=False)]
        self.assertEqual(g.exit_code(results), 0)

    def test_a_required_failure_fails_the_run(self):
        results = [g.Result("dify", g.FAIL, ""), g.Result("world-model", g.ROADMAP, "", required=False)]
        self.assertEqual(g.exit_code(results), 1)
        self.assertIn("FAIL (dify)", g.render(results))

    def test_every_moment_has_a_probe(self):
        self.assertEqual(set(g.PROBES), {"unifai-tekos", "sovereignty", "open-webui", "zuno-code", "dify", "kagent",
                                         "openclaw", "lightspeed", "delegation-approval", "world-model"})


if __name__ == "__main__":
    unittest.main()
