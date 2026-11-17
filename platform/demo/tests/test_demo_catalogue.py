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

    def test_39_directories(self):
        ids = {e.id for e in catalogue.discover(ROOT)}
        dirs = {d.name for d in (ROOT / "ansible/demos").iterdir() if d.is_dir() and d.name != "_lib"}
        self.assertEqual(len(ids), 39)
        self.assertEqual(dirs, ids)

    def test_scaffolder_has_nothing_left_to_create(self):
        entries = catalogue.discover(ROOT)
        readme = catalogue.readme_probes(ROOT)
        for entry in entries:
            for rel in scaffold.plan_demo(entry, ROOT, {}, {}, readme, scaffold.probe_names(ROOT)):
                self.assertTrue((catalogue.demo_dir(entry.id, ROOT) / rel).exists(), f"{entry.id}/{rel}")

    def test_scaffolder_reads_a_csv_by_prefix(self):
        item, why = scaffold.ready_entry("x", {"api_version": "operators.coreos.com/v1alpha1",
                                               "kind": "ClusterServiceVersion", "ns": "openshift-operators",
                                               "name": "claw-operator.v0.0.227-commit-f5aa592",
                                               "condition": "Succeeded", "now": True})
        self.assertIsNone(why)
        self.assertIn('"name_prefix": "claw-operator.v"', item)
        self.assertIn('"phase": "Succeeded"', item)
        self.assertNotIn('"name":', item)

    def test_a_demo_file_never_reads_a_sibling_through_demo_dir(self):
        """In a workshop `demo_dir` is the workshop's directory: a scenario's file reaches its own directory through
        `demo_unit.dir | default(demo_dir, true)` (agentic-ai failed its unifai-live-rag start and stop on 2026-11-15)."""
        bad = []
        for path in sorted((ROOT / "ansible/demos").glob("*/**/*.yml")):
            if path.parts[-2] == "_lib" or "_lib" in path.parts:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "demo_dir" in line.replace("default(demo_dir", "") and not line.lstrip().startswith("#"):
                    bad.append(f"{path.relative_to(ROOT)}:{number}")
        self.assertEqual(bad, [])

    def test_demo_verbs_come_from_the_makefile(self):
        verbs = consistency.demo_verbs(ROOT)
        self.assertIn("rehearse", verbs)
        self.assertNotIn("reset", verbs)


class FixtureCopy(unittest.TestCase):
    """A writable copy of the fixture catalogue."""

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


class Negative(FixtureCopy):
    """Each case breaks a copy of the fixture catalogue and expects one named problem."""

    def test_fixture_is_clean(self):
        self.assertEqual(self.found(), [])

    def queue(self, action, names):
        (self.demo / f"{action}.yml").write_text(
            "---\n- name: \"fixture | queue\"\n  ansible.builtin.include_tasks: \"{{ demo_lib }}/queue_probes.yml\"\n"
            f"  vars:\n    queue_probes: {names!r}\n"
            "- name: \"fixture | flush\"\n  ansible.builtin.include_tasks: \"{{ demo_lib }}/flush_checks.yml\"\n")

    def test_trace_queued_without_the_run_it_reads(self):
        self.queue("check", ["sovereignty", "trace"])
        self.assertTrue(any("check.yml: queues the golden-path probe `trace` without `unifai-tekos`" in p
                            for p in self.found()), self.found())
        for fine in (["trace", "unifai-tekos"], ["all"]):
            self.queue("check", fine)
            self.assertFalse(any("golden-path probe" in p for p in self.found()), self.found())

    def test_unknown_probe_queued(self):
        self.queue("start", ["no-such-probe"])
        self.assertTrue(any("start.yml: queues the golden-path probe `no-such-probe`, which" in p
                            for p in self.found()), self.found())

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

    def test_csv_pinned_by_name(self):
        (self.demo / "check.yml").write_text(
            '- ansible.builtin.include_tasks: "{{ demo_lib }}/cr_ready.yml"\n  vars:\n    cr_ready:\n'
            '      - {"api_version": "operators.coreos.com/v1alpha1", "kind": "ClusterServiceVersion", '
            '"name": "x-operator.v1.2.3", "namespace": "y", "phase": "Succeeded"}\n')
        self.assertTrue(any("pinned by name: use `name_prefix`" in p for p in self.found()))

    def test_lifecycle_sections(self):
        text = self.page.read_text().replace("### Stop\n\nNothing to do.\n\n", "")
        self.page.write_text(text)
        self.assertTrue(any("`## Presenter lifecycle` holds" in p for p in self.found()))
        self.page.write_text(text.replace("### Uninstall\n\nThe file removes the fixture add-on marker.",
                                          "### Stop\n\n### Uninstall\n\nThe file removes the fixture add-on marker."))
        self.assertTrue(any("`### Stop` is empty" in p for p in self.found()))


class SectionWarnings(FixtureCopy):
    def test_an_object_the_page_names_but_the_file_does_not_read(self):
        text = self.page.read_text().replace(
            "### Status\n\nNothing to do.", "### Status\n\nThe file reads the Deployment `fixture-api` and `fixture-db`.")
        self.page.write_text(text)
        self.assertEqual(self.found(), [], "a warning is never a problem")
        warned = consistency.warnings(self.root, only=["fixture-demo"])
        self.assertEqual(len(warned), 2)
        self.assertIn("names `fixture-api`, which the file does not read", warned[0])
        status = self.demo / "status.yml"
        status.write_text(status.read_text().replace('- "git log -1 --format=%h"',
                                                     '- "git log -1 --format=%h"\n      - "oc get deploy fixture-api fixture-db -n x"'))
        self.assertEqual(consistency.warnings(self.root, only=["fixture-demo"]), [])

    def test_a_route_host_read_portably_counts(self):
        text = self.page.read_text().replace(
            "### Status\n\nNothing to do.", "### Status\n\nThe file reads the route `fixture-ui.apps.demo999.example.com`.")
        self.page.write_text(text)
        self.assertEqual(len(consistency.warnings(self.root, only=["fixture-demo"])), 1)
        status = self.demo / "status.yml"
        status.write_text(status.read_text() + (
            '- ansible.builtin.include_tasks: "{{ demo_lib }}/routes.yml"\n  vars:\n    routes:\n'
            '      - {"namespace": "x", "name": "fixture-ui", "host": "fixture-ui.{{ cluster_base_domain }}"}\n'))
        self.assertEqual(consistency.warnings(self.root, only=["fixture-demo"]), [])

    def test_unmoved_page_gives_no_warning(self):
        self.assertEqual(consistency.warnings(self.root, only=["fixture-unscaffolded"]), [])


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
