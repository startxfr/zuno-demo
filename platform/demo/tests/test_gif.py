"""The GIF of a demo recording (ADR-0617, WP-284): the cut list against the markers and the page, the ffmpeg command,
the size limit, and the guards of `make demo record` and `make demo gif`. No ffmpeg, podman or cluster is needed.

Run from the repository root:
    python3 platform/demo/tests/test_gif.py
"""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))

import gif  # noqa: E402
import presenter  # noqa: E402
import session  # noqa: E402

TIMES = ["0:00", "0:45", "1:45", "3:00", "4:15"]


def markers(**changes) -> dict:
    """A take shaped like the open-webui walkthrough's (contract of WP-284)."""
    at = {"login": 1.0, "home": 6.0, "q1-sent": 9.0, "q1-done": 15.0, "code-picked": 18.0, "q2-done": 30.0,
          "tools": 33.0, "end": 35.0}
    at.update(changes.pop("at", {}))
    data = {"demo": "open-webui", "persona": "sale-01", "viewport": {"width": 1280, "height": 800},
            "started": "2026-11-16T09:00:00+00:00",
            "markers": [{"name": n, "t": t, "png": f"{n}.png"} for n, t in at.items()],
            "motion_from": "q1-sent", "created": [{"kind": "chat", "id": "c-1"}], "cleaned": True,
            "owned": {"before": 3, "after": 3, "same": True}, "status": "pass", "detail": ""}
    data.update(changes)
    return data


def cut(*moments, **changes) -> dict:
    data = {"target_seconds": [1, 600], "width": 960, "fps": 10, "moments": list(moments)}
    data.update(changes)
    return data


def takes(**changes) -> dict:
    """A recording of two takes shaped like identity-personas' (ADR-0618): name -> its markers.json."""
    at = {"login": 1.0, "unifai": 5.0, "workspaces": 8.0, "webui": 12.0, "q-sent": 15.0, "q-done": 24.0, "end": 25.0}
    made = {}
    for name in ("consultant-02", "sale-01"):
        made[name] = markers(at=dict(at), demo="identity-personas", persona=name, take=name, motion_from="unifai",
                             created=[{"kind": "chat", "id": f"c-{name}"}], **changes.get(name, {}))
        made[name]["markers"] = sorted((m for m in made[name]["markers"] if m["name"] in at), key=lambda m: m["t"])
    return made


def write_takes(directory: pathlib.Path, recording: dict) -> None:
    """The files a recorder run of several takes leaves: takes.json and one sub-directory per take."""
    (directory / "takes.json").write_text(json.dumps({"demo": "identity-personas", "status": "pass", "takes": [
        {"name": name, "persona": m["persona"], "dir": name, "status": "pass", "detail": "PASS"} for name, m in recording.items()]}))
    for name, m in recording.items():
        (directory / name).mkdir()
        (directory / name / "markers.json").write_text(json.dumps(m))
        (directory / name / "recording.webm").write_bytes(b"webm")
        for marker in m["markers"]:
            (directory / name / marker["png"]).write_bytes(b"png")


TWO = [{"take": "consultant-02", "still": "workspaces", "hold": 4, "caption": "consultant-02: three workspaces"},
       {"take": "sale-01", "still": "workspaces", "hold": 4, "caption": "sale-01: two workspaces"},
       {"take": "consultant-02", "from": "q-sent", "to": "q-done", "fit": 6, "hold": 3, "caption": "Six tools"},
       {"take": "sale-01", "from": "q-sent", "to": "q-done", "fit": 6, "hold": 3, "caption": "Three tools"}]


def refused(test: unittest.TestCase, cut_list: dict, take: dict, needle: str, times=TIMES) -> None:
    with test.assertRaises(gif.CutError) as ctx:
        gif.plan("open-webui", cut_list, take, times)
    test.assertTrue(any(needle in r for r in ctx.exception.reasons), ctx.exception.reasons)


