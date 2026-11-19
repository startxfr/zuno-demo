"""check_docs: the non-blocking freshness warnings ("Last reviewed: YYYY-MM-DD").

Run from the repository root:
    python3 platform/docs/tests/test_freshness.py
"""
from __future__ import annotations

import datetime
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_docs  # noqa: E402

TODAY = datetime.date(2026, 11, 19)


def page(date):
    return f"# T\n\nLast reviewed: {date}\n\nText\n"


class Freshness(unittest.TestCase):
    def test_scope(self):
        self.assertTrue(check_docs.freshness_scope("docs/platform/slo.md"))
        self.assertTrue(check_docs.freshness_scope("docs/demo/scenarios/rhoai/external-models.md"))
        self.assertTrue(check_docs.freshness_scope("docs/overview.md"))
        self.assertFalse(check_docs.freshness_scope("docs/adr/0001-x.md"))
        self.assertFalse(check_docs.freshness_scope("docs/roadmap/versions.md"))
        self.assertFalse(check_docs.freshness_scope("docs/platform/image.png"))

    def test_a_recent_page_is_silent(self):
        self.assertEqual(check_docs.freshness_warnings({"docs/platform/a.md": page("2026-10-01")}, TODAY), [])

    def test_an_old_page_is_named_with_its_age(self):
        out = check_docs.freshness_warnings({"docs/platform/a.md": page("2026-07-01")}, TODAY)
        self.assertEqual(len(out), 1)
        self.assertIn("docs/platform/a.md", out[0])
        self.assertIn("141 days", out[0])

    def test_undated_pages_are_counted_once(self):
        out = check_docs.freshness_warnings({"docs/data/a.md": "# A\n", "docs/data/b.md": "# B\n"}, TODAY)
        self.assertEqual(len(out), 1)
        self.assertIn("2 page(s)", out[0])

    def test_pages_out_of_scope_are_ignored(self):
        self.assertEqual(check_docs.freshness_warnings({"docs/adr/0001-x.md": "# A\n"}, TODAY), [])

    def test_a_bad_date_is_reported(self):
        out = check_docs.freshness_warnings({"docs/platform/a.md": page("2026-13-45")}, TODAY)
        self.assertIn("not a valid date", out[0])


if __name__ == "__main__":
    unittest.main()
