"""flush_checks.yml: the golden-path argv, with named probes and with the `all` queue entry.

`all` runs the whole golden path (`golden_path_probe.py` with no `--only`), so a demo never hard-codes the probe list.

Run from the repository root:
    python3 platform/demo/tests/test_flush_checks.py
"""
from __future__ import annotations

import pathlib
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
    def argv(self, probes):
        task = _tasks()[0]
        return _render(task["ansible.builtin.command"]["argv"], zuno_repo_root=REPO, demo_queued_probes=probes)

    def record_vars(self, probes, rc=0):
        task = [t for t in _tasks() if "ansible.builtin.set_fact" in t][0]
        out = {}
        scope = dict(demo_queued_probes=probes, demo_queued_browser=[], demo_id="d", demo_unit={"name": "start"},
                     _demo_golden={"rc": rc, "stdout_lines": ["ok"]})
        for key in ("_demo_nl", "_demo_golden_ran", "_demo_browser_ran"):
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
