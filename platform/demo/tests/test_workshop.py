"""Workshops by composition (ADR-0616 clause 10, WP-280): the agenda read from the page, its expansion into steps,
the chained actions, one guard, and the agenda checks of consistency.py. The fixture workshop plays the fixture
scenario's 5-minute version, one named step of its 15-minute version, and two rows of its own.

Run from the repository root:
    python3 platform/demo/tests/test_workshop.py
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
import guard  # noqa: E402
import render  # noqa: E402
import workshop  # noqa: E402


def load(root, demo_id):
    entry = catalogue.find(demo_id, root)
    return catalogue.load(entry), consistency.load_yaml(catalogue.demo_dir(demo_id, root) / "demo.yml")


class Agenda(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page, cls.manifest = load(FIXTURES, "fixture-workshop")

    def test_rows_are_classified_from_the_play_cell(self):
        rows = workshop.agenda_rows(self.page)
        self.assertEqual([(r.at, r.kind) for r in rows], [("0:00", "own"), ("0:02", "scenario"), ("0:07", "scenario"),
                                                          ("0:09", "inline"), ("0:12", "own")])
        self.assertEqual(rows[1].entry(), {"at": "0:02", "scenario": "fixture-demo", "version": "5"})
        self.assertEqual(rows[2].entry(), {"at": "0:07", "scenario": "fixture-demo", "version": "15", "only": ["5:00"]})
        self.assertEqual(rows[3].entry(), {"at": "0:09", "inline": "the-workshops-own-table"})
        self.assertEqual(rows[0].kind, "own", "a link to a section without a timed table is not inline")

    def test_expansion(self):
        flat = workshop.expand(self.page, self.manifest, FIXTURES)
        self.assertEqual([f.name for f in flat], ["0:00", "0:02/0:00", "0:02/1:30", "0:02/4:00", "0:07/5:00",
                                                  "0:09/0:00", "0:09/2:00", "0:12"])
        self.assertEqual([f.number for f in flat], list(range(1, 9)))
        self.assertEqual((flat[1].demo_id, flat[1].file), ("fixture-demo", "steps/00-00.yml"))
        self.assertEqual((flat[5].demo_id, flat[5].file), ("fixture-workshop", "steps/agenda-0-09--00-00.yml"))
        self.assertEqual((flat[0].file, flat[7].file), ("steps/agenda-0-00.yml", "steps/agenda-0-12.yml"))
        self.assertEqual(flat[3].transition, '"Now one step of the longer version."')
        self.assertEqual(flat[2].transition, "")
        self.assertEqual((flat[4].position, flat[4].of), (1, 1))

    def test_headers(self):
        flat = workshop.expand(self.page, self.manifest, FIXTURES)
        self.assertEqual(render.workshop_step_header(self.page, flat[2], len(flat)),
                         "fixture-workshop · workshop · step 3/8 · 0:02 The scenario · fixture-demo 1:30 (2/3)")
        self.assertEqual(render.workshop_step_header(self.page, flat[0], len(flat)),
                         "fixture-workshop · workshop · step 1/8 · 0:00 Opening")
        self.assertTrue(render.workshop_next_line(flat, flat[0]).startswith("Next: 2/8 · 0:02 The scenario · "))
        self.assertEqual(render.workshop_next_line(flat, flat[-1]), "Last step done: make demo stop")

    def test_unresolved_entries(self):
        for bad, why in (({"at": "0:02", "scenario": "no-such", "version": "5"}, "unknown scenario"),
                         ({"at": "0:02", "scenario": "fixture-demo", "version": "15", "only": ["9:99"]}, "no step"),
                         ({"at": "0:09", "inline": "presenter-lifecycle"}, "no timed table"),
                         ({"at": "7:77", "own": True}, "not a row")):
            with self.assertRaises(workshop.AgendaError) as ctx:
                workshop.expand(self.page, {"agenda": [bad]}, FIXTURES)
            self.assertIn(why, str(ctx.exception))


class Chain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page, cls.manifest = load(FIXTURES, "fixture-workshop")
        cls.manifests = workshop.load_manifests("fixture-workshop", cls.manifest,
                                                lambda d: consistency.load_yaml(d / "demo.yml"), FIXTURES)

    def test_forward_then_own_and_backward_in_reverse(self):
        manifest = {"agenda": [{"at": "0:01", "scenario": "a", "version": "5"}, {"at": "0:02", "scenario": "b",
                    "version": "5"}, {"at": "0:03", "scenario": "a", "version": "15"}]}
        self.assertEqual([u.name for u in workshop.action_units("w", manifest, "start", FIXTURES)],
                         ["start:a", "start:b", "start"])
        self.assertEqual([u.name for u in workshop.action_units("w", manifest, "stop", FIXTURES)],
                         ["stop:b", "stop:a", "stop"])

    def test_probes_are_deferred_to_the_workshops_own_file(self):
        check = workshop.action_units("w", self.manifest, "check", FIXTURES)
        self.assertEqual([u.defer_flush for u in check], [True, False])
        self.assertFalse(any(u.defer_flush for u in workshop.action_units("w", self.manifest, "status", FIXTURES)))
        text = (ROOT / "ansible/demos/_lib/flush_checks.yml").read_text()
        self.assertEqual(text.count("not (demo_unit.defer_flush | default(false) | bool)"), 6)

    def test_one_guard_names_every_changing_unit(self):
        units = workshop.action_units("fixture-workshop", self.manifest, "install", FIXTURES)
        changes = workshop.changing(units, self.manifests)
        self.assertEqual(list(changes), ["install:fixture-demo"])
        self.assertIn("fixture add-on marker", guard.mutation_summary(changes["install:fixture-demo"]))
        self.assertEqual(workshop.changing(workshop.action_units("fixture-workshop", self.manifest, "status",
                                                                 FIXTURES), self.manifests), {})

    def test_rehearsal_honours_mutating_steps_and_not_rehearsed(self):
        manifests = dict(self.manifests)
        manifests["fixture-demo"] = dict(manifests["fixture-demo"], not_rehearsed={"install": "by hand"})
        to_run, decided, order = workshop.rehearsal(self.page, self.manifest, manifests, FIXTURES)
        skipped = {d.name: d for d in decided if d.status == "skipped"}
        self.assertEqual(sorted(skipped), ["0:02/1:30", "install:fixture-demo"])
        self.assertEqual(skipped["install:fixture-demo"].messages, ["not rehearsed: by hand"])
        self.assertEqual(order[:2], ["status:fixture-demo", "status"])
        self.assertEqual(order[-2:], ["uninstall:fixture-demo", "uninstall"])
        self.assertEqual(len(order), len(to_run) + len(decided))


class RealWorkshops(unittest.TestCase):
    def test_the_six_agendas_resolve(self):
        os.environ.pop("ZUNO_DEMO_ROOT", None)
        counts = {}
        for entry in catalogue.discover(ROOT):
            if entry.kind == "workshop":
                page, manifest = load(ROOT, entry.id)
                counts[entry.id] = len(workshop.expand(page, manifest, ROOT))
        self.assertEqual(len(counts), 6)
        self.assertTrue(all(n > 10 for n in counts.values()), counts)

    def test_sovereign_plays_two_named_steps_of_the_15_minute_version(self):
        page, manifest = load(ROOT, "sovereign-governed-ai")
        proof = [f.step.time for f in workshop.expand(page, manifest, ROOT) if f.at == "0:33"]
        self.assertEqual(proof, ["10:30", "12:30"])


class AgendaConsistency(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="zuno-workshop-"))
        shutil.copytree(FIXTURES / "docs", self.root / "docs")
        shutil.copytree(FIXTURES / "ansible", self.root / "ansible")
        self.demo = self.root / "ansible/demos/fixture-workshop"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def found(self):
        return consistency.problems(self.root, only=["fixture-workshop"], docs=False)

    def edit(self, old, new):
        path = self.demo / "demo.yml"
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new))

    def test_fixture_is_clean(self):
        self.assertEqual(self.found(), [])

    def test_wrong_version(self):
        self.edit('"scenario": "fixture-demo", "version": "5"', '"scenario": "fixture-demo", "version": "15"')
        self.assertTrue(any("agenda entry 0:02 is" in p and "the page's row says" in p for p in self.found()))

    def test_only_time_that_does_not_exist(self):
        self.edit('"only": ["5:00"]', '"only": ["5:30"]')
        found = self.found()
        self.assertTrue(any("has no step 5:30" in p for p in found), found)

    def test_missing_and_extra_entries(self):
        self.edit('  - {"at": "0:12", "own": true}  # Close and questions\n', '  - {"at": "0:20", "own": true}\n')
        found = self.found()
        self.assertTrue(any("Agenda row 0:12 (Close and questions) has no agenda entry" in p for p in found))
        self.assertTrue(any("agenda entry 0:20 is not a row" in p for p in found))

    def test_unquoted_time(self):
        # YAML 1.1 reads an unquoted 1:05 as the integer 65 (a time under one hour stays a string).
        self.edit('{"at": "0:12", "own": true}', '{"at": 1:05, "own": true}')
        self.assertTrue(any("agenda `at` 65 is not a string: quote the time stamp" in p for p in self.found()))

    def test_own_step_files(self):
        (self.demo / "steps/agenda-0-12.yml").unlink()
        shutil.copy(self.demo / "steps/agenda-0-00.yml", self.demo / "steps/agenda-0-44.yml")
        found = self.found()
        self.assertTrue(any("steps/agenda-0-12.yml: missing (agenda row 0:12" in p for p in found))
        self.assertTrue(any("steps/agenda-0-44.yml: no own or inline agenda row" in p for p in found))

    def test_inline_do_command_must_be_covered(self):
        step = self.demo / "steps/agenda-0-09--00-00.yml"
        step.write_text(step.read_text().replace("git log -1 --format=%s", "git log -1 --format=%h"))
        self.assertTrue(any("`git log -1 --format=%s` is not covered" in p for p in self.found()))

    def test_a_workshop_page_may_name_what_its_scenarios_read(self):
        page = self.root / "docs/demo/workshops/fixture-workshop.md"
        page.write_text(page.read_text().replace(
            "### Status\n\nNothing to do.", "### Status\n\nThe scenarios read `fixture-add-on` and `fixture-nowhere`."))
        warned = consistency.warnings(self.root, only=["fixture-workshop"])
        self.assertEqual(len(warned), 1, warned)
        self.assertIn("`fixture-nowhere`", warned[0])

    def test_check_must_flush(self):
        (self.demo / "check.yml").write_text('- ansible.builtin.include_tasks: "{{ demo_lib }}/nothing_to_run.yml"\n')
        self.assertTrue(any("check.yml: a workshop's check must include _lib/flush_checks.yml" in p
                            for p in self.found()))


if __name__ == "__main__":
    unittest.main()
