"""A terminal take (ADR-0618, WP-287): the text gate on the captured session, the `record: {kind, allow}` key of
demo.yml, a terminal take in gif.py, and the two calls of `make demo record` for a terminal demo (capture and gate,
then render). The capture and the replay are faked: no pty, podman, cluster or ffmpeg is needed.

Run from the repository root:
    python3 platform/demo/tests/test_terminal_take.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent))

import catalogue  # noqa: E402
import consistency  # noqa: E402
import gif  # noqa: E402
import presenter  # noqa: E402
import session  # noqa: E402
import textgate  # noqa: E402

PROMPT = "\x1b]1337;rc=0\x07$ "


def cast_text(*outputs: str) -> str:
    header = {"version": 2, "width": 100, "height": 30, "timestamp": 1763200000, "env": {"TERM": "xterm-256color"}}
    lines = [json.dumps(header)]
    t = 0.0
    for chunk in outputs:
        t += 0.5
        lines.append(json.dumps([round(t, 3), "o", chunk]))
    return "\n".join(lines) + "\n"


CLEAN = cast_text(PROMPT, "g", "it log -1 --format=%h\r\n", "\x1b[?2004l", "1f61ca4\r\n", "\x1b[?2004h" + PROMPT,
                  "\x1b[H\x1b[2J", PROMPT, "oc get externalsecrets -n zuno-ai-run\r\n",
                  "NAME                  STORE         STATUS\r\nllm-provider-maas     vault-store   SecretSynced\r\n",
                  PROMPT)


class Gate(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="zuno-gate-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def take(self, cast: str, status: str = "done") -> dict:
        (self.dir / textgate.CAST).write_text(cast)
        (self.dir / textgate.STEPS).write_text(json.dumps({"status": status}))
        return textgate.gate(self.dir)

    def test_a_clean_session_passes_and_reads_as_text(self):
        record = self.take(CLEAN)
        self.assertEqual((record["status"], record["hits"], record["steps_status"]), ("pass", [], "done"))
        text = (self.dir / textgate.TRANSCRIPT).read_text()
        self.assertIn("$ git log -1 --format=%h\n1f61ca4\n", text)
        self.assertIn(textgate.CLEAR_LINE, text)
        self.assertIn("SecretSynced", text)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("1337", text)                       # the prompt's invisible exit-code sequence
        self.assertNotIn("\r", text)
        self.assertEqual(textgate.passed(self.dir), (True, ""))

    def test_both_clear_screen_forms(self):
        self.assertIn(textgate.CLEAR_LINE, textgate.plain("a\x1b[H\x1b[Jb"))
        self.assertIn(textgate.CLEAR_LINE, textgate.plain("a\x1b[H\x1b[2Jb"))

    def test_each_detector_refuses_and_never_shows_the_value(self):
        secrets = {
            "bearer token": "curl -H 'Authorization: Bearer abcdefghijklmnop123456'",
            "JWT": "id_token eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzYWxlLTAxIn0.c2lnbmF0dXJlLXZhbHVl",
            "sha256~ token": "sha256~AbCdEfGhIjKlMnOpQrStUvWxYz0123",
            "URL userinfo": "https://admin:hunter2@vault.example/v1",
            "a password value": "password: hunter2",
            "a api_key value": '{"api_key": "sk-live-123"}',
        }
        for detector, line in secrets.items():
            record = self.take(cast_text(PROMPT, line + "\r\n", PROMPT))
            self.assertEqual(record["status"], "refused", detector)
            self.assertIn(detector, [h["detector"] for h in record["hits"]], (detector, record["hits"]))
            gate_file = (self.dir / textgate.GATE).read_text()
            self.assertNotIn("hunter2", gate_file)
            self.assertNotIn("sk-live", gate_file)
            self.assertEqual(textgate.passed(self.dir)[0], False)

    def test_stand_ins_and_words_are_not_values(self):
        for line in ("token: ***", "TOKEN   READY", "password: <none>", "secretRef: llm-provider",
                     "Authorization: Bearer $(oc whoami -t)", "SecretSynced True", "tokenRateLimits: 3"):
            self.assertEqual(textgate.hits(textgate.plain(line + "\n")), [], line)

    def test_the_cast_is_never_edited(self):
        (self.dir / textgate.CAST).write_text(cast_text("password: hunter2\r\n"))
        before = (self.dir / textgate.CAST).read_bytes()
        textgate.gate(self.dir)
        self.assertEqual((self.dir / textgate.CAST).read_bytes(), before)

    def test_passed_needs_the_same_cast_and_a_finished_capture(self):
        self.take(CLEAN, status="fail")
        self.assertIn("did not finish", textgate.passed(self.dir)[1])
        self.take(CLEAN)
        with open(self.dir / textgate.CAST, "a") as handle:
            handle.write(json.dumps([9.0, "o", "more"]) + "\n")
        self.assertIn("changed after the gate", textgate.passed(self.dir)[1])

    def test_no_cast_or_a_bad_one(self):
        with self.assertRaises(textgate.GateError):
            textgate.gate(self.dir)
        (self.dir / textgate.CAST).write_text('{"version": 1}\n')
        with self.assertRaises(textgate.GateError):
            textgate.gate(self.dir)


class TerminalMarkers(unittest.TestCase):
    """gif.py on a terminal take: nothing created, no persona's list read."""

    def markers(self, **changes):
        data = {"demo": "fixture-demo", "kind": "terminal", "persona": "", "viewport": {"width": 1280, "height": 800},
                "motion_from": "start", "created": [], "cleaned": None, "owned": None, "status": "pass",
                "markers": [{"name": "start", "t": 0.5}, {"name": "00-00-typed", "t": 1.0},
                            {"name": "00-00-done", "t": 4.0}, {"name": "end", "t": 6.0}]}
        data.update(changes)
        return data

    def cut(self):
        return {"target_seconds": [1, 60], "moments": [
            {"from": "00-00-typed", "to": "00-00-done", "fit": 3, "hold": 2, "step": "0:00", "caption": "x"}]}

    def test_a_terminal_take_passes_with_owned_null(self):
        gif.plan("fixture-demo", self.cut(), self.markers(), ["0:00"])

    def test_a_terminal_take_creates_nothing(self):
        for changes in ({"created": [{"kind": "chat", "id": "1"}]}, {"cleaned": True}):
            with self.assertRaises(gif.CutError) as ctx:
                gif.plan("fixture-demo", self.cut(), self.markers(**changes), ["0:00"])
            self.assertIn("creates nothing", ctx.exception.reasons[0])

    def test_an_unknown_kind_and_a_browser_take_without_owned(self):
        with self.assertRaises(gif.CutError) as ctx:
            gif.plan("fixture-demo", self.cut(), self.markers(kind="video"), ["0:00"])
        self.assertIn("unknown take kind", ctx.exception.reasons[0])
        with self.assertRaises(gif.CutError) as ctx:
            gif.plan("fixture-demo", self.cut(), self.markers(kind="browser"), ["0:00"])
        self.assertIn("does not say what the persona owns", " ".join(ctx.exception.reasons))


