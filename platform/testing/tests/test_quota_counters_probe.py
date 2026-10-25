"""WP-177 tests for platform/testing/quota_counters_probe.py (no cluster needed).

Run from this directory:

    python3 tests/test_quota_counters_probe.py
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import quota_counters_probe as probe  # noqa: E402


def counter(name: str, remaining: int, groups: str = "g", max_value: int = 1000) -> dict:
    return {"limit": {"name": name, "max_value": max_value}, "set_variables": {"h": groups}, "remaining": remaining}


SUB = "models-as-a-service-qwen36-27b-instruct-ai-gateway-qwen36-27b-instruct-tokens"


class ClassifyTests(unittest.TestCase):
    def test_families(self) -> None:
        self.assertEqual(probe.family("standard-user"), "user")
        self.assertEqual(probe.family("standard-group"), "group")
        self.assertEqual(probe.family(SUB), "subscription")
        self.assertEqual(probe.family("l1"), "other")

    def test_only_the_subscription_moved(self) -> None:
        before = [counter(SUB, 1000), counter("standard-group", 900, max_value=1000)]
        after = [counter(SUB, 859), counter("standard-group", 900, max_value=1000)]
        self.assertEqual(probe.moved_families(before, after), {"subscription": 141})

    def test_new_counter_counts_from_zero(self) -> None:
        after = [counter("standard-user", 950, max_value=1000)]
        self.assertEqual(probe.moved_families([], after), {"user": 50})

    def test_judge(self) -> None:
        self.assertEqual(probe.judge({"subscription": 5}, {"subscription"})[0], 0)
        code, message = probe.judge({"subscription": 5, "group": 5}, {"subscription"})
        self.assertEqual(code, 1)
        self.assertIn("IMPROVED", message)
        code, message = probe.judge({}, {"subscription"})
        self.assertEqual(code, 1)
        self.assertIn("DIFFERS", message)


class _Stub(BaseHTTPRequestHandler):
    reads = 0
    chat_status = 200

    def log_message(self, *args) -> None:  # silence
        pass

    def _send(self, status: int, body) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        type(self).reads += 1
        remaining = 1000 if type(self).reads == 1 else 859
        self._send(200, [counter(SUB, remaining)])

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("content-length", 0)))
        if self.path.endswith("/token"):
            self._send(200, {"access_token": "t"})
        else:
            self._send(type(self).chat_status, {"choices": []})


class EndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        _Stub.reads = 0
        _Stub.chat_status = 200
        self.server = HTTPServer(("127.0.0.1", 0), _Stub)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{self.server.server_port}"
        import os
        os.environ.update({"LIMITADOR_URL": url, "KEYCLOAK_URL": url, "AI_GATEWAY_URL": url,
                           "EVAL_CLIENT_SECRET": "s", "DEMO_PERSONA_PASSWORD": "p"})

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_expected_set_exits_zero(self) -> None:
        self.assertEqual(probe.main(["--settle", "0"]), 0)

    def test_unexpected_set_exits_one(self) -> None:
        self.assertEqual(probe.main(["--settle", "0", "--expect", "subscription,group"]), 1)

    def test_chat_failure_exits_two(self) -> None:
        _Stub.chat_status = 503
        self.assertEqual(probe.main(["--settle", "0"]), 2)

    def test_unreachable_exits_two(self) -> None:
        import os
        os.environ["LIMITADOR_URL"] = "http://127.0.0.1:9"
        self.assertEqual(probe.main(["--settle", "0"]), 2)


if __name__ == "__main__":
    unittest.main()