class CutList(unittest.TestCase):
    def test_the_open_webui_cut_list_fits_its_page_and_its_markers(self):
        cut_list = gif.load_cut_list(gif.cut_list_path("open-webui"))
        times = gif.page_times("open-webui")
        self.assertEqual(times, TIMES)
        # The first real take (2026-11-15, demo333): q1 answered in 2.96 s, q2 in 6.08 s.
        real = markers(at={"login": 1.0, "home": 8.28, "q1-sent": 10.36, "q1-done": 13.32, "code-picked": 14.65,
                           "q2-done": 20.73, "tools": 22.05, "end": 23.43})
        self.assertAlmostEqual(gif.plan("open-webui", cut_list, real, times).seconds, 42.92, places=2)
        for q1, q2 in ((6, 12), (3, 4), (40, 120), (120, 200)):   # fast, very fast and very slow answers
            take = markers(at={"q1-done": 9.0 + q1, "code-picked": 12.0 + q1, "q2-done": 12.0 + q1 + q2,
                               "tools": 15.0 + q1 + q2, "end": 17.0 + q1 + q2})
            p = gif.plan("open-webui", cut_list, take, times)
            self.assertTrue(40 <= p.seconds <= 60, f"{q1}/{q2}: {p.seconds}")
            self.assertTrue(all(m.seconds >= 2 for m in p.moments))
        self.assertEqual([m.marker or m.kind for m in p.moments],
                         ["login", "home", "motion", "code-picked", "motion", "tools", "end"])
        self.assertEqual((p.width, p.height, p.out_height, p.fps), (960, 600, 656, 10))

    def test_fit_sets_the_speed_within_1_and_16(self):
        p = gif.plan("open-webui", cut({"from": "q1-sent", "to": "q1-done", "fit": 3, "caption": "x"}), markers(), TIMES)
        self.assertAlmostEqual(p.moments[0].speed, 2.0)
        self.assertAlmostEqual(p.moments[0].seconds, 3.0)
        slow = gif.plan("open-webui", cut({"from": "q1-sent", "to": "q1-done", "fit": 10, "hold": 1, "caption": "x"}),
                        markers(), TIMES).moments[0]
        self.assertAlmostEqual(slow.speed, 0.6)              # a fast answer is slowed down to its fit...
        self.assertAlmostEqual(slow.seconds, 11.0)
        floor = gif.plan("open-webui", cut({"from": "q1-sent", "to": "q1-done", "fit": 20, "hold": 1, "caption": "x"}),
                         markers(), TIMES).moments[0]
        self.assertEqual(floor.speed, 0.5)                   # ...never under half speed: the moment is then shorter,
        self.assertAlmostEqual(floor.seconds, 6 / 0.5 + 1)   # and `fit` never freezes a frame
        fast = gif.plan("open-webui", cut({"from": "q1-sent", "to": "end", "fit": 1, "hold": 1, "caption": "x"}),
                        markers(), TIMES)
        self.assertEqual(fast.moments[0].speed, 16.0)
        self.assertAlmostEqual(fast.moments[0].seconds, 26 / 16 + 1)
        refused(self, cut({"from": "q1-sent", "to": "end", "fit": 1, "caption": "x"}), markers(), "at least 2 s")

    def test_a_fixed_speed_stays_allowed(self):
        p = gif.plan("open-webui", cut({"from": "code-picked", "to": "q2-done", "speed": 4,
                                        "hold": 1, "caption": "x"}), markers(), TIMES)
        self.assertAlmostEqual(p.moments[0].seconds, 12 / 4 + 1)

    def test_refusals(self):
        still = {"still": "home", "hold": 3, "caption": "x"}
        refused(self, cut({"still": "nowhere", "hold": 3, "caption": "x"}), markers(), "not in markers.json")
        refused(self, cut({"from": "q1-done", "to": "q1-sent", "fit": 3, "caption": "x"}), markers(), "is not after")
        refused(self, cut({"still": "home", "hold": 1.5, "caption": "x"}), markers(), "at least 2 s")
        refused(self, cut({"from": "q1-sent", "to": "q1-done", "speed": 4, "caption": "x"}), markers(), "at least 2 s")
        refused(self, cut({"from": "q1-sent", "to": "q1-done", "speed": 20, "caption": "x"}), markers(), "0.5 to 16")
        refused(self, cut({"from": "q1-sent", "to": "q1-done", "speed": 0.3, "caption": "x"}), markers(), "0.5 to 16")
        refused(self, cut({"from": "q1-sent", "to": "q1-done", "caption": "x"}), markers(), "`fit` or `speed`")
        refused(self, cut({"from": "q1-sent", "to": "q1-done", "fit": 3, "speed": 2, "caption": "x"}), markers(),
                "`fit` or `speed`")
        refused(self, cut({"still": "home", "hold": 3}), markers(), "`caption` is required")
        refused(self, cut({"still": "home", "hold": 3, "caption": "x" * 61}), markers(), "at most 60")
        gif.plan("open-webui", cut({"still": "home", "hold": 3, "caption": "x" * 60}), markers(), TIMES)
        refused(self, cut({"still": "home", "hold": 3, "step": "0:50", "caption": "x"}), markers(), "step 0:50")
        refused(self, cut({"still": "home", "hold": 3, "fit": 3, "caption": "x"}), markers(), "takes only")
        refused(self, cut({"still": "home", "hold": 3, "colour": "red", "caption": "x"}), markers(), "unknown key")
        refused(self, cut(still, gif_name="x"), markers(), "unknown key(s) gif_name")
        refused(self, cut(still, target_seconds=[40, 60]), markers(), "outside 40-60 s")
        refused(self, cut(still, width=2000), markers(), "`width`")
        refused(self, cut(still, fps=30), markers(), "`fps`")
        refused(self, cut(), markers(), "non-empty list")

    def test_no_motion_before_motion_from(self):
        """The take holds the Keycloak sign-in between login and home: only stills may show that part."""
        refused(self, cut({"from": "login", "to": "home", "fit": 3, "caption": "x"}), markers(), "cannot start before")
        refused(self, cut({"from": "home", "to": "q1-done", "fit": 3, "caption": "x"}), markers(), "cannot start before")
        gif.plan("open-webui", cut({"still": "login", "hold": 3, "caption": "x"}), markers(), TIMES)
        gif.plan("open-webui", cut({"from": "q1-sent", "to": "q1-done", "fit": 3, "caption": "x"}), markers(), TIMES)
        free = markers()
        del free["motion_from"]
        gif.plan("open-webui", cut({"from": "login", "to": "home", "fit": 3, "caption": "x"}), free, TIMES)
        refused(self, cut({"still": "login", "hold": 3, "caption": "x"}), markers(motion_from="nowhere"),
                "`motion_from` 'nowhere' is not a marker")

    def test_an_unquoted_step_time_is_read_as_yaml_base_60(self):
        p = gif.plan("open-webui", cut({"still": "home", "hold": 3, "step": 45, "caption": "x"}), markers(), TIMES)
        self.assertEqual(p.moments[0].step, "0:45")

    def test_a_failed_or_dirty_take_is_refused(self):
        still = {"still": "home", "hold": 3, "caption": "x"}
        refused(self, cut(still), markers(status="fail", detail="no answer"), "did not pass")
        refused(self, cut(still), markers(cleaned=False), "did not clean what it created (chat c-1)")
        refused(self, cut(still), markers(owned={"before": 3, "after": 4, "same": False}), "3 before, 4 after")
        # A take that showed a node name or a private address is refused even if its status says pass.
        refused(self, cut(still), markers(private_addresses={"flagged": True, "count": 2, "at": ["q-done"]}),
                "showed node names or private IP addresses (at q-done)")
        gif.plan("open-webui", cut(still), markers(private_addresses={"flagged": False, "count": 0, "at": []}), TIMES)
        refused(self, cut(still), markers(owned=None), "does not say what the persona owns")
        gif.plan("open-webui", cut(still), markers(created=[], cleaned=None), TIMES)    # nothing created
        refused(self, cut(still), markers(demo="dify"), "not 'open-webui'")
        back = markers()
        back["markers"][3]["t"] = 2.0
        refused(self, cut(still), back, "goes back in time")
        refused(self, cut(still), markers(viewport={}), "viewport")


