"""The OKF read boundary lint (platform/okf/check_okf_read_boundary.py) finds
what it claims to find.

Run from the repository root:
    python3 platform/okf/tests/test_okf_read_boundary.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_okf_read_boundary as lint  # noqa: E402


class BoundaryLint(unittest.TestCase):
    def _found(self, name, text):
        root = pathlib.Path(tempfile.mkdtemp())
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return lint.find_reads([path], root)

    def test_detects_each_read_shape(self):
        for text in ('p = d / "agent.okf.md"\n', "p = d / 'okf-index.json'\n", 'p = d / "tasks" / f"{t}.md"\n'):
            self.assertTrue(self._found("components/x/app.py", text), text)

    def test_ignores_comments_and_prose(self):
        self.assertFalse(self._found("components/x/app.py", '# reads "agent.okf.md"\n'))
        self.assertFalse(self._found("components/x/app.py", "see agents/<agent>/agent.okf.md for details\n"))

    def test_an_unlisted_reader_is_a_violation(self):
        found = {"components/new/app.py": [3]}
        out = lint.violations({**found, **{rel: [1] for rel in list(lint.HOOKS) + list(lint.BASELINE)}})
        self.assertEqual(len(out), 1)
        self.assertIn("components/new/app.py:3", out[0])

    def test_stale_baseline_and_hook_entries_are_reported(self):
        out = lint.violations({})
        self.assertEqual(len(out), len(lint.HOOKS) + len(lint.BASELINE))

    def test_the_repository_is_clean(self):
        self.assertEqual(lint.violations(lint.find_reads(lint._sources())), [])


if __name__ == "__main__":
    unittest.main()
