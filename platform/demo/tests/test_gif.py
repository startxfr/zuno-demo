"""The GIF of a demo recording (ADR-0617, WP-284): the cut list against the markers and the page, the ffmpeg command,
the size limit, and the guards of `make demo record` and `make demo gif`. No ffmpeg, podman or cluster is needed.

Run from the repository root:
    python3 platform/demo/tests/test_gif.py
"""
from __future__ import annotations

import contextlib
import datetime
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
            "motion_from": "q1-sent", "chat_deleted": True, "status": "pass", "detail": ""}
    data.update(changes)
    return data


def cut(*moments, **changes) -> dict:
    data = {"target_seconds": [1, 600], "width": 960, "fps": 10, "moments": list(moments)}
    data.update(changes)
    return data


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
        refused(self, cut({"still": "home", "hold": 3, "caption": "x" * 80}), markers(), "at most 70")
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
        refused(self, cut(still), markers(chat_deleted=False), "did not delete the chat")
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
            return gif.build("open-webui", self.dir, self.cut, times=TIMES, runner=self.fake_ffmpeg(size))

    def test_built_with_captions_and_a_summary(self):
        built = self.build(3 * 1048576)
        self.assertEqual(built.path, self.dir / "open-webui.gif")
        self.assertEqual((self.dir / ".gif-captions/02.txt").read_text(), "0:00  Zuno picks the model")
        summary = "\n".join(built.summary())
        self.assertIn("3.0 MB", summary)
        self.assertIn("48.0 s by ffprobe", summary)
        self.assertIn("960x656 (picture 960x600 + caption band 56)", summary)
        self.assertTrue(json.loads((self.dir / "open-webui.gif.json").read_text())["moments"])

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
        (self.tools / "open-webui.mjs").write_text("")
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

    def test_record_asks_for_the_id_and_says_the_chat_is_deleted(self):
        session.record_check("open-webui", True)
        with self.recorder:
            rc, out, err = self.run_main("record", "open-webui")
            self.assertEqual(rc, 2)
            self.assertIn("DEMO_CONFIRM=open-webui", err)
            self.assertIn("the chat it creates is deleted at the end", out)
            with mock.patch.dict(os.environ, {"DEMO_CONFIRM": "open-webui"}):
                rc, out, err = self.run_main("record", "open-webui")
            self.assertEqual(rc, 2)
            self.assertIn("No kubeconfig", err)                          # still refused before anything runs
        self.assertFalse(gif.recordings_dir().exists())

    def test_record_and_gif_take_a_scenario_with_a_cut_list(self):
        rc, _, err = self.run_main("record", "three-experiences")
        self.assertEqual((rc, "is a workshop" in err), (2, True))
        rc, _, err = self.run_main("gif", "guardrails")
        self.assertEqual((rc, "has no cut list" in err), (2, True))

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
        rc, out, _ = self.run_main("--complete", "gif")
        self.assertEqual(out.split(), ["open-webui"])


if __name__ == "__main__":
    unittest.main()