class FixtureRoot(unittest.TestCase):
    """A copy of the fixture catalogue where fixture-demo is a terminal demo with a cut list."""

    MANIFEST_ADD = ('record:\n  kind: terminal\n  allow:\n    - "oc delete pod fixture -n fixture"\n')

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="zuno-terminal-"))
        shutil.copytree(FIXTURES / "docs", self.root / "docs")
        shutil.copytree(FIXTURES / "ansible", self.root / "ansible")
        self.demo = self.root / "ansible/demos/fixture-demo"
        self.original = (self.demo / "demo.yml").read_text()
        (self.demo / "demo.yml").write_text(self.original + self.MANIFEST_ADD)
        (self.demo / "gif.yml").write_text(
            'target_seconds: [1, 60]\nmoments:\n'
            '  - {from: 00-00-typed, to: 00-00-done, fit: 3, hold: 2, step: "0:00", caption: "One read"}\n')

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def manifest(self):
        return consistency.load_yaml(self.demo / "demo.yml")

    def record_problems(self):
        entry = catalogue.find("fixture-demo", self.root)
        return consistency.record_problems(entry, catalogue.load(entry), self.manifest(), self.root)


class RecordKey(FixtureRoot):
    def test_the_fixture_terminal_record_key_is_valid(self):
        self.assertEqual(self.record_problems(), [])

    def edit(self, new: str):
        (self.demo / "demo.yml").write_text(self.original + new)

    def test_an_allow_entry_must_be_a_do_command_and_never_an_always_refused_one(self):
        self.edit('record:\n  kind: terminal\n  allow: ["oc whoami -t", "oc delete pod other -n fixture"]\n')
        found = self.record_problems()
        self.assertTrue(any("`oc whoami -t`, which is never typed" in p for p in found), found)
        self.assertTrue(any("`oc delete pod other -n fixture`, which is not a Do command" in p for p in found), found)

    def test_kind_and_allow_on_a_browser_take(self):
        self.edit('record:\n  kind: video\n')
        self.assertIn("one of browser, terminal", self.record_problems()[0])
        self.edit('record:\n  kind: browser\n  allow: ["oc delete pod fixture -n fixture"]\n')
        found = self.record_problems()
        self.assertTrue(any("needs evaluations/browser/walkthroughs/fixture-demo.mjs" in p for p in found), found)
        self.assertTrue(any("`record.allow` is for a terminal take" in p for p in found), found)
        self.edit('record:\n  kind: terminal\n  colour: red\n')
        self.assertIn("unknown key(s) colour", self.record_problems()[0])

    def test_the_repository_has_no_record_problem(self):
        self.assertEqual([p for p in consistency.problems(ROOT) if "`record" in p], [])


