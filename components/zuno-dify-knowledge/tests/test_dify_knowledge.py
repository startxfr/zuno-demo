"""zuno-dify-knowledge (ADR-0599, WP-205): the External Knowledge contract over a fake mcp-gateway.

The token proxy / mcp-gateway is an httpx mock transport.

Run from the component directory:

    cd components/zuno-dify-knowledge && python3 tests/test_dify_knowledge.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import unittest
from typing import Any, Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import metrics  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

KEY = "static-dify-key"
SETTINGS = Settings(api_key=KEY, mcp_url="http://proxy.test:8080/mcp", knowledge_bases={"tech": "knowledge.tech"})
AUTH = {"Authorization": f"Bearer {KEY}"}

ROWS = [
    {"id": "1", "source": "https://wiki/x", "title": "Runbook", "snippet": "restart the pod", "score": 0.9,
     "classification": "C3"},
    {"id": "2", "source": "https://docs.redhat.com/y", "title": "OCP", "snippet": "drain a node", "score": 0.4},
]


class FakeGateway:
    def __init__(self, rows: List[Dict[str, Any]] = None, mode: str = "json") -> None:
        self.rows = ROWS if rows is None else rows
        self.mode = mode
        self.seen: List[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        message = json.loads(request.content)
        if self.mode == "down":
            return httpx.Response(503, text="no token")
        if self.mode == "denied":
            result: Dict[str, Any] = {"content": [{"type": "text", "text": "denied: not entitled"}], "isError": True}
        elif self.mode == "tool-error":
            result = {"content": [], "isError": False, "structuredContent": {"error": "technical-docs search failed"}}
        elif self.mode == "text-only":
            result = {"content": [{"type": "text", "text": json.dumps({"results": self.rows})}], "isError": False}
        elif self.mode == "sentence":
            result = {"content": [{"type": "text", "text": "No result: the arguments did not match."}], "isError": False}
        else:
            result = {"content": [{"type": "text", "text": "x"}], "isError": False,
                      "structuredContent": {"results": self.rows}}
        rpc = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        if self.mode == "sse":
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  text="event: message\ndata: " + json.dumps(
                                      {"jsonrpc": "2.0", "id": 1, "result": {
                                          "content": [], "isError": False, "structuredContent": {"results": self.rows}}}
                                  ) + "\n\n")
        return httpx.Response(200, json=rpc)


def client(gateway: FakeGateway) -> TestClient:
    return TestClient(create_app(SETTINGS, transport=httpx.MockTransport(gateway.handler)))


def body(**over: Any) -> Dict[str, Any]:
    base = {"knowledge_id": "tech", "query": "restart", "retrieval_setting": {"top_k": 5, "score_threshold": 0.0}}
    base.update(over)
    return base


class RetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        metrics.reset()

    def test_records_keep_classification_and_source(self) -> None:
        gw = FakeGateway()
        r = client(gw).post("/retrieval", json=body(), headers=AUTH)
        self.assertEqual(r.status_code, 200)
        records = r.json()["records"]
        self.assertEqual(records[0], {
            "content": "restart the pod", "score": 0.9, "title": "Runbook",
            "metadata": {"source": "https://wiki/x", "classification": "C3", "id": "1"}})
        # a chunk with no classification fails closed to C2, like the gateway
        self.assertEqual(records[1]["metadata"]["classification"], "C2")

    def test_call_is_one_tools_call_with_query_and_top_k(self) -> None:
        gw = FakeGateway()
        client(gw).post("/retrieval", json=body(retrieval_setting={"top_k": 3}), headers=AUTH)
        self.assertEqual(len(gw.seen), 1)
        sent = json.loads(gw.seen[0].content)
        self.assertEqual(sent["method"], "tools/call")
        self.assertEqual(sent["params"], {"name": "knowledge.tech.search", "arguments": {"query": "restart", "top_k": 3}})
        # Dify's bearer is never relayed: the token proxy owns Authorization
        self.assertNotIn("authorization", gw.seen[0].headers)

    def test_score_threshold_filters_locally(self) -> None:
        r = client(FakeGateway()).post(
            "/retrieval", json=body(retrieval_setting={"top_k": 5, "score_threshold": 0.5}), headers=AUTH)
        self.assertEqual([x["title"] for x in r.json()["records"]], ["Runbook"])

    def test_top_k_is_capped(self) -> None:
        gw = FakeGateway()
        client(gw).post("/retrieval", json=body(retrieval_setting={"top_k": 500}), headers=AUTH)
        self.assertEqual(json.loads(gw.seen[0].content)["params"]["arguments"]["top_k"], SETTINGS.max_top_k)

    def test_nothing_allowed_is_an_empty_list_not_an_error(self) -> None:
        r = client(FakeGateway(rows=[])).post("/retrieval", json=body(), headers=AUTH)
        self.assertEqual((r.status_code, r.json()), (200, {"records": []}))

    def test_answers_in_sse_and_text_only_and_sentence(self) -> None:
        self.assertEqual(len(client(FakeGateway(mode="sse")).post("/retrieval", json=body(), headers=AUTH).json()["records"]), 2)
        self.assertEqual(len(client(FakeGateway(mode="text-only")).post("/retrieval", json=body(), headers=AUTH).json()["records"]), 2)
        self.assertEqual(client(FakeGateway(mode="sentence")).post("/retrieval", json=body(), headers=AUTH).json(), {"records": []})

    def test_failures_are_502_never_an_empty_success(self) -> None:
        for mode in ("down", "denied", "tool-error"):
            r = client(FakeGateway(mode=mode)).post("/retrieval", json=body(), headers=AUTH)
            self.assertEqual(r.status_code, 502, mode)
            self.assertNotIn("records", r.json())
        self.assertEqual(metrics.value("zuno_dify_knowledge_requests_total", code="502"), 3)

    def test_registration_probe_is_200_empty_and_calls_nothing(self) -> None:
        gw = FakeGateway()
        r = client(gw).post("/retrieval", json={"knowledge_id": "", "query": "",
                                                  "retrieval_setting": {"top_k": 1, "score_threshold": 0.0}}, headers=AUTH)
        self.assertEqual((r.status_code, r.json()), (200, {"records": []}))
        self.assertEqual(gw.seen, [])

    def test_unknown_knowledge_is_2001_and_calls_nothing(self) -> None:
        gw = FakeGateway()
        r = client(gw).post("/retrieval", json=body(knowledge_id="other"), headers=AUTH)
        self.assertEqual((r.status_code, r.json()["error_code"]), (404, 2001))
        self.assertEqual(gw.seen, [])

    def test_empty_query_calls_nothing(self) -> None:
        gw = FakeGateway()
        r = client(gw).post("/retrieval", json=body(query="  "), headers=AUTH)
        self.assertEqual((r.status_code, r.json()), (200, {"records": []}))
        self.assertEqual(gw.seen, [])

    def test_only_the_static_bearer_is_accepted(self) -> None:
        gw = FakeGateway()
        c = client(gw)
        for headers, code in (({}, 1001), ({"Authorization": "Basic abc"}, 1001), ({"Authorization": "Bearer "}, 1001),
                              ({"Authorization": "Bearer wrong"}, 1002), ({"Authorization": f"Bearer {KEY}x"}, 1002)):
            r = c.post("/retrieval", json=body(), headers=headers)
            self.assertEqual((r.status_code, r.json()["error_code"]), (403, code), headers)
        self.assertEqual(gw.seen, [])

    def test_bad_body_is_400(self) -> None:
        c = client(FakeGateway())
        self.assertEqual(c.post("/retrieval", content=b"nope", headers=AUTH).status_code, 400)
        self.assertEqual(c.post("/retrieval", json=body(retrieval_setting={"top_k": "many"}), headers=AUTH).status_code, 400)

    def test_probes_and_metrics_need_no_key(self) -> None:
        c = client(FakeGateway())
        self.assertEqual(c.get("/healthz").status_code, 200)
        self.assertEqual(c.get("/readyz").status_code, 200)
        self.assertEqual(c.get("/metrics").status_code, 200)


class SettingsTests(unittest.TestCase):
    def test_key_from_file_and_required(self) -> None:
        with self.assertRaises(ValueError):
            Settings.from_env({})
        path = pathlib.Path(__file__).with_name("key.tmp")
        path.write_text("filekey\n")
        try:
            self.assertEqual(Settings.from_env({"API_KEY_FILE": str(path)}).api_key, "filekey")
        finally:
            path.unlink()

    def test_knowledge_bases_parse(self) -> None:
        s = Settings.from_env({"API_KEY": "k", "KNOWLEDGE_BASES": "tech=knowledge.tech, ops=knowledge.ops"})
        self.assertEqual(s.knowledge_bases, {"tech": "knowledge.tech", "ops": "knowledge.ops"})
        with self.assertRaises(ValueError):
            Settings.from_env({"API_KEY": "k", "KNOWLEDGE_BASES": "broken"})


class ProxyKeyTests(unittest.TestCase):
    """WP-225 lot C: the token proxy's inbound key, sent only when configured."""

    def test_the_proxy_key_is_sent_to_the_proxy_and_dify_s_key_never_is(self) -> None:
        import dataclasses

        gw = FakeGateway()
        settings = dataclasses.replace(SETTINGS, proxy_key="p" * 32)
        TestClient(create_app(settings, transport=httpx.MockTransport(gw.handler))).post(
            "/retrieval", json=body(), headers=AUTH)
        self.assertEqual(gw.seen[0].headers["authorization"], "Bearer " + "p" * 32)
        self.assertNotIn(KEY, str(gw.seen[0].headers))

    def test_proxy_key_file(self) -> None:
        import os
        import tempfile

        base = {"API_KEY": KEY}
        self.assertEqual(Settings.from_env(base).proxy_key, "")
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            fh.write("# token proxy inbound key\n" + "p" * 32 + "\n")
        self.addCleanup(os.unlink, fh.name)
        self.assertEqual(Settings.from_env({**base, "PROXY_KEY_FILE": fh.name}).proxy_key, "p" * 32)
        with tempfile.NamedTemporaryFile("w", delete=False) as empty:
            empty.write("")
        self.addCleanup(os.unlink, empty.name)
        with self.assertRaises(ValueError):
            Settings.from_env({**base, "PROXY_KEY_FILE": empty.name})


if __name__ == "__main__":
    unittest.main()
