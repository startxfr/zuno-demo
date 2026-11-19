"""dashboard_coverage: the pure parts of the dashboard coverage pack (ADR-0058, informational).

The stages make live calls; these cases feed the planning and judging functions the shapes the cluster returns, so a
change to the stack config, the tool bindings or a series the dashboards plot is caught here first.

Run from the repository root:
    python3 evaluations/tests/test_dashboard_coverage.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

import yaml

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import dashboard_coverage as d  # noqa: E402

REPO = HERE.parents[2]


def sample(value, **labels):
    return {"metric": labels, "value": [0, str(value)]}


class ToolPlan(unittest.TestCase):
    STACK = {"agents": {
        "tekos": {"tasks": ["answer-technical-question", "write-code"],
                  "toolCapabilities": ["search_confluence", "k8s.resource.list"]},
        "naveo": {"tasks": ["coming-soon"], "toolCapabilities": ["search_confluence"]},
        "kagent": {"tasks": {"diagnose": ["k8s.resource.list"]}, "toolCapabilities": ["k8s.resource.list", "metrics.query"]},
    }}

    def test_pairs_come_from_the_admitted_release(self):
        pairs = d.load_tool_plan(self.STACK, {})
        self.assertEqual([p["agent"] for p in pairs["search_confluence"]], ["tekos", "tekos"])
        self.assertIn({"agent": "kagent", "task": "diagnose"}, pairs["k8s.resource.list"])

    def test_placeholder_tasks_are_never_called(self):
        pairs = d.load_tool_plan(self.STACK, {})
        self.assertNotIn("coming-soon", [p["task"] for p in pairs["search_confluence"]])

    def test_plan_has_denied_and_unknown_calls(self):
        calls = d.build_tool_calls(d.load_tool_plan(self.STACK, {}))
        labels = [c["label"] for c in calls]
        self.assertIn("unknown tool", labels)
        self.assertTrue(any(l.startswith("denied k8s.resource.list") for l in labels))
        self.assertTrue(any(c["tool"] == "k8s.resource.list" and c["task"] != "coverage-probe-no-such-task" for c in calls))

    def test_no_declaring_agent_means_no_read_or_denied_call_for_that_tool(self):
        calls = d.build_tool_calls(d.load_tool_plan({"agents": {}}, {}))
        self.assertEqual([c["label"] for c in calls], ["unknown tool"])

    def test_the_real_stack_config_declares_every_wanted_capability(self):
        stack = yaml.safe_load((REPO / "platform/okf/stack-config.generated.yaml").read_text())
        pairs = d.load_tool_plan(stack, {})
        for cap in ("search_confluence", "k8s.resource.list"):
            self.assertTrue(pairs[cap], f"no admitted agent declares {cap}: the pack would send no read for it")

    def test_summarise_counts_statuses(self):
        self.assertEqual(d.summarise_calls([{"status": 200}, {"status": 403}, {"status": 403}]), {"200": 1, "403": 2})


class Judging(unittest.TestCase):
    def test_all_zero_vector_is_missing(self):
        self.assertEqual(d.judge_vector([sample(0, client="dify")])[0], d.MISSING)
        self.assertEqual(d.judge_vector([])[0], d.MISSING)

    def test_positive_vector_passes(self):
        status, detail = d.judge_vector([sample(3, client="dify"), sample(1, client="kagent")])
        self.assertEqual(status, d.OK)
        self.assertIn("2 series", detail)

    def test_label_requirement_names_the_missing_values(self):
        vec = [sample(3, client="dify"), sample(1, client="kagent")]
        status, detail = d.judge_vector(vec, d.need_labels("client", ("dify", "open-webui", "openclaw")))
        self.assertEqual(status, d.MISSING)
        self.assertIn("open-webui", detail)
        self.assertIn("openclaw", detail)
        self.assertNotIn("missing: dify", detail)

    def test_label_requirement_met(self):
        vec = [sample(1, rag_outcome="error"), sample(4, rag_outcome="success")]
        self.assertEqual(d.judge_vector(vec, d.need_labels("rag_outcome", ("error",)))[0], d.OK)

    def test_quota_judgement(self):
        self.assertEqual(d.judge_quota(17, [200] * 16 + [429])[0], d.OK)
        self.assertEqual(d.judge_quota(None, [502, 502])[0], d.MISSING)
        self.assertIn("models are down", d.judge_quota(None, [502, 502])[1])
        self.assertEqual(d.judge_quota(None, [200, 200])[0], d.MISSING)

    def test_unparsable_sample_counts_as_zero(self):
        self.assertEqual(d.judge_vector([{"metric": {}, "value": []}])[0], d.MISSING)


class Queries(unittest.TestCase):
    def test_every_query_names_a_metric_a_dashboard_plots(self):
        dashboards = "".join(p.read_text() for p in (REPO / "gitops/charts/grafana/templates").glob("dashboard-*.yaml"))
        for family, check, expr, _ in d.coverage_queries("2h"):
            metric = next(m for m in ("zuno_model_calls_total", "zuno_model_tokens_total", "zuno_model_cost_usd_total",
                                      "zuno_semantic_cache_lookups_total", "zuno_tool_invocations_total",
                                      "rag_search_duration_seconds_count", "zuno_guardrails_evaluations_total",
                                      "zuno_guardrails_detections_total", "limited_calls") if m in expr)
            self.assertIn(metric, dashboards, f"{family} / {check}: no dashboard plots {metric}")

    def test_window_is_applied(self):
        self.assertTrue(all("[3h]" in expr for _, _, expr, _ in d.coverage_queries("3h")))


class PraxisCall(unittest.TestCase):
    """Praxis admits experience-client namespaces only (ADR-0619): the call must not leave the ai-gateway pod."""

    def run_models(self):
        import subprocess
        import golden_path_probe as g

        calls = []

        def fake_oc(*args, stdin=None, timeout=120):
            calls.append({"args": args, "stdin": stdin})
            out = '{"status": 200, "note": "ok", "calls": [{"label": "x", "status": 200, "note": "ok"}]}'
            return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

        class FakeCtx:
            def gateway_token(self):
                return "gw-token"

            def persona_token(self, username):
                self.persona = username
                return "persona-token"

        original = g.oc
        g.oc = fake_oc
        try:
            ctx = FakeCtx()
            rows = d.stage_models(ctx)
        finally:
            g.oc = original
        return ctx, rows, calls

    def test_praxis_is_called_from_the_dify_token_proxy_pod_with_a_stress_persona(self):
        ctx, rows, calls = self.run_models()
        praxis = [c for c in calls if "zuno-token-proxy" in " ".join(c["args"]) and "exec" in c["args"]]
        self.assertEqual(len(praxis), 1)
        self.assertIn("zuno-dify", praxis[0]["args"])
        self.assertNotIn("-c", praxis[0]["args"][: praxis[0]["args"].index("--")])  # no container flag: python's own -c follows
        self.assertEqual(praxis[0]["stdin"], "persona-token\n")
        self.assertTrue(ctx.persona.startswith("stress-"), ctx.persona)
        self.assertEqual([r.status for r in rows if "praxis" in r.check], [d.OK])

    def test_no_secret_is_on_a_command_line_and_the_ai_gateway_pod_never_calls_praxis(self):
        _, _, calls = self.run_models()
        for c in calls:
            self.assertNotIn("persona-token", " ".join(c["args"]))
            self.assertNotIn("gw-token", " ".join(c["args"]))
            if "deploy/ai-gateway" in c["args"]:
                self.assertNotIn("praxis", " ".join(c["args"]))
        self.assertNotIn("praxis.zuno-ai-gateways", d._MODEL_SNIPPET)


class Output(unittest.TestCase):
    def test_render_counts_gaps_and_stays_informational(self):
        text = d.render([d.Row("tools", "denied", d.MISSING, "x"), d.Row("tools", "allowed", d.OK, "y")])
        self.assertIn("1 family check(s) MISSING of 2 row(s)", text)
        self.assertIn("exit code stays 0", text)

    def test_no_cluster_login_exits_zero(self):
        import golden_path_probe as g

        original = g.Context
        g.Context = lambda: (_ for _ in ()).throw(RuntimeError("not logged in"))
        try:
            self.assertEqual(d.main(["--only", "tools"]), 0)
        finally:
            g.Context = original


if __name__ == "__main__":
    unittest.main()
