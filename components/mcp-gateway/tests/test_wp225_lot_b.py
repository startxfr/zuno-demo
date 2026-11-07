"""WP-225 lot B (ADR-0603 M12, M13, M15) in the mcp-gateway:

- the signed caller context sent to every streamable-HTTP backend, built from the
  validated identity only;
- the namespace matcher enforced in every selector of a `metrics.query` PromQL
  (app/promql_scope.py), including the crafted queries that try to escape it;
- the email recipient allowlist of `email.report.send`, by the caller's groups;
- the bound on a JSON-RPC batch at /mcp, answered with one Invalid Request.

Run from the component directory:

    cd components/mcp-gateway && python3 tests/test_wp225_lot_b.py
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import pathlib
import sys
import unittest
from unittest import mock

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("TOOL_BINDINGS_PATH", str(_REPO_ROOT / "platform/bindings/tools/tool-bindings.yaml"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okf_release_dir import AGENTS_DIR as _OKF_AGENTS_DIR, TOOL_POLICY_PATH as _OKF_TOOL_POLICY_PATH  # noqa: E402

os.environ.setdefault("TOOL_POLICY_PATH", _OKF_TOOL_POLICY_PATH)
os.environ.setdefault("DATA_CLASSIFICATION_PATH", str(_REPO_ROOT / "policies/data-classification/classification.yaml"))
os.environ.setdefault("AGENTS_DIR", _OKF_AGENTS_DIR)
os.environ["MCP_FRONTDOOR_CAPABILITIES"] = "metrics.query,confluence.page.search"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as gateway_main  # noqa: E402
from app import caller_context, downstream, promql_scope  # noqa: E402
from app.auth import CallerIdentity, validate_token_or_kubernetes  # noqa: E402
from app.handlers import email_report  # noqa: E402
from app.policy import PolicyStore  # noqa: E402
from app.promql_scope import PromQLScopeError, scope_query  # noqa: E402

NS = ["zuno-ai-run", "zuno-data"]
MATCHER = 'namespace=~"zuno-ai-run|zuno-data"'
OPS = CallerIdentity(sub="ops-01", groups=["ocp-ai-ops"], raw_claims={"iss": "zuno", "email": "Ops@Example.com",
                                                                         "preferred_username": "ops-01"}, token="jwt")


def _decode(raw):
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


class _Captured(Exception):
    pass


def _capture_outbound(binding_name, workload_token="wt"):
    """Invoke the real downstream path for `binding_name` and return the headers of
    the outbound HTTP client (the MCP session itself is stopped before any I/O)."""
    captured = {}

    class _Client:
        def __init__(self, timeout=None, headers=None):
            captured.update(headers or {})

    def _stop(*_a, **_k):
        raise _Captured()

    binding = gateway_main.binding_registry.resolve(binding_name)
    with mock.patch.object(downstream, "MCP_GATEWAY_WORKLOAD_TOKEN", workload_token), \
            mock.patch.object(downstream.httpx2, "AsyncClient", _Client), \
            mock.patch.object(downstream, "streamable_http_client", _stop):
        try:
            asyncio.run(downstream.invoke(binding, binding_name, {}, "ops-01", "jwt",
                                          caller_groups=["ocp-ai-ops"], caller_claims=OPS.raw_claims))
        except _Captured:
            pass
    return binding, captured


class CallerContextTest(unittest.TestCase):
    def test_signed_from_the_identity_for_one_backend(self):
        claims = {**OPS.raw_claims, "email_verified": True}
        h = caller_context.build(sub="s", groups=["b", "a", "a"], claims=claims, tool="create_page",
                                 audience="confluence", workload_token="wt", now=1000)
        raw, sig = h[caller_context.CONTEXT_HEADER], h[caller_context.SIGNATURE_HEADER]
        expected = hmac.new(caller_context.derive_key("wt", "confluence"), raw.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(sig, expected)
        self.assertEqual(_decode(raw), {"v": 1, "aud": "confluence", "sub": "s", "groups": ["a", "b"],
                                        "email": "ops@example.com", "email_verified": True,
                                        "username": "ops-01", "tool": "create_page", "iat": 1000})
        self.assertNotEqual(caller_context.derive_key("wt", "confluence"), b"wt")
        self.assertNotEqual(caller_context.derive_key("wt", "confluence"), caller_context.derive_key("wt", "aap"),
                            "each backend has its own key")

    def test_email_verified_is_true_only_for_a_json_true(self):
        for value in (False, None, "true", 1):
            h = caller_context.build(sub="s", groups=[], claims={"email": "a@b", "email_verified": value},
                                     tool="t", audience="salesforce", workload_token="wt")
            self.assertIs(_decode(h[caller_context.CONTEXT_HEADER])["email_verified"], False, value)

    def test_no_workload_token_or_audience_no_headers(self):
        self.assertEqual(caller_context.build(sub="s", groups=[], claims={}, tool="t", audience="aap",
                                              workload_token=""), {})
        self.assertEqual(caller_context.build(sub="s", groups=[], claims={}, tool="t", audience="",
                                              workload_token="wt"), {})

    def test_a_consuming_binding_gets_a_context_for_its_own_backend(self):
        binding, captured = _capture_outbound("confluence.page.create")
        self.assertTrue(binding.caller_context)
        self.assertEqual(captured.get("X-Zuno-Gateway-Token"), "wt")
        payload = _decode(captured[caller_context.CONTEXT_HEADER])
        self.assertEqual((payload["aud"], payload["sub"], payload["groups"], payload["tool"]),
                         ("confluence", "ops-01", ["ocp-ai-ops"], binding.provider_tool))
        expected = hmac.new(caller_context.derive_key("wt", "confluence"),
                            captured[caller_context.CONTEXT_HEADER].encode(), hashlib.sha256).hexdigest()
        self.assertEqual(captured[caller_context.SIGNATURE_HEADER], expected)

    def test_only_the_four_zuno_servers_consume_the_context(self):
        consuming = {b.backend for b in gateway_main.binding_registry._bindings if b.caller_context}
        self.assertEqual(consuming, {"confluence", "git-forge", "salesforce", "aap"})
        for b in gateway_main.binding_registry._bindings:
            if b.caller_context:
                self.assertEqual(b.transport, "streamable-http", b.capability)

    def test_a_third_party_backend_gets_neither_the_context_nor_the_workload_token(self):
        binding, captured = _capture_outbound("metrics.query")
        self.assertEqual(binding.backend, "k8s")
        self.assertNotIn(caller_context.CONTEXT_HEADER, captured)
        self.assertNotIn(caller_context.SIGNATURE_HEADER, captured)
        self.assertNotIn("X-Zuno-Gateway-Token", captured)
        self.assertEqual(captured["Authorization"], "Bearer jwt")

    def test_inbound_caller_headers_are_never_forwarded(self):
        """A caller that sends its own X-Zuno-Caller-* to the gateway: the outbound
        call carries the gateway's context (for consuming backends) or none at all."""
        forged = {"X-Zuno-Caller-Context": "Zm9yZ2Vk", "X-Zuno-Caller-Signature": "0" * 64,
                  "X-Zuno-Data-Classification": "C2"}
        seen = []

        class _Client:
            def __init__(self, timeout=None, headers=None):
                seen.append(dict(headers or {}))

        def _stop(*_a, **_k):
            raise _Captured()

        gateway_main.app.dependency_overrides[validate_token_or_kubernetes] = lambda: OPS
        env = {"MCP_FRONTDOOR_CAPABILITIES": "metrics.query,aap.platform.audit", "METRICS_NAMESPACES_BY_GROUP": ""}
        try:
            with mock.patch.dict(os.environ, env), \
                    mock.patch.object(downstream, "MCP_GATEWAY_WORKLOAD_TOKEN", "wt"), \
                    mock.patch.object(downstream.httpx2, "AsyncClient", _Client), \
                    mock.patch.object(downstream, "streamable_http_client", _stop), \
                    mock.patch.object(gateway_main, "invoke_downstream", downstream.invoke), \
                    mock.patch.object(gateway_main, "policy_store", PolicyStore(
                        _OKF_TOOL_POLICY_PATH, str(_REPO_ROOT / "policies/data-classification/classification.yaml"))):
                client = TestClient(gateway_main.app, raise_server_exceptions=False)
                for name in ("metrics.query", "aap.platform.audit"):
                    client.post("/mcp", headers=forged, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                              "params": {"name": name, "arguments": {"query": "up"}}})
        finally:
            gateway_main.app.dependency_overrides.clear()
        self.assertEqual(len(seen), 2, seen)
        k8s, aap = seen
        self.assertNotIn("X-Zuno-Caller-Context", k8s)
        self.assertNotIn("X-Zuno-Caller-Signature", k8s)
        self.assertNotEqual(aap["X-Zuno-Caller-Context"], forged["X-Zuno-Caller-Context"])
        self.assertNotEqual(aap["X-Zuno-Caller-Signature"], forged["X-Zuno-Caller-Signature"])
        self.assertEqual(_decode(aap["X-Zuno-Caller-Context"])["aud"], "aap")

    def test_a_non_boolean_flag_fails_the_binding(self):
        from app.bindings import Binding, _validate
        bad = Binding(capability="x.y", backend="b", transport="streamable-http", provider_tool="t",
                      auth_mode="service-identity", caller_context="yes")
        self.assertIn("non-boolean caller_context", _validate(bad))


