#!/usr/bin/env python3
"""How evaluations/unifai_rag_library.py drives the UnifAI RAG API (ADR-0616, WP-274), against a fake client.

No network, no httpx: the library's API functions take any client with httpx's get/post/put/request methods.

    python3 evaluations/tests/test_unifai_rag_library.py
"""
import base64
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import unifai_rag_library as lib  # noqa: E402

API = "https://unifai.example/api1"


class Resp:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


class FakeRag:
    """A persona's library: uploads become COLLECTING, then DONE after `polls_to_done` listings."""

    def __init__(self, names=(), polls_to_done=2, fail_names=(), delete_status=200):
        self.sources = {n: {"source_id": f"id-{n}", "source_name": n, "status": "DONE"} for n in names}
        self.polls_to_done = polls_to_done
        self.fail_names = set(fail_names)
        self.delete_status = delete_status
        self.uploaded = {}
        self.deleted = []
        self._age = {}

    def get(self, url, params=None):
        assert url == f"{API}/data_sources/data.sources.get" and params == {"source_type": "DOCUMENT"}
        for name, age in list(self._age.items()):
            self._age[name] = age + 1
            if name in self.fail_names:
                self.sources[name]["status"] = "FAILED"
            elif self._age[name] >= self.polls_to_done:
                self.sources[name]["status"] = "DONE"
        return Resp(200, {"sources": list(self.sources.values())})

    def post(self, url, json=None):
        assert url == f"{API}/docs/upload"
        for f in json["files"]:
            self.uploaded[f["name"]] = base64.b64decode(f["content"])
        return Resp(200, {"message": "Files uploaded successfully"})

    def put(self, url, json=None):
        assert url == f"{API}/pipelines/embed"
        assert json["source_type"] == "document" and json["skip_validation"] is True
        for d in json["data"]:
            name = d["source_name"]
            self.sources[name] = {"source_id": f"id-{name}", "source_name": name, "status": "COLLECTING"}
            self._age[name] = 0
        return Resp(200, {"registration_completed": True})

    def request(self, method, url, json=None):
        assert method == "DELETE" and url == f"{API}/data_sources/data.source.delete"
        if self.delete_status != 200:
            return Resp(self.delete_status, {"status": "partial"})
        for sid in json["pipeline_ids"]:
            name = next(n for n, s in self.sources.items() if s["source_id"] == sid)
            del self.sources[name]
            self.deleted.append(name)
        return Resp(200, {"status": "success", "results": {"succeeded": [], "failed": []}})


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class LibraryTest(unittest.TestCase):
    def test_delete_touches_only_the_named_files(self):
        rag = FakeRag(names=["travel-and-expense-policy.md", "questions.md", "keep-me.md"])
        results = lib.delete_named(rag, API, ["travel-and-expense-policy.md", "questions.md", "on-call-rota-handbook.md"])
        self.assertEqual([r["result"] for r in results], ["deleted", "deleted", "absent"])
        self.assertTrue(all(r["ok"] for r in results))
        self.assertEqual(sorted(rag.sources), ["keep-me.md"])

    def test_partial_delete_is_a_failure(self):
        rag = FakeRag(names=["a.md"], delete_status=207)
        [result] = lib.delete_named(rag, API, ["a.md"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["result"], "HTTP 207")

    def test_upload_sends_base64_json_then_waits_until_done(self):
        rag = FakeRag(polls_to_done=3)
        clock = Clock()
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "on-call-rota-handbook.md"
            path.write_text("# On-call\n")
            [up] = lib.upload_files(rag, API, [path])
        self.assertEqual(up["result"], "started")
        self.assertEqual(rag.uploaded["on-call-rota-handbook.md"], b"# On-call\n")
        [done] = lib.wait_done(rag, API, ["on-call-rota-handbook.md"], timeout=60, interval=3,
                               sleep=clock.sleep, clock=clock)
        self.assertTrue(done["ok"])
        self.assertEqual(done["result"], "DONE")

    def test_upload_leaves_a_present_file_alone(self):
        rag = FakeRag(names=["a.md"])
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "a.md"
            path.write_text("x")
            [up] = lib.upload_files(rag, API, [path])
        self.assertEqual(up["result"], "present")
        self.assertEqual(rag.uploaded, {})

    def test_a_failed_pipeline_ends_the_wait(self):
        rag = FakeRag(fail_names=["bad.md"])
        rag.put(f"{API}/pipelines/embed", json={"data": [{"source_name": "bad.md", "tags": []}],
                                                 "source_type": "document", "skip_validation": True})
        clock = Clock()
        [res] = lib.wait_done(rag, API, ["bad.md"], timeout=60, sleep=clock.sleep, clock=clock)
        self.assertFalse(res["ok"])
        self.assertEqual(res["result"], "FAILED")
        self.assertLess(clock.now, 60)

    def test_the_wait_times_out(self):
        rag = FakeRag(polls_to_done=1000)
        rag.put(f"{API}/pipelines/embed", json={"data": [{"source_name": "slow.md", "tags": []}],
                                                 "source_type": "document", "skip_validation": True})
        clock = Clock()
        [res] = lib.wait_done(rag, API, ["slow.md"], timeout=9, interval=3, sleep=clock.sleep, clock=clock)
        self.assertFalse(res["ok"])
        self.assertEqual(res["result"], "COLLECTING")

    def test_warm_runs_one_turn_and_always_deletes_its_session(self):
        class Run:
            def __init__(self, status, reply):
                self.status, self.reply, self.seconds = status, reply, 1.234

        class Target:
            def __init__(self, run):
                self._run, self.cleaned, self.calls = run, 0, []

            def run(self, persona, message, workflow=None, timeout=0):
                self.calls.append((persona, workflow))
                return self._run

            def cleanup(self):
                self.cleaned += 1

        good = Target(Run(200, "I can help with your documents."))
        [r] = lib.warm(good, "consultant-01", "consultant-01-my-assistant")
        self.assertTrue(r["ok"])
        self.assertEqual(good.calls, [("consultant-01", "consultant-01-my-assistant")])
        self.assertEqual(good.cleaned, 1)
        bad = Target(Run(403, ""))
        [r] = lib.warm(bad, "consultant-01", "consultant-01-my-assistant")
        self.assertFalse(r["ok"])
        self.assertEqual(r["result"], "HTTP 403")
        self.assertEqual(bad.cleaned, 1)

    def test_names_with_a_path_are_refused(self):
        for bad in ["../x.md", "a/b.md", "", "a\\b.md"]:
            with self.assertRaises(lib.LibraryError):
                lib.check_name(bad)


if __name__ == "__main__":
    unittest.main()
