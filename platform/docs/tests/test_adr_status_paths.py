"""check_docs: a path cited by the Status line of a live ADR must exist, or the ADR carries a dated Amended note naming it.

Synthetic ADR text and a fake tree; the real tree is covered by running check_docs.py itself in CI.

Run from the repository root:
    python3 platform/docs/tests/test_adr_status_paths.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_docs  # noqa: E402

TREE = {"components/a/app.py", "docs/x.md"}


def exists(path):
    return path in TREE


def adr(status, extra=""):
    return f"# ADR-9999: t\n\n- **Status:** {status}\n- **Target:** v0.1\n\n## Decision\n\ntext\n{extra}"


def findings(status, extra=""):
    return [f.message for f in check_docs.adr_status_path_findings("9999", adr(status, extra), exists)]


class AdrStatusPaths(unittest.TestCase):
    def test_existing_paths_are_fine(self):
        self.assertEqual(findings("Implemented (`components/a/app.py`, `docs/x.md`)."), [])

    def test_a_missing_path_is_named_with_the_fix(self):
        found = findings("Implemented (`components/a/gone.py`).")
        self.assertEqual(len(found), 1)
        self.assertIn("ADR-9999 status cites components/a/gone.py, which does not exist", found[0])
        self.assertIn("Amended", found[0])
        self.assertIn("docs/adr/9999-*.md", found[0])

    def test_accepted_is_checked_too_but_other_statuses_are_not(self):
        self.assertEqual(len(findings("Accepted (`components/a/gone.py`).")), 1)
        for status in ("Proposed (`components/a/gone.py`)", "Superseded by ADR-1 (`components/a/gone.py`)",
                       "Partially implemented (`components/a/gone.py`)"):
            self.assertEqual(findings(status), [], status)

    def test_an_amended_note_that_names_the_path_makes_it_pass(self):
        note = "\n## Amended (2026-11-19): removed\n\n`components/a/gone.py` was deleted.\n"
        self.assertEqual(findings("Implemented (`components/a/gone.py`).", note), [])
        self.assertEqual(findings("Implemented (`components/a/gone.py`).", note.replace("## Amended (", "## Amendment (")), [])

    def test_the_note_may_name_the_file_or_its_directory(self):
        self.assertEqual(findings("Implemented (`components/a/b/gone.py`).", "\n## Amended (2026-11-19)\n\ngone.py was removed.\n"), [])
        self.assertEqual(findings("Implemented (`components/agent-runtime/app/x.py`).",
                                  "\n## Amended (2026-11-19)\n\n`components/agent-runtime/` was deleted.\n"), [])

    def test_a_note_that_does_not_name_it_is_not_enough(self):
        self.assertEqual(len(findings("Implemented (`components/a/gone.py`).", "\n## Amended (2026-11-19)\n\nsomething else.\n")), 1)

    def test_a_mention_outside_an_amended_section_is_not_enough(self):
        self.assertEqual(len(findings("Implemented (`components/a/gone.py`).", "\n## Notes\n\ncomponents/a/gone.py was removed.\n")), 1)

    def test_status_that_says_zuno_demo_agents_or_moved_is_skipped(self):
        self.assertEqual(findings("Implemented (`components/a/gone.py` now in zuno-demo-agents)."), [])
        self.assertEqual(findings("Implemented (`components/a/gone.py`, moved to another repo)."), [])

    def test_what_cannot_be_checked_is_skipped(self):
        for cited in ("`tests/test_x.py`", "`agents/tekos/tasks/t.md`", "`policies/tools/p.yaml`", "`evaluations/benchmarks/run.json`",
                      "`components/<name>/app.py`", "`components/*/app.py`", "`components/{a,b}/app.py`", "`make d1`", "`app.py`",
                      "`components/a/dir`"):
            self.assertEqual(findings(f"Implemented ({cited})."), [], cited)

    def test_a_status_with_no_path_or_no_status_line_is_fine(self):
        self.assertEqual(findings("Implemented."), [])
        self.assertEqual([f.message for f in check_docs.adr_status_path_findings("9999", "# ADR\n\nno status here\n", exists)], [])


if __name__ == "__main__":
    unittest.main()