class PromQLScopeTest(unittest.TestCase):
    def scoped(self, query):
        return scope_query(query, NS)

    def test_every_selector_shape_gets_the_matcher(self):
        cases = {
            "up": f"up{{{MATCHER}}}",
            'up{job="x"}': f'up{{job="x", {MATCHER}}}',
            '{__name__=~".+"}': f'{{__name__=~".+", {MATCHER}}}',
            'up{a="b",}': f'up{{a="b",{MATCHER}}}',
            "sum by (namespace) (rate(c[5m]))": f"sum by (namespace) (rate(c{{{MATCHER}}}[5m]))",
            "a / on(pod) group_left(node) b": f"a{{{MATCHER}}} / on(pod) group_left(node) b{{{MATCHER}}}",
            "max_over_time(rate(x[5m])[1h:5m])": f"max_over_time(rate(x{{{MATCHER}}}[5m])[1h:5m])",
            "job:up:rate5m": f"job:up:rate5m{{{MATCHER}}}",
            "1 + 1": "1 + 1",
        }
        for query, expected in cases.items():
            self.assertEqual(self.scoped(query), expected, query)

    def test_a_namespace_matcher_of_the_caller_cannot_widen(self):
        # Matchers are ANDed: the caller's own namespace matcher only narrows.
        for query in ('up{namespace="openshift-etcd"}', 'up{namespace=~".*"}', 'up{namespace!="zuno-ai-run"}',
                      'up{namespace=~".+", namespace!=""}'):
            out = self.scoped(query)
            self.assertTrue(out.endswith(f", {MATCHER}}}"), out)

    def test_an_or_inside_braces_scopes_every_alternative(self):
        out = self.scoped('{namespace="openshift-etcd" or __name__="up"}')
        self.assertEqual(out.count(MATCHER), 2, out)
        left, right = out.split(" or ")
        self.assertIn(MATCHER, left)
        self.assertIn(MATCHER, right)

    def test_a_comment_cannot_hide_a_selector_or_swallow_the_matcher(self):
        out = self.scoped('up # }\n + on() group_left() kube_pod_info')
        self.assertIn(f"up{{{MATCHER}}}", out)
        self.assertIn(f"kube_pod_info{{{MATCHER}}}", out)
        self.assertNotIn("#", out)

    def test_strings_are_not_selectors(self):
        out = self.scoped('label_replace(up, "namespace", "openshift-etcd", "", "")')
        self.assertEqual(out, f'label_replace(up{{{MATCHER}}}, "namespace", "openshift-etcd", "", "")')
        out = self.scoped('up{a="} or vector(1) {"}')
        self.assertEqual(out, f'up{{a="}} or vector(1) {{", {MATCHER}}}')

    def test_constructs_that_cannot_be_scoped_are_refused(self):
        for query in ("info(up)", "up}", 'up{a="b"', '"open', "up[5m{a=\"b\"}]", "2up", "upé", "up[x]",
                      'sum by (namespace="x") (up)', "up{a=(b)}", "", "   ", "rate(up[5m]", "rate(up[5m]))"):
            with self.assertRaises(PromQLScopeError, msg=query):
                self.scoped(query)

    def test_unicode_digits_and_spaces_are_a_scope_error_not_a_crash(self):
        # "²".isdigit() is True; it must be refused as a character, never reach a
        # regular expression that cannot match it (AttributeError, a 500).
        for query in ("²", "up > ²", "rate(up[5²m])", "up\u2003+ up", "\u0663"):
            with self.assertRaises(PromQLScopeError, msg=repr(query)):
                self.scoped(query)

    def test_the_metrics_tool_refuses_a_unicode_digit_cleanly(self):
        """Through /mcp: the 400 of _authorize_and_invoke becomes a tool error naming
        the scope failure, not an internal error."""
        gateway_main.app.dependency_overrides[validate_token_or_kubernetes] = lambda: OPS
        env = {"METRICS_NAMESPACES_BY_GROUP": json.dumps({"ocp-ai-ops": ["zuno-ai-run"]}),
               "MCP_FRONTDOOR_CAPABILITIES": "metrics.query"}
        try:
            with mock.patch.dict(os.environ, env), mock.patch.object(gateway_main, "policy_store", PolicyStore(
                    _OKF_TOOL_POLICY_PATH, str(_REPO_ROOT / "policies/data-classification/classification.yaml"))):
                resp = TestClient(gateway_main.app).post("/mcp", headers={"X-Zuno-Data-Classification": "C2"}, json={
                    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "metrics.query", "arguments": {"query": "up > ²"}}})
        finally:
            gateway_main.app.dependency_overrides.clear()
        self.assertEqual(resp.status_code, 200, resp.text)
        result = resp.json()["result"]
        self.assertTrue(result["isError"], result)
        self.assertIn("cannot be scoped", result["content"][0]["text"])

    def test_every_rewritten_query_parses_and_every_selector_is_scoped(self):
        """A real PromQL parser (promql-parser, tests/requirements.txt) reads each
        rewritten query: it must parse, and every vector selector (each `or` branch
        included) must carry the namespace matcher."""
        try:
            import promql_parser
        except ImportError:
            self.skipTest("promql-parser not installed (pip install --require-hashes -r tests/requirements.txt)")
        queries = [
            "up", 'up{job="x"}', '{__name__=~".+"}', 'up{a="b",}', "sum by (namespace) (rate(c[5m]))",
            "a / on(pod) group_left(node) b", "max_over_time(rate(x[5m])[1h:5m])", "job:up:rate5m",
            'up{namespace="openshift-etcd"}', 'up{namespace=~".*"} or vector(1)',
            '{namespace="openshift-etcd" or __name__="up"}', 'up # }\n + on() group_left() kube_pod_info',
            'label_replace(up, "namespace", "openshift-etcd", "", "")', 'up{a="} or vector(1) {"}',
            "histogram_quantile(0.9, sum by (le) (rate(h_bucket[5m])))", "rate(x[5m:1m] offset 1h) > bool 0",
            "count_values(\"namespace\", up)", "topk(3, up) unless on(job) down", "up @ start()", "-up",
            "sum without (namespace) (up)", "absent(nonexistent_metric)", "1 + 1",
        ]
        unscoped = []

        def visit(node):
            if isinstance(node, promql_parser.VectorSelector):
                groups = node.matchers.or_matchers or [node.matchers.matchers]
                for group in groups:
                    if not any(m.name == "namespace" and m.op == promql_parser.MatchOp.Re
                               and m.value == "zuno-ai-run|zuno-data" for m in group):
                        unscoped.append(str(node))
            return True

        for query in queries:
            out = self.scoped(query)
            try:
                expr = promql_parser.parse(out)
            except ValueError as exc:
                self.fail(f"{query!r} rewritten to {out!r}, which does not parse: {exc}")
            promql_parser.walk(expr, visit)
        self.assertEqual(unscoped, [])

    def test_configured_namespaces_are_validated(self):
        with self.assertRaises(PromQLScopeError):
            scope_query("up", ['x"} or vector(1) or {a="'])
        with self.assertRaises(PromQLScopeError):
            scope_query("up", [])

    def test_entitlement_by_group(self):
        mapping = {"ocp-ai-ops": ["zuno-ai-run"], "team-data": ["zuno-data"], "ocp-paas-ops": ["*"]}
        ent = promql_scope.entitlement(["ocp-ai-ops", "team-data"], mapping)
        self.assertEqual(ent.namespaces, ("zuno-ai-run", "zuno-data"))
        self.assertTrue(promql_scope.entitlement(["ocp-paas-ops"], mapping).unrestricted)
        self.assertEqual(promql_scope.entitlement(["sales"], mapping).namespaces, ())
        self.assertFalse(promql_scope.entitlement(["sales"], {}).configured)

    def test_scope_arguments(self):
        args = {"query": "up", "time": "now"}
        with mock.patch.dict(os.environ, {"METRICS_NAMESPACES_BY_GROUP": ""}):
            self.assertIs(promql_scope.scope_arguments("metrics.query", args, ["x"]), args, "off: unchanged")
        with mock.patch.dict(os.environ, {"METRICS_NAMESPACES_BY_GROUP": "{}"}):
            self.assertIs(promql_scope.scope_arguments("metrics.query", args, ["x"]), args, "the chart default is off")
        env = {"METRICS_NAMESPACES_BY_GROUP": json.dumps({"ocp-ai-ops": ["zuno-ai-run"]})}
        with mock.patch.dict(os.environ, env):
            out = promql_scope.scope_arguments("metrics.query", args, ["ocp-ai-ops"])
            self.assertEqual(out, {"query": 'up{namespace=~"zuno-ai-run"}', "time": "now"})
            self.assertIs(promql_scope.scope_arguments("k8s.logs.read", args, ["x"]), args)
            with self.assertRaises(PermissionError):
                promql_scope.scope_arguments("metrics.query", args, ["sales"])
            with self.assertRaises(PromQLScopeError):
                promql_scope.scope_arguments("metrics.query", {"q": "up"}, ["ocp-ai-ops"])
        with mock.patch.dict(os.environ, {"METRICS_NAMESPACES_BY_GROUP": "{bad"}):
            with self.assertRaises(PermissionError, msg="a malformed mapping fails closed"):
                promql_scope.scope_arguments("metrics.query", args, ["ocp-ai-ops"])