FAKE_CAPTURE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
mode = os.environ.get("FAKE_CAPTURE", "clean")
demo, rest = sys.argv[1], sys.argv[2:]
if rest == ["--plan"]:
    print("0:00  $ git log -1 --format=%h")
    if mode == "plan-refuse":
        print("CAPTURE: failed row 1:30: `oc delete pod fixture -n fixture` is refused by the read-only allowlist")
        sys.exit(1)
    sys.exit(0)
out = pathlib.Path(rest[0])
prompt = "\x1b]1337;rc=0\x07$ "
body = {"clean": "1f61ca4\r\n", "jwt": "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4eHh4eHgifQ.c2lnbmF0dXJlLXg\r\n"}.get(mode, "")
if mode != "nocast":
    header = {"version": 2, "width": 100, "height": 30, "timestamp": 1}
    events = [[0.5, "o", prompt], [1.0, "o", "git log -1 --format=%h\r\n"], [2.0, "o", body], [2.5, "o", prompt]]
    (out / "terminal.cast").write_text("\n".join([json.dumps(header)] + [json.dumps(e) for e in events]) + "\n")
status = "done" if mode in ("clean", "jwt") else "fail"
(out / "terminal-steps.json").write_text(json.dumps({"demo": demo, "status": status, "detail": mode}))
print("CAPTURE: done" if status == "done" else "CAPTURE: failed " + mode)
sys.exit(0 if status == "done" else 1)
'''

FAKE_RECORDER = r'''#!/bin/sh
[ "$3" = --terminal ] || exit 9
echo "recording: $2"
printf 'webm' > "$2/recording.webm"
echo "RESULT: PASS"
'''


class Routing(FixtureRoot):
    def setUp(self):
        super().setUp()
        self.home = pathlib.Path(tempfile.mkdtemp(prefix="zuno-home-"))
        self.tools = pathlib.Path(tempfile.mkdtemp(prefix="zuno-tools-"))
        (self.tools / "capture.py").write_text(FAKE_CAPTURE)
        (self.tools / "record.sh").write_text(FAKE_RECORDER)
        (self.tools / "record.sh").chmod(0o755)
        self.kubeconfig = self.home / "kubeconfig"
        self.kubeconfig.write_text("apiVersion: v1\n")
        env = {"HOME": str(self.home), "ZUNO_DEMO_ROOT": str(self.root), "KUBECONFIG": str(self.kubeconfig)}
        self.patches = [mock.patch.dict(os.environ, env),
                        mock.patch.multiple(presenter, CAPTURE=self.tools / "capture.py",
                                            RECORDER=self.tools / "record.sh")]
        for p in self.patches:
            p.start()
        for name in ("DEMO_CONFIRM", "FAKE_CAPTURE", "RECORD_NO_SCOUT"):
            os.environ.pop(name, None)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.tools, ignore_errors=True)
        super().tearDown()

    def run_main(self, *argv, **env):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(sys, "stdin", io.StringIO("")), mock.patch.dict(os.environ, env):
            rc = presenter.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def capture(self, mode="clean"):
        session.record_check("fixture-demo", True)
        return self.run_main("record", "fixture-demo", DEMO_CONFIRM="fixture-demo", FAKE_CAPTURE=mode)

    def test_a_terminal_take_needs_a_check_of_the_day(self):
        rc, _, err = self.run_main("record", "fixture-demo")
        self.assertEqual(rc, 2)
        self.assertIn("needs a `make demo check fixture-demo` that passed today", err)

    def test_a_plan_refusal_stops_before_the_prompt(self):
        session.record_check("fixture-demo", True)
        rc, out, err = self.run_main("record", "fixture-demo", FAKE_CAPTURE="plan-refuse")
        self.assertEqual(rc, 2)
        self.assertIn("may not type every Do command", err)
        self.assertNotIn("Type the demo id", out)

    def test_the_notice_shows_what_is_typed_and_allowed(self):
        session.record_check("fixture-demo", True)
        rc, out, err = self.run_main("record", "fixture-demo")
        self.assertEqual(rc, 2)
        self.assertIn("typed: 0:00  $ git log -1 --format=%h", out)
        self.assertIn("typed beyond the read-only allowlist (demo.yml record.allow): oc delete pod fixture -n fixture",
                      out)
        self.assertIn("DEMO_CONFIRM=fixture-demo", err)
        self.assertFalse(gif.recordings_dir().exists())

    def test_a_clean_capture_passes_the_gate_and_stops_for_the_transcript(self):
        rc, out, _ = self.capture()
        self.assertEqual(rc, 0, out)
        self.assertIn("Text gate passed", out)
        self.assertIn("make demo record fixture-demo render", out)
        take = presenter.latest_terminal_take("fixture-demo")
        self.assertTrue((take / textgate.TRANSCRIPT).is_file())
        self.assertFalse((take / "recording.webm").exists())             # nothing filmed before the review
        self.assertTrue(list(session.logs_dir().glob("fixture-demo-capture-*.log")))

    def test_a_hit_refuses_the_take(self):
        rc, out, _ = self.capture("jwt")
        self.assertEqual(rc, 1)
        self.assertIn("HIT transcript.txt:", out)
        self.assertIn(": JWT", out)
        self.assertNotIn("eyJzdWIi", out)
        self.assertIn("REFUSED by the text gate", out)

    def test_no_cast_is_the_capture_refusing_a_local_value(self):
        rc, out, _ = self.capture("nocast")
        self.assertEqual(rc, 1)
        self.assertIn("REFUSED by the capture: the session printed a real local value", out)

    def test_render_films_the_checked_take_once(self):
        rc, _, err = self.run_main("record", "fixture-demo", "render")
        self.assertEqual(rc, 2)
        self.assertIn("no captured session of fixture-demo", err)
        self.capture()
        built = mock.Mock()
        built.summary.return_value = ["GIF: fake"]
        with mock.patch.object(gif, "build", return_value=built) as build:
            rc, out, _ = self.run_main("record", "fixture-demo", "render")
        self.assertEqual(rc, 0, out)
        self.assertIn("GIF: fake", out)
        take = presenter.latest_terminal_take("fixture-demo")
        self.assertEqual(build.call_args[0][:2], ("fixture-demo", take))
        self.assertTrue((take / "recording.webm").is_file())
        rc, _, err = self.run_main("record", "fixture-demo", "render")
        self.assertIn("already filmed", err)

    def test_render_refuses_a_take_the_gate_did_not_pass(self):
        self.capture("jwt")
        rc, _, err = self.run_main("record", "fixture-demo", "render")
        self.assertEqual(rc, 2)
        self.assertIn("the text gate refused this take", err)


class BrowserRender(unittest.TestCase):
    def test_render_is_only_for_a_terminal_demo(self):
        out, err = io.StringIO(), io.StringIO()
        home = tempfile.mkdtemp(prefix="zuno-home-")
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                    mock.patch.dict(os.environ, {"HOME": home}):
                os.environ.pop("ZUNO_DEMO_ROOT", None)
                rc = presenter.main(["record", "open-webui", "render"])
        finally:
            shutil.rmtree(home, ignore_errors=True)
        self.assertEqual(rc, 2)
        self.assertIn("is recorded in a browser", err.getvalue())


if __name__ == "__main__":
    unittest.main()
