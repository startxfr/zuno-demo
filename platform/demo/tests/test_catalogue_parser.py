"""The demo catalogue parser and the terminal renderer (ADR-0616 clauses 2 and 4, WP-270).

The real pages of docs/demo/ must parse: 30 scenarios with 157 timed rows in their 5-minute versions and 275 in their
15-minute versions, the four EXCLUDED_BLOCKS found, 6 workshops. Synthetic pages prove each contract error.

Run from the repository root:
    python3 platform/demo/tests/test_catalogue_parser.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "platform" / "docs"))

import catalogue as c  # noqa: E402
import render  # noqa: E402
from runner import UnitResult  # noqa: E402

PAGE = """# Scenario: synthetic

## Introduction

Text.

## 5-minute version

Profile 1.

| Time | Do | Say | You should see |
|---|---|---|---|
| 0:00 | `oc get pods -n x \\| grep y` | "One." | A pod. |
| 2:00 | Close | "Two." | |

## 15-minute version

Run the 5-minute version, then:

| Time | Do | Say | You should see |
|---|---|---|---|
| 5:00 | Deep dive | "Three." | |
| 14:00 | Close | "Four." | |

## If something goes wrong

| Symptom | Fallback | Say |
|---|---|---|
| Nothing at 5:00 | Wait. | "Wait." |
"""


def write_page(text: str, stem: str = "synthetic") -> pathlib.Path:
    directory = pathlib.Path(tempfile.mkdtemp())
    path = directory / f"{stem}.md"
    path.write_text(text, encoding="utf-8")
    return path


class RealPages(unittest.TestCase):
    """The catalogue as it is in this tree (ZUNO_DEMO_ROOT unset)."""

    @classmethod
    def setUpClass(cls):
        os.environ.pop("ZUNO_DEMO_ROOT", None)
        cls.entries = c.discover(ROOT)
        cls.pages = {e.id: c.load(e) for e in cls.entries}

    def test_36_demos_30_scenarios_6_workshops(self):
        kinds = [e.kind for e in self.entries]
        self.assertEqual(len(self.entries), 36)
        self.assertEqual(kinds.count("scenario"), 30)
        self.assertEqual(kinds.count("workshop"), 6)

    def test_step_counts(self):
        k5 = sum(len(p.steps("5")) for p in self.pages.values())
        k15_own = sum(len(p.steps15_own) for p in self.pages.values())
        self.assertEqual(k5, 157)
        self.assertEqual(k15_own, 275)

    def test_fifteen_minute_version_is_cumulative(self):
        for page in self.pages.values():
            if page.kind != "scenario":
                continue
            fifteen = page.steps("15")
            self.assertEqual([s.time for s in fifteen[:len(page.steps5)]], [s.time for s in page.steps5], page.id)
            self.assertEqual([s.number for s in fifteen], list(range(1, len(fifteen) + 1)), page.id)

    def test_every_exclusion_is_found(self):
        seen = [b for p in self.pages.values() for b in p.excluded_seen]
        for block in c.EXCLUDED_BLOCKS:
            self.assertIn(block, seen, f"EXCLUDED_BLOCKS entry no longer matches its page: {block}")

    def test_escaped_pipe_is_unescaped(self):
        step = next(s for s in self.pages["guardrails"].steps("15") if s.time == "7:30")
        self.assertIn("| grep guardrails", step.do)
        self.assertEqual(step.file_name, "07-30.yml")

    def test_slugs_follow_check_docs(self):
        import check_docs  # noqa: E402
        for page in self.pages.values():
            self.assertTrue({s.slug for s in page.sections} <= check_docs.markdown_anchors(page.text), page.id)

    def test_lifecycle_sections_render_when_present(self):
        for page in self.pages.values():
            text, migrated = page.lifecycle_text("start")
            if migrated:
                for action in c.LIFECYCLE_ACTIONS:
                    body, _ = page.lifecycle_text(action)
                    self.assertTrue(body and body.strip(), f"{page.id}: empty ### {action}")
                    self.assertEqual(render.action_section(page, action)[0], action.upper())

    def test_readme_probes(self):
        probes = c.readme_probes(ROOT)
        self.assertEqual(c.show_ready(probes["guardrails"]), "probe guardrails")
        self.assertEqual(c.show_ready(probes["quotas"]), "rehearse first")
        self.assertEqual(c.show_ready(probes["world-model"]), "no")


class Contract(unittest.TestCase):
    def load(self, text, stem="synthetic"):
        return c.load_page(write_page(text, stem), "scenario", "test")

    def test_synthetic_page(self):
        page = self.load(PAGE)
        self.assertEqual([s.time for s in page.steps("5")], ["0:00", "2:00"])
        self.assertEqual([s.time for s in page.steps("15")], ["0:00", "2:00", "5:00", "14:00"])
        self.assertEqual(page.steps("5")[0].do, "`oc get pods -n x | grep y`")
        self.assertEqual(page.steps("15")[3].file_name, "14-00.yml")

    def test_unknown_table_fails(self):
        text = PAGE.replace("Profile 1.", "| A | B |\n|---|---|\n| 1 | 2 |")
        with self.assertRaises(c.ParseError) as ctx:
            self.load(text)
        self.assertIn("unknown table", str(ctx.exception))

    def test_unknown_subsection_fails(self):
        text = PAGE.replace("## If something goes wrong", "### Extra\n\nText.\n\n## If something goes wrong")
        with self.assertRaises(c.ParseError) as ctx:
            self.load(text)
        self.assertIn("unknown subsection", str(ctx.exception))

    def test_excluded_table_needs_its_page(self):
        table = "| Order | Prompt | Measured | What the audience sees |\n|---|---|---|---|\n| 1 | x | y | z |"
        with self.assertRaises(c.ParseError):
            self.load(PAGE.replace("Profile 1.", table))
        page = self.load(PAGE.replace("Profile 1.", table), stem="blender-3d")
        self.assertEqual(len(page.steps("5")), 2)

    def test_missing_lead_line_fails(self):
        with self.assertRaises(c.ParseError) as ctx:
            self.load(PAGE.replace("Run the 5-minute version, then:", "Then:"))
        self.assertIn("Run the 5-minute version", str(ctx.exception))

    def test_times_must_ascend(self):
        with self.assertRaises(c.ParseError):
            self.load(PAGE.replace("| 5:00 | Deep dive", "| 1:00 | Deep dive"))

    def test_times_must_be_unique(self):
        with self.assertRaises(c.ParseError):
            self.load(PAGE.replace("| 2:00 | Close", "| 0:00 | Close"))

    def test_untimed_row_fails(self):
        with self.assertRaises(c.ParseError):
            self.load(PAGE.replace("| 2:00 | Close", "| Close | Close"))

    def test_two_step_tables_fail(self):
        step_table = "| Time | Do | Say | You should see |\n|---|---|---|---|\n| 3:00 | x | y | z |"
        with self.assertRaises(c.ParseError):
            self.load(PAGE.replace("## 15-minute version", step_table + "\n\n## 15-minute version"))

    def test_fenced_tables_are_ignored(self):
        page = self.load(PAGE.replace("Profile 1.", "```\n| A | B |\n```"))
        self.assertEqual(len(page.steps("5")), 2)

    def test_split_cells(self):
        self.assertEqual(c.split_cells("| a \\| b | c |"), ["a | b", "c"])
        self.assertEqual(c.split_cells("| `x` | |"), ["`x`", ""])


class Rendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = c.load_page(FIXTURES / "docs/demo/scenarios/fixture/fixture-demo.md", "scenario", "fixture")
        cls.legacy = c.load_page(FIXTURES / "docs/demo/scenarios/fixture/fixture-unscaffolded.md", "scenario", "fixture")

    def test_action_section_from_presenter_lifecycle(self):
        lines = render.action_section(self.page, "start")
        self.assertEqual(lines[0], "START")
        self.assertIn("- [ ] Open two terminals.", lines)

    def test_unmigrated_page_falls_back(self):
        lines = render.action_section(self.legacy, "status")
        self.assertIn("page not migrated yet", lines[0])
        self.assertTrue(any("keeps this checklist" in l for l in lines))

    def test_step_header_body_next(self):
        steps = self.page.steps("15")
        self.assertEqual(render.step_header(self.page, "15", steps[3], len(steps)),
                         "fixture-demo · 15-minute · step 4/6 · 5:00")
        body = render.step_body(steps[3])
        self.assertEqual(body[0], "Do:")
        self.assertIn("  Terminal: `git log -2 --oneline | head -1`", body)
        self.assertTrue(render.next_line(steps, steps[3]).startswith("Next: 5/6 · 6:00 · "))
        self.assertEqual(render.next_line(steps, steps[-1]), "Last step done: make demo stop")

    def test_failure_rows_cite_the_step_first(self):
        lines = render.failure_rows(self.page, "6:00")
        self.assertEqual(lines[:2], ["FAILED", "If something goes wrong:"])
        self.assertIn("6:00", lines[2])
        reordered = render.failure_rows(self.page, "0:00")
        self.assertIn("The 6:00 read fails", reordered[2])

    def test_result_block(self):
        self.assertEqual(render.result_block(UnitResult("check", "nothing")), ["RESULT", "  Nothing to run."])
        block = render.result_block(UnitResult("7:30", "failed", commands=[
            {"cmd": "oc get x", "rc": 1, "output": "error: nope", "truncated": True}]))
        self.assertIn("  $ oc get x   [exit 1]", block)
        self.assertIn("    error: nope", block)
        self.assertTrue(any("first 40 lines" in l for l in block))

    def test_markdown_strips_links_and_renders_tables(self):
        lines = render.markdown("See [the ADR](../adr/x.md) and **bold**.\n\n| A | B |\n|---|---|\n| one | two |")
        self.assertIn("See the ADR and bold.", lines)
        self.assertIn("- A: one", lines)
        self.assertIn("    B: two", lines)


if __name__ == "__main__":
    unittest.main()
