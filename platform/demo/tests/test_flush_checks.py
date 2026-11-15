"""flush_checks.yml: the golden-path argv, with named probes and with the `all` queue entry.

`all` runs the whole golden path (`golden_path_probe.py` with no `--only`), so a demo never hard-codes the probe list.

Run from the repository root:
    python3 platform/demo/tests/test_flush_checks.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

import yaml
from jinja2.nativetypes import NativeEnvironment

ROOT = pathlib.Path(__file__).resolve().parents[3]
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

    def record_vars(self, probes, rc=0):
        task = [t for t in _tasks() if "ansible.builtin.set_fact" in t][0]
        out = {}
        scope = dict(demo_queued_probes=probes, demo_queued_browser=[], demo_id="d", demo_unit={"name": "start"},
                     _demo_golden={"rc": rc, "stdout_lines": ["ok"]}, _demo_probe_order={"stdout": self.order(probes)})
        for key in ("_demo_nl", "_demo_only", "_demo_golden_ran", "_demo_browser_ran"):
            scope[key] = _render(task["vars"][key], **scope)
        for key in ("_demo_golden_rows", "_demo_cmds"):
            out[key] = _render(task["vars"][key], **scope, _demo_browser_rows=[], **{"_demo_browser": {}})
        return out

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
        self.assertEqual(self.record_vars(["trace", "unifai-tekos"])["_demo_golden_rows"][0]["id"],
                         "golden-path/unifai-tekos,trace")

    def test_a_merged_queue_is_ordered_and_each_probe_runs_once(self):
        merged = ["trace", "sovereignty", "dify", "unifai-tekos", "trace", "dify"]
        self.assertEqual(self.argv(merged)[-1], "unifai-tekos,sovereignty,dify,trace")

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
        rows = self.record_vars(["all"])
        self.assertEqual(rows["_demo_golden_rows"][0]["id"], "golden-path/all")
        self.assertEqual(rows["_demo_cmds"][0]["cmd"], "python3 evaluations/golden_path_probe.py")
        named = self.record_vars(["dify"])
        self.assertEqual(named["_demo_golden_rows"][0]["id"], "golden-path/dify")
        self.assertEqual(named["_demo_cmds"][0]["cmd"], "python3 evaluations/golden_path_probe.py --only dify")

    def test_the_demo_does_not_name_the_probes(self):
        start = (ROOT / "ansible/demos/service-mesh-kiali/start.yml").read_text()
        tasks = yaml.safe_load(start)
        self.assertEqual(tasks[0]["vars"]["queue_probes"], ["all"])


if __name__ == "__main__":
    unittest.main()
