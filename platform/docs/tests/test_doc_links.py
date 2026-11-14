"""check_docs: relative markdown links and their #anchors resolve (doc_links).

On 2026-11-12 an audit found 18 broken links the first version of the check could not see, because it only
looked at 4-digit ADR names in three directories. These cases rebuild each kind in a temporary tree. The real
repository is covered by running check_docs.py itself in CI.

Run from the repository root:
    python3 platform/docs/tests/test_doc_links.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_docs  # noqa: E402


class DocLinks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name) / "repo"
        for rel, text in {
            "docs/adr/README.md": "# ADRs\n\n## Standard clauses\n\nText.\n",
            "docs/adr/0212-chat.md": "# ADR-0212: Chat\n\n- **Status:** Superseded\n\n## Context\n",
            "docs/roadmap/README.md": "# Roadmap\n",
            "docs/roadmap/work-packages/wp-110-rhtas-operator-deployment-and-fundamentals.md": "# WP-110\n",
        }.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def problems(self, rel: str, text: str):
        return check_docs.doc_link_problems(self.root / rel, text, self.root)

    def test_good_links_pass(self):
        text = ("[clauses](../adr/README.md#standard-clauses) [adr](../adr/0212-chat.md#context)\n"
                "[self](#roadmap) [ext](https://github.com/startxfr/zuno-demo-agents/blob/main/agents/tekos/README.md)\n"
                "[mail](mailto:a@b.c)\n[ref]: ../adr/README.md\n")
        self.assertEqual(self.problems("docs/roadmap/README.md", "# Roadmap\n" + text), [])

    def test_file_moved_to_the_agents_repository(self):
        found = self.problems("docs/agents/tekos.md", "See [`/agents/tekos`](../../agents/tekos/README.md).\n")
        self.assertEqual([(1, "../../agents/tekos/README.md")], [p[:2] for p in found])
        self.assertIn("does not resolve", found[0][2])

    def test_link_to_a_sibling_checkout_is_reported(self):
        found = self.problems("docs/agents/tekos.md", "[x](../../../zuno-demo-agents/agents/tekos/README.md)\n")
        self.assertEqual(len(found), 1)
        self.assertIn("outside this repository", found[0][2])

    def test_standard_clauses_one_directory_too_shallow(self):
        # docs/roadmap/README.md exists but has no such section: an anchor finding, not a missing file.
        found = self.problems("docs/roadmap/adr-decisions-v0.1.md", "[Standard clauses](README.md#standard-clauses)\n")
        self.assertEqual(len(found), 1)
        self.assertIn("'#standard-clauses'", found[0][2])
        found = self.problems("docs/roadmap/work-packages/wp-08.md", "[s](README.md#standard-clauses)\n")
        self.assertIn("does not resolve", found[0][2])

    def test_wrong_file_name(self):
        found = self.problems("docs/roadmap/work-packages/wp-178.md",
                              "- **Related:** [WP-110](wp-110-rhtas-operator-live-findings.md)\n")
        self.assertEqual(len(found), 1)

    def test_anchor_to_a_bullet_is_not_a_heading(self):
        found = self.problems("docs/adr/0214-x.md", "[ADR-0212](0212-chat.md#status)\n")
        self.assertEqual(len(found), 1)
        self.assertIn("'#status'", found[0][2])

    def test_code_is_not_a_link(self):
        text = "`[x](missing.md)`\n```\n[y](missing.md)\n```\n"
        self.assertEqual(self.problems("docs/adr/README.md", text), [])

    def test_repeated_headings_get_a_counter(self):
        anchors = check_docs.markdown_anchors("# A b\n## A b\n### `A` b!\n```\n# not\n```\n")
        self.assertEqual(anchors, {"a-b", "a-b-1", "a-b-2"})

    def test_template_placeholders_are_exempt(self):
        self.assertIn("docs/adr/TEMPLATE.md", check_docs.DOC_LINK_EXEMPT)


if __name__ == "__main__":
    unittest.main()