class Ffmpeg(unittest.TestCase):
    def setUp(self):
        self.take = markers()
        self.plan = gif.plan("open-webui", gif.load_cut_list(gif.cut_list_path("open-webui")), self.take, TIMES)
        self.argv = gif.ffmpeg_argv(self.plan, self.take, "open-webui.gif")

    def test_one_input_per_moment_in_order(self):
        inputs = [self.argv[i + 1] for i, a in enumerate(self.argv) if a == "-i"]
        self.assertEqual(inputs, ["/rec/login.png", "/rec/home.png", "/rec/recording.webm", "/rec/code-picked.png",
                                  "/rec/recording.webm", "/rec/tools.png", "/rec/end.png"])
        joined = " ".join(self.argv)
        self.assertIn("-ss 9.000 -t 6.000 -i /rec/recording.webm", joined)       # q1: seek, never buffer the take
        self.assertIn("-loop 1 -framerate 10 -t 3.000 -i /rec/login.png", joined)
        self.assertEqual(self.argv[-3:], ["-loop", "0", "/rec/open-webui.gif"])

    def test_filter_graph(self):
        graph = self.argv[self.argv.index("-filter_complex") + 1]
        self.assertIn("scale=960:600:flags=lanczos", graph)
        self.assertIn("pad=960:656:0:0:color=black", graph)                       # the caption band under the picture
        self.assertIn("y=h-56+(56-text_h)/2", graph)                              # the caption sits in that band
        self.assertNotIn("box=1", graph)                                          # never an overlay on the picture
        self.assertIn("setpts=(PTS-STARTPTS)/1.0000,", graph)                     # q1: 6 s fit to 6 s
        self.assertIn("tpad=stop_mode=clone:stop_duration=3.000", graph)          # the hold only
        self.assertIn("textfile=/rec/.gif-captions/01.txt", graph)
        self.assertIn(gif.FONT, graph)
        self.assertIn("concat=n=7:v=1:a=0", graph)
        self.assertIn("palettegen=stats_mode=diff", graph)
        self.assertIn("paletteuse=dither=bayer", graph)
        self.assertNotIn("Zuno picks", graph)                                     # captions go through files

    def test_podman_mounts_the_take_only_and_has_no_network(self):
        argv = gif.podman(pathlib.Path("/tmp/take"), ["ffmpeg"])
        self.assertEqual(argv[:6], ["podman", "run", "--rm", "--network", "none", "-v"])
        self.assertEqual(argv[6], "/tmp/take:/rec:Z")
        self.assertIn(gif.IMAGE, argv)