def _rpc(body, identity=OPS):
    gateway_main.app.dependency_overrides[validate_token_or_kubernetes] = lambda: identity
    try:
        return TestClient(gateway_main.app).post("/mcp", json=body, headers={"X-Zuno-Data-Classification": "C2"})
    finally:
        gateway_main.app.dependency_overrides.clear()


class MetricsThroughTheGatewayTest(unittest.TestCase):
    def setUp(self):
        self.sent = []

        async def fake_downstream(binding, tool_name, arguments, *a, **kw):
            self.sent.append(arguments)
            return {"ok": True}

        # The real tool policy (metrics.query for ocp-ai-ops), whatever another test module
        # installed before this one when the suite runs under pytest.
        self._orig = gateway_main.invoke_downstream, gateway_main.policy_store
        gateway_main.invoke_downstream = fake_downstream
        gateway_main.policy_store = PolicyStore(
            _OKF_TOOL_POLICY_PATH, str(_REPO_ROOT / "policies/data-classification/classification.yaml")
        )

        self._env = mock.patch.dict(os.environ, {"MCP_FRONTDOOR_CAPABILITIES": "metrics.query"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        gateway_main.invoke_downstream, gateway_main.policy_store = self._orig

    def call(self, query):
        return _rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "metrics.query", "arguments": {"query": query}}})

    def test_the_backend_receives_the_scoped_query(self):
        env = {"METRICS_NAMESPACES_BY_GROUP": json.dumps({"ocp-ai-ops": ["zuno-ai-run"]})}
        with mock.patch.dict(os.environ, env):
            resp = self.call('kube_pod_info{namespace="openshift-etcd"} or {__name__="up"}')
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertFalse(resp.json()["result"].get("isError"), resp.json())
        self.assertEqual(self.sent, [{"query": 'kube_pod_info{namespace="openshift-etcd", namespace=~"zuno-ai-run"}'
                                               ' or {__name__="up", namespace=~"zuno-ai-run"}'}])

    def test_an_unscopable_query_never_reaches_the_backend(self):
        env = {"METRICS_NAMESPACES_BY_GROUP": json.dumps({"ocp-ai-ops": ["zuno-ai-run"]})}
        with mock.patch.dict(os.environ, env):
            resp = self.call("info(up)")
        self.assertTrue(resp.json()["result"]["isError"], resp.json())
        self.assertEqual(self.sent, [])

    def test_a_caller_without_a_namespace_is_refused(self):
        env = {"METRICS_NAMESPACES_BY_GROUP": json.dumps({"team-data": ["zuno-data"]})}
        with mock.patch.dict(os.environ, env):
            resp = self.call("up")
        self.assertTrue(resp.json()["result"]["isError"], resp.json())
        self.assertEqual(self.sent, [])

    def test_off_sends_the_query_unchanged(self):
        with mock.patch.dict(os.environ, {"METRICS_NAMESPACES_BY_GROUP": ""}):
            self.call("up")
        self.assertEqual(self.sent, [{"query": "up"}])


