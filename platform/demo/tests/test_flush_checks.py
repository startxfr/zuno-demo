"""flush_checks.yml: the golden-path argv, with named probes and with the `all` queue entry, and what it records:
one row per probe with the probe's own detail (platform/demo/probe_rows.py), shown by the terminal RESULT and the
rehearsal report.

`all` runs the whole golden path (`golden_path_probe.py` with no `--only`), so a demo never hard-codes the probe list.

Run from the repository root:
    python3 platform/demo/tests/test_flush_checks.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest

import yaml
from jinja2.nativetypes import NativeEnvironment

ROOT = pathlib.Path(__file__).resolve().parents[3]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT / "platform/demo"))

import catalogue  # noqa: E402
import probe_rows  # noqa: E402
import rehearse  # noqa: E402
import render  # noqa: E402
import runner  # noqa: E402

GOLDEN_PASS = "PASS     dify     4.0s  answered by gpt-oss-20b\nRESULT: PASS\n"
GOLDEN_FAIL = ("PASS     unifai-tekos   31.2s  run 6f1c answered\n"
               "FAIL     trace           0.0s  no run id: the unifai-tekos moment did not run or failed\n"
               "RESULT: FAIL (trace)\n")
BROWSER_FAIL = ("PASS  open-webui     3.2s  signed in, answer shown\n"
                "FAIL  kagent         9.9s  Timeout 30000ms; Authorization: Bearer abcdefghijklmnop.qrst "
                "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln sha256~AAAABBBBCCCCDDDD\n"
                "RESULT: FAIL (kagent)\n")
FLUSH = ROOT / "ansible/demos/_lib/flush_checks.yml"
REPO = "/repo"


def _tasks():
    return yaml.safe_load(FLUSH.read_text())


def _render(template, **variables):
    return NativeEnvironment().from_string(template).render(**variables)


class FlushChecks(unittest.TestCase):
    def task(self, title):
        return [t for t in _tasks() if title in t["name"]][0]

    def order(self, probes):
        """What the ordering task prints for this queue: its argv, run for real (it only reads the probe script)."""
        argv = _render(self.task("in the script's order")["ansible.builtin.command"]["argv"],
                       zuno_repo_root=str(ROOT), demo_queued_probes=probes)
        self.assertEqual(argv[:2], ["python3", str(ROOT / "platform/demo/probe_order.py")])
        return subprocess.run([sys.executable] + argv[1:], check=True, capture_output=True, text=True).stdout

    def argv(self, probes):
        task = self.task("run the queued golden-path probes")
        only = _render(task["vars"]["_demo_only"], _demo_probe_order={"stdout": self.order(probes)})
        return _render(task["ansible.builtin.command"]["argv"], zuno_repo_root=REPO, _demo_only=only)

    def record(self, probes, rc=0, stdout="", stderr="", browser=None, golden=None):
        """What the flush records for these queues: the runs the helper task builds, through probe_rows.record."""
        task = self.task("one row per probe")
        scope = dict(demo_queued_probes=probes, demo_queued_browser=["open-webui", "kagent"] if browser else [],
                     _demo_probe_order={"stdout": self.order(probes)} if probes else {"skipped": True},
                     _demo_golden=golden if golden is not None else (
                         {"rc": rc, "stdout": stdout, "stderr": stderr} if probes else {"skipped": True}),
                     _demo_browser=browser or {"skipped": True})
        for key in ("_demo_golden_ran", "_demo_browser_ran", "_demo_only", "_demo_golden_run", "_demo_browser_run",
                    "_demo_runs"):
            scope[key] = _render(task["vars"][key], **scope)
        return probe_rows.record({"agent": "d", "layer": "check", "runs": scope["_demo_runs"]})

    def test_named_probes_run_with_only(self):
        self.assertEqual(self.argv(["dify", "guardrails"]),
                         ["python3", f"{REPO}/evaluations/golden_path_probe.py", "--only", "dify,guardrails"])

    def test_all_runs_the_whole_golden_path_without_only(self):
        self.assertEqual(self.argv(["all"]), ["python3", f"{REPO}/evaluations/golden_path_probe.py"])

    def test_all_absorbs_the_other_queued_probes(self):
        self.assertEqual(self.argv(["dify", "all"]), ["python3", f"{REPO}/evaluations/golden_path_probe.py"])

    def test_the_queue_runs_in_the_script_order(self):
        # `trace` reads the run id `unifai-tekos` leaves: queued first, it failed with "no run id" (2026-11-15).
        self.assertEqual(self.argv(["trace", "unifai-tekos"])[-2:], ["--only", "unifai-tekos,trace"])
        self.assertEqual(self.record(["trace", "unifai-tekos"])["checks"][0]["id"],
                         "golden-path/unifai-tekos,trace")

    def test_a_merged_queue_is_ordered_and_each_probe_runs_once(self):
        merged = ["trace", "sovereignty", "dify", "unifai-tekos", "trace", "dify"]
        self.assertEqual(self.argv(merged)[-1], "unifai-tekos,sovereignty,dify,trace")

    def test_the_confirmation_notice_names_the_probes_in_the_order_they_run(self):
        notice = rehearse.check_notices(["trace", "unifai-tekos", "trace"], [])[0]
        self.assertTrue(notice.startswith("golden-path probes: unifai-tekos, trace ("), notice)
        self.assertTrue(rehearse.check_notices(["dify", "all"], [])[0].startswith("every golden-path probe"))

    def test_the_order_is_the_script_own(self):
        sys.path.insert(0, str(ROOT / "platform/demo"))
        sys.path.insert(0, str(ROOT / "evaluations"))
        import golden_path_probe
        import probe_order
        self.assertEqual(probe_order.known(), list(golden_path_probe.PROBES))
        self.assertEqual(probe_order.ordered(reversed(list(golden_path_probe.PROBES))), list(golden_path_probe.PROBES))
        self.assertEqual(probe_order.ordered(["zz", "trace"]), ["trace", "zz"])
        for name, needs in probe_order.NEEDS.items():
            for need in needs:
                self.assertLess(probe_order.known().index(need), probe_order.known().index(name))

    def test_the_record_names_the_run(self):
        whole = self.record(["all"])
        self.assertEqual(whole["checks"][0]["id"], "golden-path/all")
        self.assertEqual(whole["commands"][0]["cmd"], "python3 evaluations/golden_path_probe.py")
        named = self.record(["dify"], stdout=GOLDEN_PASS)
        self.assertEqual([c["id"] for c in named["checks"]], ["golden-path/dify"])
        self.assertEqual(named["commands"][0]["cmd"], "python3 evaluations/golden_path_probe.py --only dify")

    def test_a_failed_run_names_the_probe_that_failed_and_why(self):
        # observability-trace, 2026-11-15 09:51: the report only said "golden-path/trace,unifai-tekos FAIL -> exit 1".
        got = self.record(["trace", "unifai-tekos"], rc=1, stdout=GOLDEN_FAIL)
        rows = {c["id"]: c for c in got["checks"]}
        self.assertEqual(list(rows), ["golden-path/unifai-tekos", "golden-path/trace"])
        self.assertTrue(rows["golden-path/unifai-tekos"]["passed"])
        self.assertFalse(rows["golden-path/trace"]["passed"])
        self.assertEqual(rows["golden-path/trace"]["detail"], "no run id: the unifai-tekos moment did not run or failed")
        self.assertEqual(rows["golden-path/unifai-tekos"]["duration_ms"], 31200)
        self.assertEqual(got["commands"][0]["rc"], 1)
        self.assertEqual(got["commands"][0]["output"], "")   # the result lines are the rows, not repeated

    def test_roadmap_and_skipped_rows_pass_with_their_status(self):
        got = self.record(["world-model"], stdout="ROADMAP  world-model     0.4s  zuno_world_model_enabled is false\n"
                                                  "RESULT: PASS\n")
        self.assertTrue(got["checks"][0]["passed"])
        self.assertEqual(got["checks"][0]["detail"], "roadmap: zuno_world_model_enabled is false")

    def test_a_run_that_fails_without_a_failing_line_is_one_failed_row(self):
        got = self.record(["dify", "nope"], rc=2, stderr="usage: golden_path_probe.py\n"
                                                         "golden_path_probe.py: error: unknown moment(s): ['nope']\n")
        self.assertEqual(len(got["checks"]), 1)
        self.assertEqual(got["checks"][0]["id"], "golden-path/dify,nope")
        self.assertFalse(got["checks"][0]["passed"])
        self.assertIn("exit 2", got["checks"][0]["detail"])
        self.assertIn("unknown moment(s): ['nope']", got["checks"][0]["detail"])
        self.assertIn("usage: golden_path_probe.py", got["commands"][0]["output"])

    def test_a_run_without_an_exit_code_is_a_failure_not_nothing(self):
        got = self.record(["dify"], golden={"msg": "the command did not run in the expected time frame"})
        self.assertFalse(got["checks"][0]["passed"])
        self.assertIn("did not finish", got["checks"][0]["detail"])
        self.assertIn("expected time frame", got["checks"][0]["detail"])
        self.assertEqual(got["commands"][0]["rc"], -1)

    def test_browser_rows_and_what_looks_like_a_secret_is_masked(self):
        got = self.record([], browser={"rc": 1, "stdout": BROWSER_FAIL,
                                       "stderr": "podman: password=hunter2hunter2 refused\n"})
        rows = {c["id"]: c for c in got["checks"]}
        self.assertEqual(list(rows), ["browser/open-webui", "browser/kagent"])
        self.assertFalse(rows["browser/kagent"]["passed"])
        text = json.dumps(got)
        for secret in ("abcdefghijklmnop", "eyJhbGciOiJSUzI1NiJ9", "sha256~AAAABBBBCCCCDDDD", "hunter2hunter2"):
            self.assertNotIn(secret, text)
        self.assertIn("Timeout 30000ms", rows["browser/kagent"]["detail"])
        self.assertIn("password=***", got["commands"][0]["output"])

    def test_no_run_records_nothing(self):
        self.assertEqual(self.record([]), {"checks": [], "commands": []})

    def test_the_terminal_and_the_rehearsal_report_show_the_probe_detail(self):
        got = self.record(["trace", "sovereignty"], rc=1, stdout=GOLDEN_FAIL.replace("unifai-tekos", "sovereignty ", 1),
                          stderr="Traceback (most recent call last):\n  boom | pipe\n")
        unit = runner.parse_results([{"name": "check", "status": "failed", "commands": got["commands"],
                                      "checks": got["checks"], "error": "One or more checks did not pass"}])[0]
        shown = "\n".join(render.result_block(unit))
        self.assertIn("FAIL golden-path/trace: no run id: the unifai-tekos moment did not run or failed", shown)
        self.assertIn("Traceback (most recent call last):", shown)
        page = catalogue.load(catalogue.find("fixture-demo", FIXTURES))
        names = rehearse.sequence(page, "5")
        results = [unit] + [runner.UnitResult(n, "nothing") for n in names if n != "check"]
        text, passed = rehearse.report(page, "5", results, None)
        self.assertFalse(passed)
        self.assertIn("golden-path/trace FAIL: no run id: the unifai-tekos moment did not run or failed", text)
        self.assertIn("## Output of the failed commands", text)
        self.assertIn("  boom | pipe", text)
        self.assertEqual(text.rstrip().split("\n")[-1], "RESULT: FAIL")

    def test_the_demo_does_not_name_the_probes(self):
        start = (ROOT / "ansible/demos/service-mesh-kiali/start.yml").read_text()
        tasks = yaml.safe_load(start)
        self.assertEqual(tasks[0]["vars"]["queue_probes"], ["all"])


if __name__ == "__main__":
    unittest.main()