class Build(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="zuno-gif-test-"))
        take = markers()
        (self.dir / "markers.json").write_text(json.dumps(take))
        (self.dir / "recording.webm").write_bytes(b"webm")
        for m in take["markers"]:
            (self.dir / m["png"]).write_bytes(b"png")
        self.cut = gif.load_cut_list(gif.cut_list_path("open-webui"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def fake_ffmpeg(self, size):
        def run(argv, **kwargs):
            with open(self.dir / "open-webui.gif", "wb") as handle:
                handle.truncate(size)
            return subprocess.CompletedProcess(argv, 0, stdout="")
        return run

    def build(self, size, seconds=48.0):
        with mock.patch.object(gif.shutil, "which", return_value="/usr/bin/podman"), \
                mock.patch.object(gif, "_duration", return_value=seconds):
            return gif.build("open-webui", self.dir, self.cut, times=TIMES, runner=self.fake_ffmpeg(size),
                             cut_path=gif.cut_list_path("open-webui"))

    def test_built_with_captions_and_a_summary(self):
        built = self.build(3 * 1048576)
        self.assertEqual(built.path, self.dir / "open-webui.gif")
        self.assertEqual((self.dir / ".gif-captions/02.txt").read_text(), "0:00  Zuno picks the model")
        summary = "\n".join(built.summary())
        self.assertIn("3.0 MB", summary)
        self.assertIn("48.0 s by ffprobe", summary)
        self.assertIn("960x656 (picture 960x600 + caption band 56)", summary)
        record = json.loads((self.dir / "open-webui.gif.json").read_text())
        self.assertTrue(record["moments"])
        # Provenance for the publication record: the take, its start, and the cut list's git blob.
        self.assertEqual(record["take"], self.dir.name)
        self.assertEqual(record["started"], "2026-11-16T09:00:00+00:00")
        self.assertEqual(record["cut_list"], "ansible/demos/open-webui/gif.yml")
        blob = subprocess.run(["git", "hash-object", str(gif.cut_list_path("open-webui"))], stdout=subprocess.PIPE,
                              universal_newlines=True, cwd=str(ROOT))
        if blob.returncode == 0:
            self.assertEqual(record["cut_list_blob"], blob.stdout.strip())
        self.assertRegex(record["cut_list_blob"], r"^[0-9a-f]{40}$")

    def test_over_8_mb_is_an_error(self):
        with self.assertRaises(gif.CutError) as ctx:
            self.build(gif.MAX_BYTES + 1)
        self.assertIn("over the 8 MB limit", ctx.exception.reasons[0])

    def test_a_duration_outside_the_target_is_an_error(self):
        with self.assertRaises(gif.CutError) as ctx:
            self.build(1048576, seconds=75.0)
        self.assertIn("ffprobe says 75.0 s", ctx.exception.reasons[0])

    def test_a_missing_file_is_refused_before_ffmpeg(self):
        (self.dir / "tools.png").unlink()
        with self.assertRaises(gif.CutError) as ctx:
            self.build(1)
        self.assertIn("missing tools.png", ctx.exception.reasons[0])

    def test_newest_recording(self):
        base = self.dir / "recordings"
        for name in ("open-webui-20261116-090000", "open-webui-20261116-100000", "open-webui-x", "dify-20261117-0"):
            (base / name).mkdir(parents=True)
            (base / name / "markers.json").write_text("{}")
        (base / "open-webui-20261117-080000").mkdir()                             # no markers.json: an aborted take
        self.assertEqual(gif.latest_recording("open-webui", base).name, "open-webui-20261116-100000")
        self.assertIsNone(gif.latest_recording("kagent", base))


class Verbs(unittest.TestCase):
    """`record` refuses before any cluster call; `gif` is offline. Both run with a temporary HOME."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="zuno-demo-test-")
        self.tools = pathlib.Path(tempfile.mkdtemp(prefix="zuno-demo-tools-"))
        (self.tools / "record.sh").write_text("#!/bin/sh\nexit 0\n")
        (self.tools / "open-webui.mjs").write_text("export const persona = 'sale-01';\n")
        (self.tools / "_helpers.mjs").write_text("export const helper = 1;\n")
        env = {"HOME": self.home, "KUBECONFIG": str(pathlib.Path(self.home) / "none")}
        self.patches = [mock.patch.dict(os.environ, env), mock.patch.dict(os.environ, {}, clear=False)]
        os.environ.pop("DEMO_CONFIRM", None)
        for p in self.patches:
            p.start()
        os.environ.pop("DEMO_CONFIRM", None)
        self.recorder = mock.patch.multiple(presenter, RECORDER=self.tools / "record.sh", WALKTHROUGHS=self.tools)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.tools, ignore_errors=True)

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(sys, "stdin", io.StringIO("")):
            rc = presenter.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_record_is_refused_during_a_freeze(self):
        session.freeze_on()
        rc, _, err = self.run_main("record", "open-webui")
        self.assertEqual(rc, 2)
        self.assertIn("`record` is refused during a freeze", err)

    def test_record_needs_its_recorder_and_walkthrough(self):
        with mock.patch.multiple(presenter, RECORDER=self.tools / "record.sh", WALKTHROUGHS=self.tools / "absent"):
            rc, _, err = self.run_main("record", "open-webui")
        self.assertEqual(rc, 2)
        self.assertIn("open-webui.mjs is missing", err)

    def test_record_needs_a_check_that_passed_today(self):
        with self.recorder:
            rc, _, err = self.run_main("record", "open-webui")
            self.assertEqual(rc, 2)
            self.assertIn("none is recorded on this workstation", err)
            session.record_check("open-webui", False)
            rc, _, err = self.run_main("record", "open-webui")
            self.assertIn("the last one FAILED", err)
            session.record_check("open-webui", True)
            data = session.last_check("open-webui")
            data["date"] = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
            session._write_json(session.checks_dir() / "open-webui.json", data)
            rc, _, err = self.run_main("record", "open-webui")
            self.assertIn("the last one passed on", err)
            self.assertIn("make demo start open-webui", err)

    def current_sha(self) -> str:
        """The contract with record.mjs: helpers then walkthrough, each `path NUL bytes NUL`."""
        import hashlib
        digest = hashlib.sha256()
        for name in ("_helpers.mjs", "open-webui.mjs"):
            digest.update(f"evaluations/browser/walkthroughs/{name}".encode() + b"\0"
                          + (self.tools / name).read_bytes() + b"\0")
        return digest.hexdigest()

    def scout(self, status="done", sha=None, changes=(), stamp="20261116-090000"):
        directory = gif.recordings_dir() / f"open-webui-{stamp}-scout"
        directory.mkdir(parents=True)
        current = self.current_sha()
        (directory / "scout.json").write_text(json.dumps({
            "demo": "open-webui", "status": status, "walkthrough_sha256": sha or current, "changes": list(changes),
            "when": "2026-11-16T09:00:00Z", "detail": "" if status == "done" else "the picker was not found"}))
        return directory

    def test_record_needs_a_finished_scout_of_the_current_walkthrough(self):
        session.record_check("open-webui", True)
        with self.recorder:
            rc, _, err = self.run_main("record", "open-webui")
            self.assertEqual(rc, 2)
            self.assertIn("no scout of open-webui", err)
            self.assertIn("run `make demo scout open-webui` first", err)
            self.scout(status="fail", stamp="20261116-080000")
            rc, _, err = self.run_main("record", "open-webui")
            self.assertIn("did not finish (status 'fail': the picker was not found)", err)
            self.scout(sha="0" * 64, stamp="20261116-090000")
            rc, _, err = self.run_main("record", "open-webui")
            self.assertIn("another version of the walkthrough", err)
            self.scout(stamp="20261116-100000")
            (self.tools / "_helpers.mjs").write_text("export const helper = 2;\n")      # a helper changed since
            rc, _, err = self.run_main("record", "open-webui")
            self.assertIn("another version of the walkthrough", err)

    def test_record_no_scout_override_names_the_demo_and_says_so(self):
        session.record_check("open-webui", True)
        with self.recorder:
            with mock.patch.dict(os.environ, {"RECORD_NO_SCOUT": "dify"}):
                rc, _, err = self.run_main("record", "open-webui")
            self.assertIn("RECORD_NO_SCOUT='dify' does not name 'open-webui'", err)
            with mock.patch.dict(os.environ, {"RECORD_NO_SCOUT": "open-webui"}):
                rc, out, err = self.run_main("record", "open-webui")
            self.assertIn("SCOUT GATE SKIPPED by RECORD_NO_SCOUT=open-webui", out)
            self.assertIn("controls the take may switch: unknown (no scout)", out)
            self.assertIn("DEMO_CONFIRM=open-webui", err)                    # the confirmation still comes

    def fake_scout_recorder(self, status="done", rc=0):
        """A record.sh that writes the scout.json of a contract scout run into its 2nd argument."""
        script = self.tools / "record.sh"
        script.write_text("#!/bin/sh\n"
                          f"[ \"$3\" = --scout ] || exit 9\n"
                          "echo \"recording: $2\"\n"
                          "cat > \"$2/scout.json\" <<'JSON'\n"
                          + json.dumps({"demo": "open-webui", "status": status, "changes": [],
                                        "detail": "2 steps" if status == "done" else "failed: picker",
                                        "steps": [{"step": "home", "ok": True, "png": "scout-home.png"},
                                                  {"step": "picker", "ok": status == "done",
                                                   "error": None if status == "done" else "no picker"}]})
                          + "\nJSON\n"
                          f"echo \"SCOUT: {status}\"\nexit {rc}\n")
        script.chmod(0o755)
        kubeconfig = pathlib.Path(self.home) / "kubeconfig"
        kubeconfig.write_text("apiVersion: v1\n")
        return kubeconfig

    def test_scout_is_refused_during_a_freeze(self):
        session.freeze_on()
        rc, _, err = self.run_main("scout", "open-webui")
        self.assertEqual(rc, 2)
        self.assertIn("`scout` is refused during a freeze", err)

    def test_scout_asks_for_the_id_with_a_sign_in_only_notice(self):
        with self.recorder:
            rc, out, err = self.run_main("scout", "open-webui")
        self.assertEqual(rc, 2)
        self.assertIn("a sign-in as sale-01, then the menus the walkthrough uses: no prompt sent, no model call, "
                      "nothing created", out)
        self.assertIn("DEMO_CONFIRM=open-webui", err)
        self.assertFalse(gif.recordings_dir().exists())                     # refused before any directory

    def test_scout_needs_no_check_of_the_day_and_reports_its_steps(self):
        kubeconfig = self.fake_scout_recorder()
        with self.recorder, mock.patch.dict(os.environ, {"DEMO_CONFIRM": "open-webui", "KUBECONFIG": str(kubeconfig)}):
            rc, out, _ = self.run_main("scout", "open-webui")
        self.assertEqual(rc, 0, out)
        self.assertIn("ok     home  scout-home.png", out)
        self.assertIn("scout done: 2 steps (exit 0)", out)
        self.assertIn("Next: make demo record open-webui", out)
        scouts = [p.name for p in gif.recordings_dir().iterdir()]
        self.assertEqual(len(scouts), 1)
        self.assertRegex(scouts[0], r"^open-webui-\d{8}-\d{6}-scout$")
        self.assertEqual(presenter.latest_scout("open-webui")["status"], "done")
        logs = list(session.logs_dir().glob("open-webui-scout-*.log"))
        self.assertEqual(len(logs), 1)
        self.assertIn("SCOUT: done", logs[0].read_text())

    def test_a_failed_scout_says_which_step(self):
        kubeconfig = self.fake_scout_recorder(status="fail", rc=1)
        with self.recorder, mock.patch.dict(os.environ, {"DEMO_CONFIRM": "open-webui", "KUBECONFIG": str(kubeconfig)}):
            rc, out, _ = self.run_main("scout", "open-webui")
        self.assertEqual(rc, 1)
        self.assertIn("FAILED picker  no picker", out)
        self.assertIn("scout fail: failed: picker (exit 1)", out)

    def test_the_walkthrough_hash_is_the_recorders(self):
        with self.recorder:
            self.assertEqual(presenter.walkthrough_sha256("open-webui", ROOT), self.current_sha())
        real = ROOT / "evaluations/browser/walkthroughs"
        if (real / "_helpers.mjs").is_file():
            self.assertRegex(presenter.walkthrough_sha256("open-webui", ROOT), r"^[0-9a-f]{64}$")

    def test_record_asks_for_the_id_and_says_the_chat_is_deleted(self):
        session.record_check("open-webui", True)
        self.scout(changes=["tools switch"])
        with self.recorder:
            rc, out, err = self.run_main("record", "open-webui")
            self.assertEqual(rc, 2)
            self.assertIn("DEMO_CONFIRM=open-webui", err)
            self.assertIn("the chat it creates is deleted at the end", out)
            self.assertIn("controls the take may switch: tools switch", out)
            with mock.patch.dict(os.environ, {"DEMO_CONFIRM": "open-webui"}):
                rc, out, err = self.run_main("record", "open-webui")
            self.assertEqual(rc, 2)
            self.assertIn("No kubeconfig", err)                          # still refused before anything runs
        self.assertEqual([p.name for p in gif.recordings_dir().iterdir() if not p.name.endswith("-scout")], [])

    def without_cut_list(self, demo_id: str):
        """`demo_id` as a scenario with no cut list, whatever the repository holds today."""
        real = gif.cut_list_path
        return mock.patch.object(gif, "cut_list_path", side_effect=lambda i, root=None: (
            pathlib.Path(self.home, "no-such-gif.yml") if i == demo_id else real(i, root)))

    def assembled_demo(self, demo_id: str):
        """`demo_id` as a demo whose demo.yml says `record: {kind: assembled}`."""
        real = presenter.load_manifest
        return mock.patch.object(presenter, "load_manifest", side_effect=lambda d: (
            dict(real(d), record={"kind": "assembled"}) if pathlib.Path(d).name == demo_id else real(d)))

    def test_record_and_gif_take_a_scenario_with_a_cut_list(self):
        rc, _, err = self.run_main("record", "three-experiences")
        self.assertEqual((rc, "is a workshop" in err), (2, True))
        with self.without_cut_list("dify"):
            rc, _, err = self.run_main("gif", "dify")
        self.assertEqual((rc, "has no cut list" in err), (2, True))

    def test_an_assembled_take_is_neither_scouted_nor_recorded(self):
        with self.assembled_demo("open-webui"):
            for verb in ("scout", "record"):
                rc, _, err = self.run_main(verb, "open-webui")
                self.assertEqual(rc, 2, verb)
                self.assertIn(f"assembled by hand from media that already exist (ansible/demos/open-webui/gif.yml "
                              f"says which): there is nothing to {verb}", err)
                rc, out, _ = self.run_main("--complete", verb)
                self.assertNotIn("open-webui", out.split(), verb)
                self.assertIn("dify", out.split(), verb)
            rc, out, _ = self.run_main("--complete", "gif")
            self.assertIn("open-webui", out.split())                      # it is cut again with `make demo gif`
            rc, out, _ = self.run_main("gif", "open-webui")
            self.assertIn("No recording of open-webui", out)              # gif runs as for any demo

    def test_gif_without_a_recording(self):
        rc, out, _ = self.run_main("gif", "open-webui")
        self.assertEqual(rc, 1)
        self.assertIn("No recording of open-webui", out)

    def test_check_results_are_kept_per_demo(self):
        self.assertFalse(session.check_passed_today("open-webui"))
        session.record_check("open-webui", True, source="rehearse 5")
        self.assertTrue(session.check_passed_today("open-webui"))
        self.assertEqual(session.last_check("open-webui")["source"], "rehearse 5")
        self.assertEqual(session.checks_dir(), pathlib.Path(self.home, ".cache/zuno/demo/checks"))

    def test_completion_offers_only_demos_with_a_cut_list(self):
        for verb in ("scout", "record", "gif"):
            with self.without_cut_list("dify"):
                rc, out, _ = self.run_main("--complete", verb)
            self.assertIn("open-webui", out.split(), verb)
            self.assertNotIn("dify", out.split(), verb)                   # no cut list
        rc, out, _ = self.run_main("--complete", "scout")
        self.assertNotIn("vault-pki", out.split())                         # a terminal demo is not scouted
        rc, _, err = self.run_main("scout", "vault-pki")
        self.assertEqual(rc, 2)
        self.assertIn("is a terminal demo", err)


class SeveralTakes(unittest.TestCase):
    """A recording of several takes, one per persona (identity-personas): a moment names its take."""

    def plan(self, moments=None, recording=None):
        recording = recording or takes()
        return gif.plan("identity-personas", cut(*(moments or TWO)), next(iter(recording.values())), None, takes=recording)

    def refused(self, needle, moments=None, recording=None):
        with self.assertRaises(gif.CutError) as ctx:
            self.plan(moments, recording)
        self.assertTrue(any(needle in r for r in ctx.exception.reasons), ctx.exception.reasons)

    def test_each_moment_is_cut_from_its_own_take(self):
        p = self.plan()
        self.assertEqual([m.take for m in p.moments], ["consultant-02", "sale-01", "consultant-02", "sale-01"])
        self.assertEqual(p.moments[2].label(), "consultant-02: 15.0-24.0 s x1.5")
        argv = gif.ffmpeg_argv(p, {}, "identity-personas.gif", takes())
        inputs = [argv[i + 1] for i, a in enumerate(argv) if a == "-i"]
        self.assertEqual(inputs, ["/rec/consultant-02/workspaces.png", "/rec/sale-01/workspaces.png",
                                  "/rec/consultant-02/recording.webm", "/rec/sale-01/recording.webm"])
        self.assertEqual(argv[-1], "/rec/identity-personas.gif")

    def test_a_moment_must_name_one_of_the_takes(self):
        self.refused("moment 1: `take` must name one of the recording's takes (consultant-02, sale-01)",
                     [dict(TWO[0], take="ai-ops-01")] + TWO[1:])
        self.refused("moment 2: `take` must name one of the recording's takes", [TWO[0], {k: v for k, v in TWO[1].items() if k != "take"}])

    def test_a_single_take_refuses_the_key(self):
        refused(self, cut({"take": "sale-01", "still": "home", "hold": 3, "caption": "x"}), markers(),
                "`take` is for a recording of several takes")

    def test_each_take_is_checked_on_its_own(self):
        self.refused("take sale-01: the recording did not pass", recording=takes(**{"sale-01": {"status": "fail", "detail": "x"}}))
        self.refused("take sale-01: the take did not clean what it created (chat c-sale-01)",
                     recording=takes(**{"sale-01": {"cleaned": False}}))
        self.refused("take consultant-02: what the persona owns changed during the take",
                     recording=takes(**{"consultant-02": {"owned": {"before": 1, "after": 2, "same": False}}}))
        # No motion before the take's own `motion_from`.
        self.refused("moment 1: a motion segment cannot start before `unifai`",
                     [{"take": "sale-01", "from": "login", "to": "unifai", "fit": 3, "caption": "x"}])

    def test_the_takes_share_one_viewport(self):
        self.refused("the takes do not share one viewport (consultant-02 1280x800, sale-01 1024x768)",
                     recording=takes(**{"sale-01": {"viewport": {"width": 1024, "height": 768}}}))

    def test_built_from_the_sub_directories_and_recorded_with_its_takes(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp) / "identity-personas-20261116-010000"
            directory.mkdir()
            write_takes(directory, takes())
            self.assertEqual(list(gif.load_takes(directory)), ["consultant-02", "sale-01"])
            self.assertEqual(gif.latest_recording("identity-personas", pathlib.Path(tmp)), directory)

            def ffmpeg(argv, **kwargs):
                (directory / "identity-personas.gif").write_bytes(b"x" * 1024)
                return subprocess.CompletedProcess(argv, 0, stdout="")
            with mock.patch.object(gif.shutil, "which", return_value="/usr/bin/podman"), \
                    mock.patch.object(gif, "_duration", return_value=26.0):
                gif.build("identity-personas", directory, cut(*TWO), runner=ffmpeg)
            record = json.loads((directory / "identity-personas.gif.json").read_text())
            self.assertEqual([t["name"] for t in record["takes"]], ["consultant-02", "sale-01"])
            self.assertEqual(record["takes"][1]["created"], [{"kind": "chat", "id": "c-sale-01"}])
            self.assertEqual([m["take"] for m in record["moments"]], ["consultant-02", "sale-01", "consultant-02", "sale-01"])
            self.assertEqual(record["take"], directory.name)
            # The publication record reads `created` and `cleaned`: the whole recording's, not the first take's.
            self.assertEqual(record["created"], [{"kind": "chat", "id": "c-consultant-02"}, {"kind": "chat", "id": "c-sale-01"}])
            self.assertIs(record["cleaned"], True)
            # A newer scout of several takes (it holds a takes.json too) is not "the newest recording".
            scout = pathlib.Path(tmp) / "identity-personas-20261116-020000-scout"
            scout.mkdir()
            (scout / "takes.json").write_text("{}")
            self.assertEqual(gif.latest_recording("identity-personas", pathlib.Path(tmp)), directory)
            # A file of one take missing: refused before ffmpeg, named with its take.
            (directory / "sale-01" / "recording.webm").unlink()
            with mock.patch.object(gif.shutil, "which", return_value="/usr/bin/podman"), self.assertRaises(gif.CutError) as ctx:
                gif.build("identity-personas", directory, cut(*TWO), runner=ffmpeg)
            self.assertIn("missing sale-01/recording.webm", ctx.exception.reasons[0])

    def test_the_guard_notice_names_every_persona_of_a_walkthrough_with_takes(self):
        self.assertEqual(presenter.walkthrough_persona("identity-personas", ROOT), "consultant-02 then as sale-01")
        self.assertEqual(presenter.walkthrough_persona("open-webui", ROOT), "sale-01")

    def test_the_identity_personas_cut_list_fits_its_page_and_two_takes(self):
        cut_list = gif.load_cut_list(gif.cut_list_path("identity-personas"))
        recording = takes()
        p = gif.plan("identity-personas", cut_list, next(iter(recording.values())), gif.page_times("identity-personas"), takes=recording)
        self.assertEqual(len(p.moments), 6)
        self.assertTrue(40 <= p.seconds <= 60, p.seconds)
        self.assertEqual({m.take for m in p.moments}, {"consultant-02", "sale-01"})

    def test_a_single_take_recording_has_no_takes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(gif.load_takes(pathlib.Path(tmp)))


VIDEO_BYTES, FIRST_BYTES, EDIT_BYTES = b"mp4 of the fallback", b"png of the frame at 0.1 s", b"png of the edit"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assembled(**changes) -> dict:
    """A take assembled by hand from a recorded fallback (world-model, WP-290): no recorder run, no persona; the
    video is a copy of the original, the stills are frames taken out of it."""
    original = "~/demo-fallback/fallback.mp4"
    data = {"demo": "open-webui", "kind": "assembled", "viewport": {"width": 1280, "height": 720},
            "started": "2026-11-08", "status": "pass", "detail": "", "created": [], "cleaned": None,
            "video": "fallback.mp4",
            "markers": [{"name": "first", "t": 0.1, "png": "first.png"}, {"name": "walk-end", "t": 8.0},
                        {"name": "edit", "t": 12.41, "png": "edit.png"}],
            "source": [{"path": original, "sha256": sha(VIDEO_BYTES)},
                       {"path": original, "sha256": sha(VIDEO_BYTES), "file": "first.png",
                        "altered": {"sha256": sha(FIRST_BYTES), "how": "frame at 0.100 s, taken out by ffmpeg"}},
                       {"path": original, "sha256": sha(VIDEO_BYTES), "file": "edit.png",
                        "altered": {"sha256": sha(EDIT_BYTES), "how": "frame at 12.410 s, taken out by ffmpeg"}}]}
    data.update(changes)
    return data


WALK = [{"still": "first", "hold": 3, "caption": "x"},
        {"from": "first", "to": "walk-end", "speed": 1, "caption": "x"},
        {"still": "edit", "hold": 3, "caption": "x"}]


class Assembled(unittest.TestCase):
    """A take made by hand from media that already exist (WP-290): it says what it was made from, and is cut only
    from those files, checked by SHA-256."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="zuno-gif-assembled-"))
        self.take = assembled()
        (self.dir / "markers.json").write_text(json.dumps(self.take))
        for name, data in (("fallback.mp4", VIDEO_BYTES), ("first.png", FIRST_BYTES), ("edit.png", EDIT_BYTES)):
            (self.dir / name).write_bytes(data)
        self.cut = cut(*WALK)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def build(self, ran: list):
        def run(argv, **kwargs):
            ran.append(argv)
            (self.dir / "open-webui.gif").write_bytes(b"gif")
            return subprocess.CompletedProcess(argv, 0, stdout="")
        with mock.patch.object(gif.shutil, "which", return_value="/usr/bin/podman"), \
                mock.patch.object(gif, "_duration", return_value=14.0):
            return gif.build("open-webui", self.dir, self.cut, times=TIMES, runner=run)

    def test_no_persona_nothing_created(self):
        p = gif.plan("open-webui", self.cut, self.take, TIMES)
        self.assertEqual([m.kind for m in p.moments], ["still", "motion", "still"])
        refused(self, self.cut, assembled(created=[{"kind": "chat", "id": "1"}]), "an assembled take creates nothing")
        refused(self, self.cut, assembled(cleaned=True), "an assembled take creates nothing")
        refused(self, self.cut, assembled(kind="pasted"), "unknown take kind 'pasted'")

    def test_without_source_it_is_refused(self):
        for source in (None, [], "~/demo-fallback/fallback.mp4"):
            take = assembled(source=source)
            if source is None:
                del take["source"]
            refused(self, self.cut, take, "an assembled take needs `source`")

    def test_malformed_sources_are_refused(self):
        def source(**item):
            entry = {"path": "~/demo-fallback/fallback.mp4", "sha256": sha(VIDEO_BYTES)}
            entry.update(item)
            return assembled(source=[{k: v for k, v in entry.items() if v is not None}])
        refused(self, self.cut, source(sha256="abc"), "64 lower-case hex")
        refused(self, self.cut, source(sha256=sha(VIDEO_BYTES).upper()), "64 lower-case hex")
        refused(self, self.cut, source(path=None), "`path` names the original")
        refused(self, self.cut, source(file="../fallback.mp4"), "`file` is a plain file name")
        refused(self, self.cut, source(altered={"sha256": sha(FIRST_BYTES)}), "`altered` is {sha256, how}")
        refused(self, self.cut, source(altered={"sha256": "x", "how": "crop"}), "`altered` is {sha256, how}")
        refused(self, self.cut, source(note="hand-made"), "takes only path, sha256, file and altered")
        twice = assembled()
        twice["source"].append(dict(twice["source"][0]))
        refused(self, self.cut, twice, "fallback.mp4 is listed twice")

    def test_every_file_a_moment_reads_is_a_source(self):
        refused(self, self.cut, assembled(source=assembled()["source"][:1]), "first.png is not a source")
        refused(self, cut(WALK[1]), assembled(source=assembled()["source"][1:]), "fallback.mp4 is not a source")

    def test_the_video_is_a_plain_name_played_by_motion_moments(self):
        argv = gif.ffmpeg_argv(gif.plan("open-webui", self.cut, self.take, TIMES), self.take, "open-webui.gif")
        inputs = [argv[i + 1] for i, a in enumerate(argv) if a == "-i"]
        self.assertEqual(inputs, ["/rec/first.png", "/rec/fallback.mp4", "/rec/edit.png"])
        for video in ("../fallback.mp4", "sub/fallback.mp4", "", "..", 3):
            refused(self, self.cut, assembled(video=video), "must be a plain file name")
        browser = gif.ffmpeg_argv(gif.plan("open-webui", cut({"from": "q1-sent", "to": "q1-done", "fit": 3,
                                                              "caption": "x"}), markers(), TIMES), markers(), "x.gif")
        self.assertIn("/rec/recording.webm", browser)                           # a recorder take: unchanged

    def test_built_from_its_sources_and_recorded_with_them(self):
        ran = []
        self.build(ran)
        self.assertEqual(len(ran), 1)
        record = json.loads((self.dir / "open-webui.gif.json").read_text())
        self.assertEqual(record["kind"], "assembled")
        self.assertEqual(record["source"], self.take["source"])
        self.assertEqual(record["source"][0]["path"], "~/demo-fallback/fallback.mp4")
        self.assertEqual((record["created"], record["cleaned"]), ([], None))

    def test_a_file_that_is_not_its_source_is_refused_before_ffmpeg(self):
        (self.dir / "edit.png").write_bytes(b"another picture")
        ran = []
        with self.assertRaises(gif.CutError) as ctx:
            self.build(ran)
        self.assertEqual(ran, [])
        self.assertIn("edit.png: its SHA-256", ctx.exception.reasons[0])
        self.assertIn("is not the recorded " + sha(EDIT_BYTES)[:16], ctx.exception.reasons[0])
        # The copy of the video is checked against the original's SHA-256 (a copy is not altered).
        (self.dir / "edit.png").write_bytes(EDIT_BYTES)
        (self.dir / "fallback.mp4").write_bytes(b"re-encoded")
        with self.assertRaises(gif.CutError) as ctx:
            self.build(ran)
        self.assertIn("fallback.mp4: its SHA-256", ctx.exception.reasons[0])
        self.assertEqual(ran, [])

    def test_a_source_missing_from_the_take_is_refused(self):
        self.cut = cut(WALK[0], {"still": "edit", "hold": 3, "caption": "x"})       # the video is not cut...
        (self.dir / "fallback.mp4").unlink()
        with self.assertRaises(gif.CutError) as ctx:                               # ...but every source is checked
            self.build([])
        self.assertIn("missing fallback.mp4, a source of the take", ctx.exception.reasons[0])

    def test_the_dry_run_checks_the_sources_too(self):
        cut_path = self.dir / "gif.yml"
        cut_path.write_text(json.dumps(self.cut))
        with mock.patch.object(gif, "cut_list_path", return_value=cut_path), \
                mock.patch.object(gif, "page_times", return_value=TIMES):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(gif.main(["open-webui", str(self.dir), "--dry-run"]), 0)
            self.assertIn("/rec/fallback.mp4", out.getvalue())
            (self.dir / "first.png").write_bytes(b"another picture")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(gif.main(["open-webui", str(self.dir), "--dry-run"]), 1)
            self.assertIn("REFUSED: first.png: its SHA-256", err.getvalue())


class WorldModel(unittest.TestCase):
    def test_the_world_model_cut_list_fits_its_page_and_its_assembled_take(self):
        """The take assembled on 2026-11-17 from the recorded fallback (markers as written in the cache)."""
        cut_list = gif.load_cut_list(gif.cut_list_path("world-model"))
        take = assembled(demo="world-model", video="world-model-recorded-2026-11-08.mp4",
                         markers=[{"name": "first", "t": 0.1, "png": "first.png"}, {"name": "walk-end", "t": 8.0},
                                  {"name": "edit", "t": 12.41, "png": "edit.png"},
                                  {"name": "after", "t": 12.6, "png": "after.png"}])
        original = "~/demo-fallback/world-model-recorded-2026-11-08.mp4"
        take["source"] = [{"path": original, "sha256": sha(VIDEO_BYTES)}] + [
            {"path": original, "sha256": sha(VIDEO_BYTES), "file": f"{n}.png",
             "altered": {"sha256": sha(n.encode()), "how": "a frame"}} for n in ("first", "edit", "after")]
        p = gif.plan("world-model", cut_list, take, gif.page_times("world-model"))
        self.assertTrue(41 <= p.seconds <= 60, p.seconds)                  # a second of margin above 40 s
        self.assertEqual([m.marker or m.kind for m in p.moments], ["first", "motion", "edit", "after"])
        self.assertEqual((p.moments[1].start, p.moments[1].end, p.moments[1].speed), (0.1, 8.0, 1.0))  # real speed
        self.assertEqual((p.width, p.height, p.fps), (640, 360, 6))
        self.assertEqual([m.step for m in p.moments], ["0:30", "1:15", "2:15", ""])
        manifest = presenter.load_manifest(gif.cut_list_path("world-model").parent)
        self.assertEqual(presenter.take_kind(manifest), "assembled")


class CaptionWidth(unittest.TestCase):
    """26 px captions: 60 characters fit 960 px and wider; a narrower GIF takes fewer, never cut off silently."""

    def test_the_limit_follows_the_width(self):
        self.assertEqual([gif.caption_max(w) for w in (1280, 960, 800, 720, 640, 480)], [60, 60, 58, 52, 46, 33])

    def test_a_narrow_gif_refuses_a_caption_it_would_cut(self):
        still = {"still": "home", "hold": 3}
        gif.plan("open-webui", cut(dict(still, caption="x" * 46), width=640), markers(), TIMES)
        refused(self, cut(dict(still, caption="x" * 47), width=640), markers(),
                "at most 46 characters on a 640 px GIF")
        gif.plan("open-webui", cut(dict(still, caption="x" * 60), width=1280), markers(), TIMES)
        refused(self, cut(dict(still, caption="x" * 61), width=960), markers(), "at most 60 characters")


if __name__ == "__main__":
    unittest.main()