class BatchBoundTest(unittest.TestCase):
    def ping(self, i):
        return {"jsonrpc": "2.0", "id": i, "method": "ping"}

    def test_a_batch_within_the_bound_is_served(self):
        with mock.patch.dict(os.environ, {"MCP_MAX_BATCH_SIZE": "3"}):
            resp = _rpc([self.ping(i) for i in range(3)])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 3)

    def test_a_batch_past_the_bound_is_one_invalid_request(self):
        sent = []

        async def fake_dispatch(msg, **kw):
            sent.append(msg)
            return {"jsonrpc": "2.0", "id": msg.get("id"), "result": {}}

        with mock.patch.dict(os.environ, {"MCP_MAX_BATCH_SIZE": "3"}), \
                mock.patch.object(gateway_main.mcp_frontdoor, "dispatch", fake_dispatch):
            resp = _rpc([self.ping(i) for i in range(4)])
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsInstance(body, dict, "one error object, not an array")
        self.assertEqual(body["jsonrpc"], "2.0")
        self.assertIsNone(body["id"])
        self.assertEqual(body["error"]["code"], -32600)
        self.assertIn("exceeds the limit of 3", body["error"]["message"])
        self.assertEqual(sent, [], "no message of the batch is processed")

    def test_an_empty_batch_is_an_invalid_request(self):
        body = _rpc([]).json()
        self.assertEqual((body["id"], body["error"]["code"]), (None, -32600))

    def test_default_and_malformed_bound(self):
        with mock.patch.dict(os.environ, {"MCP_MAX_BATCH_SIZE": ""}):
            self.assertEqual(gateway_main.max_batch_size(), gateway_main.DEFAULT_MAX_BATCH_SIZE)
        with mock.patch.dict(os.environ, {"MCP_MAX_BATCH_SIZE": "lots"}):
            self.assertEqual(gateway_main.max_batch_size(), gateway_main.DEFAULT_MAX_BATCH_SIZE)
        with mock.patch.dict(os.environ, {"MCP_MAX_BATCH_SIZE": "0"}):
            self.assertEqual(gateway_main.max_batch_size(), 0)
            resp = _rpc([self.ping(i) for i in range(30)])
            self.assertEqual(len(resp.json()), 30, "0 is unbounded")


