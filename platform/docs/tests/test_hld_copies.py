"""check_docs: every copy of the platform map (HLD) equals the reference, and sync_hld.py brings a copy back.

Synthetic page texts; the real tree is covered by running check_docs.py itself in CI.

Run from the repository root:
    python3 platform/docs/tests/test_hld_copies.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_docs  # noqa: E402
import sync_hld  # noqa: E402

SIG = check_docs.HLD_SIGNATURE
BODY = SIG + '\n    A["one"]\n    B["two"]\n  A --> B'
FOCUS = "\n\n  classDef focus fill:#ffd54f,stroke:#d84315;\n  class B focus;\n"


def page(body=BODY, focus=FOCUS):
    return f"# Page\n\nText.\n\n```mermaid\n{body}{focus}```\n\nMore text.\n"


REFERENCE = page(focus="\n")
REF_PATH = check_docs.HLD_REFERENCE


def findings(pages):
    return [f.message for f in check_docs.hld_copy_findings(pages, REFERENCE)]


class HldCopies(unittest.TestCase):
    def test_a_copy_with_its_own_highlight_is_equal(self):
        self.assertEqual(findings({REF_PATH: REFERENCE, "docs/demo/a.md": page()}), [])

    def test_a_different_highlight_node_is_not_a_difference(self):
        other = page(focus="\n\n  classDef focus fill:#ffd54f;\n  class A focus;\n")
        self.assertEqual(findings({"docs/demo/a.md": other}), [])

    def test_a_changed_node_is_named_with_the_fix(self):
        stale = page(body=BODY.replace('"two"', '"2"'))
        found = findings({"docs/demo/b.md": stale})
        self.assertEqual(len(found), 1)
        self.assertIn("docs/demo/b.md", found[0])
        self.assertIn("sync_hld.py", found[0])

    def test_a_page_without_the_map_is_ignored(self):
        self.assertEqual(findings({"docs/x.md": "# X\n\n```mermaid\nflowchart LR\n A-->B\n```\n"}), [])

    def test_a_reference_without_exactly_one_map_is_a_finding(self):
        out = check_docs.hld_copy_findings({}, "# no map here\n")
        self.assertEqual(len(out), 1)
        self.assertIn("exactly one platform map", out[0].message)

    def test_sync_restores_a_stale_copy_and_keeps_its_highlight(self):
        stale = page(body=BODY.replace('"two"', '"2"'))
        ref_body = check_docs.hld_without_focus(check_docs.hld_blocks(REFERENCE)[0])
        fixed = sync_hld.sync_page(stale, ref_body)
        self.assertEqual(findings({"docs/demo/c.md": fixed}), [])
        self.assertIn("class B focus;", fixed)
        self.assertIn("Text.", fixed)
        self.assertIn("More text.", fixed)

    def test_sync_leaves_an_equal_page_untouched(self):
        ref_body = check_docs.hld_without_focus(check_docs.hld_blocks(REFERENCE)[0])
        self.assertEqual(sync_hld.sync_page(page(), ref_body), page())


if __name__ == "__main__":
    unittest.main()
