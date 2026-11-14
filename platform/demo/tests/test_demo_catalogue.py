"""The catalogue pages and ansible/demos/ agree (ADR-0616 clause 14, WP-271).

Every demo has its directory and files, every timed row its step file, every Do command is covered, no read-only unit
changes anything, and every `make demo <verb>` of the docs exists. The negative cases mutate a copy of the fixture.

Run from the repository root:
    python3 platform/demo/tests/test_demo_catalogue.py
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent))

import catalogue  # noqa: E402
import consistency  # noqa: E402
import scaffold  # noqa: E402


class Repository(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("ZUNO_DEMO_ROOT", None)

    def test_no_problem(self):
        self.assertEqual(consistency.problems(ROOT), [])

    def test_36_directories(self):
        ids = {e.id for e in catalogue.discover(ROOT)}
        dirs = {d.name for d in (ROOT / "ansible/demos").iterdir() if d.is_dir() and d.name != "_lib"}
        self.assertEqual(len(ids), 36)
        self.assertEqual(dirs, ids)

    def test_scaffolder_has_nothing_left_to_create(self):
        entries = catalogue.discover(ROOT)
        readme = catalogue.readme_probes(ROOT)
        for entry in entries:
            for rel in scaffold.plan_demo(entry, ROOT, {}, {}, readme, scaffold.probe_names(ROOT)):
                self.assertTrue((catalogue.demo_dir(entry.id, ROOT) / rel).exists(), f"{entry.id}/{rel}")

    def test_demo_verbs_come_from_the_makefile(self):
        verbs = consistency.demo_verbs(ROOT)
        self.assertIn("rehearse", verbs)
        self.assertNotIn("reset", verbs)


class Negative(unittest.TestCase):
    """Each case breaks a copy of the fixture catalogue and expects one named problem."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="zuno-catalogue-"))
        shutil.copytree(FIXTURES / "docs", self.root / "docs")
        shutil.copytree(FIXTURES / "ansible", self.root / "ansible")
        self.demo = self.root / "ansible/demos/fixture-demo"
        self.page = self.root / "docs/demo/scenarios/fixture/fixture-demo.md"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def found(self):
        return consistency.problems(self.root, only=["fixture-demo"], docs=False)

    def test_fixture_is_clean(self):
        self.assertEqual(self.found(), [])

    def test_removed_step_file(self):
        (self.demo / "steps/05-00.yml").unlink()
        self.assertTrue(any("steps/05-00.yml: missing" in p for p in self.found()))

    def test_added_timed_row(self):
        text = self.page.read_text().replace("| 14:00 | Close |", "| 10:00 | Read | \"x\" | |\n| 14:00 | Close |")
        self.page.write_text(text)
        self.assertTrue(any("steps/10-00.yml: missing (row 10:00" in p for p in self.found()))

    def test_orphan_step_file(self):
        shutil.copy(self.demo / "steps/14-00.yml", self.demo / "steps/13-00.yml")
        self.assertTrue(any("steps/13-00.yml: no timed row" in p for p in self.found()))

    def test_missing_action_file(self):
        (self.demo / "stop.yml").unlink()
        self.assertTrue(any("stop.yml: missing" in p for p in self.found()))

    def test_unquoted_time_key(self):
        manifest = self.demo / "demo.yml"
        manifest.write_text(manifest.read_text().replace('"1:30":', "1:30:"))
        self.assertTrue(any("quote the time stamp (\"1:30\")" in p for p in self.found()))

    def test_uncovered_do_command(self):
        step = self.demo / "steps/00-00.yml"
        step.write_text(step.read_text().replace('"git log -1 --format=%h"', '"git log -2 --format=%h"'))
        self.assertTrue(any("`git log -1 --format=%h` is not covered" in p for p in self.found()))

    def test_refused_cmd(self):
        step = self.demo / "steps/00-00.yml"
        step.write_text(step.read_text().replace('- "git log -1 --format=%h"',
                                                 '- "git log -1 --format=%h"\n      - "oc delete pod x"'))
        self.assertTrue(any("`oc delete pod x` is refused" in p for p in self.found()))

    def test_changing_module_in_a_read_unit(self):
        (self.demo / "check.yml").write_text(
            '- name: x\n  kubernetes.core.k8s:\n    state: absent\n    kind: Pod\n    name: x\n    namespace: y\n')
        self.assertTrue(any("module kubernetes.core.k8s in a unit not declared changing" in p for p in self.found()))

    def test_changing_include_in_a_read_unit(self):
        (self.demo / "start.yml").write_text('- ansible.builtin.include_tasks: "{{ demo_lib }}/../../x.yml"\n')
        self.assertTrue(any("not a read-only _lib file" in p for p in self.found()))

    def test_declared_mutation_may_change(self):
        self.assertFalse(any("install.yml" in p for p in self.found()), "install is declared in mutations")

    def test_machineset_and_gpu_node(self):
        (self.demo / "status.yml").write_text(
            '- kubernetes.core.k8s_info:\n    api_version: machine.openshift.io/v1beta1\n    kind: MachineSet\n'
            '    name: zuno-gpu-a\n    namespace: openshift-machine-api\n')
        found = self.found()
        self.assertTrue(any("names a MachineSet" in p for p in found))
        self.assertTrue(any("names zuno-gpu-a" in p for p in found))

    def test_lifecycle_sections(self):
        text = self.page.read_text().replace("### Stop\n\nNothing to do.\n\n", "")
        self.page.write_text(text)
        self.assertTrue(any("`## Presenter lifecycle` holds" in p for p in self.found()))
        self.page.write_text(text.replace("### Uninstall\n\nThe file removes the fixture add-on marker.",
                                          "### Stop\n\n### Uninstall\n\nThe file removes the fixture add-on marker."))
        self.assertTrue(any("`### Stop` is empty" in p for p in self.found()))


class DocsVerbs(unittest.TestCase):
    def test_unknown_and_retired_verbs(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="zuno-docs-"))
        try:
            (root / "docs/demo").mkdir(parents=True)
            (root / "docs/adr").mkdir(parents=True)
            (root / "docs/demo/runbook.md").write_text(
                "Run `make demo use guardrails 15`, then `make demo reset`.\n"
                "The retired `make demo step-1` to `step-5` are replaced by `make demo step next`.\n"
                "Then `ONLY=dify make demo golden-path` and `make demo frobnicate`.\n")
            (root / "docs/adr/0001-x.md").write_text("History: `make demo reset`.\n")
            found = consistency.docs_problems(root, consistency.demo_verbs(ROOT), set())
            self.assertEqual(sorted(found), ["docs/demo/runbook.md:1: `make demo reset` is not a verb of DEMO_VERBS",
                                             "docs/demo/runbook.md:3: `make demo frobnicate` is not a verb of "
                                             "DEMO_VERBS"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