class EmailAllowlistTest(unittest.TestCase):
    def send(self, recipients, groups, allowlist):
        env = {"EMAIL_RECIPIENT_ALLOWLIST": json.dumps(allowlist) if isinstance(allowlist, dict) else allowlist}
        with mock.patch.dict(os.environ, env):
            return asyncio.run(email_report.handle({"recipients": recipients, "subject": "s", "body": "b"},
                                                   "u-1", caller_groups=groups))

    def test_no_allowlist_behaves_as_before(self):
        self.assertTrue(self.send(["a@zuno.example.internal"], ["sales"], "")["sent"])
        self.assertTrue(self.send(["a@zuno.example.internal"], ["sales"], "{}")["sent"], "the chart default is off")

    def test_recipient_outside_the_callers_group_is_refused(self):
        allow = {"sales": ["sales-*@zuno.example.internal"], "board": ["*@zuno.example.internal"]}
        out = self.send(["ceo@zuno.example.internal"], ["sales"], allow)
        self.assertFalse(out["sent"])
        self.assertIn("allowlist", out["reason"])
        self.assertTrue(self.send(["Sales-Team@Zuno.example.internal"], ["sales"], allow)["sent"])
        self.assertTrue(self.send(["ceo@zuno.example.internal"], ["board"], allow)["sent"])

    def test_one_recipient_outside_refuses_the_whole_send(self):
        allow = {"sales": ["sales-*@zuno.example.internal"]}
        out = self.send(["sales-a@zuno.example.internal", "b@zuno.example.internal"], ["sales"], allow)
        self.assertFalse(out["sent"])

    def test_groups_come_from_the_caller_not_the_arguments(self):
        allow = {"board": ["*@zuno.example.internal"]}
        env = {"EMAIL_RECIPIENT_ALLOWLIST": json.dumps(allow)}
        with mock.patch.dict(os.environ, env):
            out = asyncio.run(email_report.handle(
                {"recipients": ["ceo@zuno.example.internal"], "caller_groups": ["board"], "groups": ["board"]},
                "u-1", caller_groups=["sales"]))
        self.assertFalse(out["sent"])

    def test_malformed_allowlist_fails_closed(self):
        self.assertFalse(self.send(["a@zuno.example.internal"], ["sales"], "{bad")["sent"])

    def test_internal_domain_rule_still_applies(self):
        self.assertFalse(self.send(["x@gmail.com"], ["sales"], {"sales": ["*"]})["sent"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
