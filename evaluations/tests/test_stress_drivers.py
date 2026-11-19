"""The experience, UnifAI and network drivers of the stress runner (WP-308, ADR-0624), offline.

HTTP goes through httpx.MockTransport; the blocking helpers that talk to UnifAI, Keycloak, Open WebUI, Tempo and the device
flow are replaced by fakes, so what is tested is each driver's request, its verdict and its row shape.

Run from the repository root:
    python3 evaluations/tests/test_stress_drivers.py
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import httpx
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
STRESS_DIR = REPO / "evaluations" / "stress"
sys.path.insert(0, str(REPO / "platform" / "testing"))
sys.path.insert(0, str(REPO / "evaluations"))

import stress_runner as sr  # noqa: E402

sr.load_drivers(STRESS_DIR)

import driver_experiences as exp  # noqa: E402
import driver_network as net  # noqa: E402
import driver_unifai as uni  # noqa: E402

ENV = {"KEYCLOAK_URL": "https://kc", "DEMO_PERSONA_PASSWORD": "pw", "CLUSTER_BASE_DOMAIN": "apps.test"}


def ctx_with(handler, env=None):
    def route(request):
        if "openid-connect/token" in request.url.path:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
        return handler(request)

    merged = dict(ENV, **(env or {}))
    return sr.Ctx(env=merged, run_id="t", client=httpx.AsyncClient(transport=httpx.MockTransport(route)), personas=["stress-load-01"])


def one(driver_id, ctx, i=0):
    return asyncio.run(sr.REGISTRY[driver_id].run(ctx.for_worker(0), i))


def run_of(status=200, reply="Hello from Tekos", session="sid-1", routing=None):
    return SimpleNamespace(status=status, reply=reply, session_id=session, seconds=1.0, raw={"routing": routing} if routing else {})


class Registry(unittest.TestCase):
    NEW = ("unifai-agents", "observability-trace", "guardrails", "open-webui", "open-webui-zuno-code", "open-webui-zuno-wesh",
           "dify", "kagent", "blender-3d", "claude-code-sovereign", "quotas")

    def test_every_new_driver_is_registered_under_a_demo_id_with_a_family_and_needs(self):
        for driver_id in self.NEW:
            d = sr.REGISTRY[driver_id]
            demo = driver_id.replace("-zuno-code", "").replace("-zuno-wesh", "")
            self.assertTrue((REPO / "ansible" / "demos" / demo / "demo.yml").is_file(), driver_id)
            self.assertTrue(d.family and d.needs and d.description, driver_id)

    def test_only_quotas_changes_cluster_state_and_the_default_profiles_skip_it(self):
        self.assertEqual([d.id for d in sr.REGISTRY.values() if d.mutating], ["quotas"])
        for name in ("smoke", "standard", "aggressive", "soak"):
            plans, warnings = sr.build_plan(sr.load_profile(name, STRESS_DIR), {}, sr.REGISTRY)
            self.assertNotIn("quotas", [p.driver.id for p in plans], name)

    def test_smoke_needs_no_network_opening_and_standard_throttles_the_real_user_paths(self):
        smoke = {p.driver.family for p in sr.build_plan(sr.load_profile("smoke", STRESS_DIR), {}, sr.REGISTRY)[0]}
        self.assertNotIn("experiences", smoke)
        self.assertTrue({"unifai", "guardrails", "tools", "models"} <= smoke)
        for name in ("standard", "aggressive"):
            plans = sr.build_plan(sr.load_profile(name, STRESS_DIR), {}, sr.REGISTRY)[0]
            experiences = [p for p in plans if p.driver.family == "experiences"]
            self.assertEqual(len(experiences), 7, name)
            for p in experiences:
                self.assertEqual(p.concurrency, 1, (name, p.driver.id))
                self.assertGreaterEqual(p.timeout, 240, (name, p.driver.id))

    def test_the_campaign_job_ships_the_helpers_the_drivers_import(self):
        launch = (REPO / "ansible/roles/day3/tasks/stresstest_campaign_launch.yml").read_text()
        for helper in ("unifai_target.py", "device_login.py"):
            self.assertIn(f"'{helper}'", launch)
        self.assertTrue((REPO / "evaluations/common/unifai_target.py").is_file())
        self.assertTrue((REPO / "evaluations/blender/device_login.py").is_file())
        for env in ("UNIFAI_URL", "UNIFAI_VERIFY_TLS", "CLUSTER_BASE_DOMAIN"):
            self.assertIn(f"name: {env}", launch)


class UnifaiDrivers(unittest.TestCase):
    def test_unifai_agents_passes_on_a_reply_and_names_the_serving_model(self):
        run = run_of(routing={"provider": "local-maas", "model": "qwen3.6"})
        with mock.patch.object(uni, "_turn", return_value=run) as turn:
            rows = one("unifai-agents", ctx_with(lambda r: httpx.Response(500)))
        self.assertTrue(rows[0].passed, rows[0].detail)
        self.assertIn("via local-maas/qwen3.6", rows[0].detail)
        self.assertEqual(turn.call_args[0][1], "stress-load-01")  # the worker's own persona signs in

    def test_unifai_agents_fails_without_a_reply_or_on_an_error_status(self):
        for run in (run_of(reply="  "), run_of(status=599, reply="")):
            with mock.patch.object(uni, "_turn", return_value=run):
                rows = one("unifai-agents", ctx_with(lambda r: httpx.Response(500)))
            self.assertFalse(rows[0].passed)
            self.assertEqual(sr.row_status(rows[0]), run.status)

    def test_observability_trace_needs_the_turn_and_a_trace(self):
        ctx = ctx_with(lambda r: httpx.Response(500), {"TEMPO_URL": "http://tempo:3200/"})
        with mock.patch.object(uni, "_turn", return_value=run_of()), mock.patch.object(
                uni.ut, "tempo_run_trace", return_value=("a" * 32, [{"name": "chat qwen"}, {"name": "model_call"}])) as tempo:
            rows = one("observability-trace", ctx)
        self.assertEqual([r.passed for r in rows], [True, True])
        self.assertEqual(tempo.call_args[0][:2], ("sid-1", "http://tempo:3200"))
        with mock.patch.object(uni, "_turn", return_value=run_of()), mock.patch.object(uni.ut, "tempo_run_trace", return_value=("", [])):
            rows = one("observability-trace", ctx)
        self.assertEqual([r.passed for r in rows], [True, False])
        with mock.patch.object(uni, "_turn", return_value=run_of(status=500, reply="")), mock.patch.object(uni.ut, "tempo_run_trace") as tempo:
            rows = one("observability-trace", ctx)
        self.assertEqual(len(rows), 1)
        tempo.assert_not_called()

    def test_span_attributes_reads_otlp_json(self):
        trace = {"batches": [{"scopeSpans": [{"spans": [
            {"name": "other", "attributes": []},
            {"name": "guardrails_observe", "attributes": [
                {"key": "zuno.outcome", "value": {"stringValue": "detected"}}, {"key": "zuno.detection_count", "value": {"intValue": "2"}}]}]}]}]}
        self.assertEqual(uni.span_attributes(trace, "guardrails_observe"), {"zuno.outcome": "detected", "zuno.detection_count": "2"})
        self.assertEqual(uni.span_attributes(trace, "absent"), {})

    def test_guardrails_outcome_polls_tempo_until_the_span_appears(self):
        trace = {"batches": [{"scopeSpans": [{"spans": [{"name": "guardrails_observe", "attributes": [{"key": "zuno.outcome", "value": {"stringValue": "detected"}}]}]}]}]}
        answers = [{"traces": []}, {"traces": [{"traceID": "t1"}]}]
        seen = []

        class Http:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, params=None):
                seen.append((url, params))
                if url.endswith("/api/search"):
                    return SimpleNamespace(status_code=200, json=lambda: answers.pop(0))
                return SimpleNamespace(status_code=200, json=lambda: trace)

        with mock.patch("httpx.Client", return_value=Http()), mock.patch.object(uni.time, "sleep"):
            self.assertEqual(uni.guardrails_outcome("http://tempo", "st-t-guardrails-0", wait_seconds=5), "detected")
        self.assertIn('span.zuno.run_id="st-t-guardrails-0"', seen[0][1]["q"])
        self.assertIn('name="guardrails_observe"', seen[0][1]["q"])

    def test_judging_the_outcome(self):
        self.assertTrue(uni.judge_guardrails_outcome("detected")[0])
        self.assertFalse(uni.judge_guardrails_outcome("clean")[0])
        self.assertFalse(uni.judge_guardrails_outcome("")[0])
        self.assertIn("did not run", uni.judge_guardrails_outcome("")[1])

    def guardrails(self, status=200, outcome="detected"):
        seen = {}

        def handler(request):
            seen["headers"] = dict(request.headers)
            seen["body"] = request.content.decode()
            return httpx.Response(status, json={"usage": {"total_tokens": 18}, "choices": []})

        ctx = ctx_with(handler)
        with mock.patch.object(uni, "guardrails_outcome", return_value=outcome):
            rows = one("guardrails", ctx)
        return rows, seen, ctx

    def test_guardrails_sends_the_dan_prompt_with_its_run_id_and_reads_the_span(self):
        rows, seen, ctx = self.guardrails()
        self.assertTrue(rows[0].passed, rows[0].detail)
        self.assertEqual(seen["headers"]["x-zuno-run-id"], "st-t-guardrails-0")
        self.assertEqual(seen["headers"]["x-zuno-quota-class"], "stresstest")
        self.assertIn("DAN", seen["body"])
        self.assertEqual(ctx.tokens_used, 18)

    def test_guardrails_fails_on_a_miss_and_on_a_server_error(self):
        self.assertFalse(self.guardrails(outcome="clean")[0][0].passed)
        rows, _, _ = self.guardrails(status=429)
        self.assertFalse(rows[0].passed)
        self.assertEqual(sr.row_status(rows[0]), 429)
        self.assertTrue(self.guardrails(status=403)[0][0].passed)  # block mode refuses an evaluated prompt


class ExperienceDrivers(unittest.TestCase):
    def setUp(self):
        exp._TOKENS.clear()

    def test_open_webui_signs_in_once_and_answers(self):
        calls = {"login": 0}

        def login(base, username, password):
            calls["login"] += 1
            assert base == "https://open-webui.apps.test" and username == "stress-load-01" and password == "pw"
            return "owui-token"

        ctx = ctx_with(lambda r: httpx.Response(500))
        with mock.patch.object(exp, "owui_login", side_effect=login), mock.patch.object(
                exp, "owui_chat", return_value=(200, "auto", "Hi there", "qwen", ["auto"])) as chat:
            first, second = one("open-webui", ctx), one("open-webui", ctx, 1)
        self.assertTrue(first[0].passed and second[0].passed, first[0].detail)
        self.assertEqual(calls["login"], 1)
        self.assertEqual(chat.call_args[0][1:3], ("owui-token", "chat"))

    def test_the_code_and_wesh_variants_ask_for_their_model(self):
        ctx = ctx_with(lambda r: httpx.Response(500))
        with mock.patch.object(exp, "owui_login", return_value="t"), mock.patch.object(
                exp, "owui_chat", return_value=(200, "zuno-code", "x = 1", "codestral", [])) as chat:
            self.assertTrue(one("open-webui-zuno-code", ctx)[0].passed)
            self.assertEqual(chat.call_args[0][2], "code")
        with mock.patch.object(exp, "owui_login", return_value="t"), mock.patch.object(
                exp, "owui_chat", return_value=(200, "", "", "", ["auto"])) as chat:
            rows = one("open-webui-zuno-wesh", ctx)
            self.assertEqual(chat.call_args[0][2], "wesh")
        self.assertFalse(rows[0].passed)
        self.assertIn("no zuno-wesh model", rows[0].detail)

    def test_a_401_drops_the_cached_session(self):
        ctx = ctx_with(lambda r: httpx.Response(500))
        with mock.patch.object(exp, "owui_login", return_value="t"), mock.patch.object(exp, "owui_chat", return_value=(401, "auto", "", "", ["auto"])):
            rows = one("open-webui", ctx)
        self.assertFalse(rows[0].passed)
        self.assertEqual(sr.row_status(rows[0]), 401)
        self.assertNotIn("stress-load-01", exp._TOKENS)

    def test_judge_owui(self):
        self.assertTrue(exp.judge_owui("open-webui", "chat", 200, "auto", "ok", "q", [])[0])
        self.assertFalse(exp.judge_owui("open-webui", "chat", 200, "auto", " ", "q", [])[0])
        self.assertFalse(exp.judge_owui("open-webui", "code", 200, "", "", "", ["auto"])[0])

    def proxy(self, driver, handler, env=None):
        return one(driver, ctx_with(handler, env))

    def test_dify_and_kagent_call_their_own_namespace_proxy(self):
        seen = []

        def handler(request):
            seen.append((str(request.url), request.headers["authorization"]))
            return httpx.Response(200, json={"model": "qwen", "choices": [{"message": {"content": "OK"}}], "usage": {"total_tokens": 9}})

        for driver, namespace in (("dify", "zuno-dify"), ("kagent", "zuno-kagent")):
            rows = self.proxy(driver, handler)
            self.assertTrue(rows[0].passed, rows[0].detail)
            self.assertEqual(seen[-1][0], f"http://zuno-token-proxy.{namespace}.svc:8080/v1/chat/completions")
            self.assertEqual(seen[-1][1], "Bearer placeholder")

    def test_the_proxy_url_and_inbound_key_can_be_set(self):
        seen = []
        handler = lambda r: (seen.append((str(r.url), r.headers["authorization"])), httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]}))[1]
        self.proxy("dify", handler, {"DIFY_PROXY_URL": "http://proxy.example:9000/", "DIFY_PROXY_URL_KEY": "k-123"})
        self.assertEqual(seen[0], ("http://proxy.example:9000/v1/chat/completions", "Bearer k-123"))

    def test_a_proxy_refusal_is_a_failing_row_with_its_status(self):
        rows = self.proxy("kagent", lambda r: httpx.Response(403, text="denied"))
        self.assertFalse(rows[0].passed)
        self.assertEqual(sr.row_status(rows[0]), 403)


class NetworkDrivers(unittest.TestCase):
    def setUp(self):
        net._DEVICE_TOKENS.clear()

    def test_blender_replays_the_device_sign_in_then_models_and_chat(self):
        seen = []

        def handler(request):
            seen.append((request.method, str(request.url)))
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"data": []})
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}], "usage": {"total_tokens": 11}})

        ctx = ctx_with(handler)
        with mock.patch.object(net, "device_access_token", return_value="dev-token") as device:
            rows = one("blender-3d", ctx)
        self.assertTrue(rows[0].passed, rows[0].detail)
        self.assertEqual(device.call_args[0], ("https://kc/realms/zuno", "stress-load-01", "pw", "blender"))
        self.assertEqual(seen, [("GET", "https://ai-gateway.apps.test/v1/models"), ("POST", "https://ai-gateway.apps.test/v1/chat/completions")])
        self.assertEqual(ctx.tokens_used, 11)

    def test_blender_is_skipped_not_failed_while_the_entry_is_off(self):
        with mock.patch.object(net, "device_access_token", return_value="t"):
            rows = one("blender-3d", ctx_with(lambda r: httpx.Response(404)))
        self.assertTrue(rows[0].passed)
        self.assertIn("skipped", rows[0].detail)

    def test_blender_fails_on_a_429(self):
        def handler(request):
            return httpx.Response(200, json={}) if request.url.path == "/v1/models" else httpx.Response(429, text="quota")

        with mock.patch.object(net, "device_access_token", return_value="t"):
            rows = one("blender-3d", ctx_with(handler))
        self.assertFalse(rows[0].passed)
        self.assertEqual(sr.row_status(rows[0]), 429)

    def test_claude_code_sends_an_anthropic_message_to_praxis(self):
        seen = {}

        def handler(request):
            seen["url"], seen["headers"], seen["body"] = str(request.url), dict(request.headers), request.content.decode()
            return httpx.Response(200, json={"content": [{"type": "text", "text": "OK"}], "usage": {"input_tokens": 5, "output_tokens": 2}})

        ctx = ctx_with(handler)
        with mock.patch.object(net, "device_access_token", return_value="cc-token") as device:
            rows = one("claude-code-sovereign", ctx)
        self.assertTrue(rows[0].passed, rows[0].detail)
        self.assertEqual(seen["url"], "https://praxis.apps.test/v1/messages")
        self.assertEqual(seen["headers"]["authorization"], "Bearer cc-token")
        self.assertEqual(seen["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(device.call_args[0][3], "claude-code")
        self.assertEqual(ctx.tokens_used, 7)

    def test_claude_code_fails_on_an_empty_answer(self):
        with mock.patch.object(net, "device_access_token", return_value="t"):
            rows = one("claude-code-sovereign", ctx_with(lambda r: httpx.Response(200, json={"content": []})))
        self.assertFalse(rows[0].passed)

    def test_the_device_token_is_cached_per_persona_and_client(self):
        with mock.patch.dict(sys.modules, {"device_login": SimpleNamespace(device_token=mock.Mock(return_value={"access_token": "a"}))}) as _:
            fake = sys.modules["device_login"].device_token
            self.assertEqual(net.device_access_token("iss", "p", "pw", "blender"), "a")
            self.assertEqual(net.device_access_token("iss", "p", "pw", "blender"), "a")
            net.device_access_token("iss", "p", "pw", "claude-code")
        self.assertEqual(fake.call_count, 2)

    def test_judge_burst(self):
        self.assertEqual(net.judge_burst([200, 200, 429], 30)[0], True)
        self.assertEqual(net.judge_burst([502, 502], 30)[0], False)
        self.assertIn("models are down", net.judge_burst([502], 30)[1])
        self.assertEqual(net.judge_burst([200] * 3, 3)[0], False)

    def test_quotas_burns_until_the_first_429_with_the_stresstest_class(self):
        count = {"n": 0}
        classes = []

        def handler(request):
            count["n"] += 1
            classes.append(request.headers["x-zuno-quota-class"])
            return httpx.Response(429) if count["n"] == 4 else httpx.Response(200, json={"usage": {"total_tokens": 120}})

        ctx = ctx_with(handler)
        rows = one("quotas", ctx)
        self.assertTrue(rows[0].passed, rows[0].detail)
        self.assertEqual(count["n"], 4)
        self.assertEqual(set(classes), {"stresstest"})
        self.assertEqual(ctx.tokens_used, 360)


if __name__ == "__main__":
    unittest.main()
