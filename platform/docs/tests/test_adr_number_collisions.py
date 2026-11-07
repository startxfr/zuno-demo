"""check_docs: two ADR records must never share a number (ADR-0606 clause 5, WP-239).

On 2026-11-07 a second `0602-*` record was committed next to ADR-0602. The other checks key ADR files by their
four-digit prefix, so the newer file silently replaced the older one in their view. These cases feed the helper
synthetic file lists; the real directory is covered by running check_docs.py itself in CI.

Run from the repository root:
    python3 platform/docs/tests/test_adr_number_collisions.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_docs  # noqa: E402

D = pathlib.Path("docs/adr")


class AdrNumberCollisions(unittest.TestCase):
    def test_distinct_numbers_pass(self):
        paths = [D / "0601-a.md", D / "0602-b.md", D / "0603-c.md"]
        self.assertEqual(check_docs.adr_number_collisions(paths), [])

    def test_the_2026_11_07_case_is_reported(self):
        paths = [D / "0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md",
                 D / "0602-introduce-an-interactive-generative-world-model-experience.md"]
        findings = check_docs.adr_number_collisions(paths)
        self.assertEqual(len(findings), 1)
        self.assertIn("ADR-0602 is used by 2 files", str(findings[0].__dict__))

    def test_a_duplicate_whose_slug_sorts_first_is_reported(self):
        # The case the link check alone could never see: the extra file sorts before the indexed one.
        paths = [D / "0602-aaa-newer.md", D / "0602-harden.md"]
        self.assertEqual(len(check_docs.adr_number_collisions(paths)), 1)

    def test_three_files_one_number_is_one_finding(self):
        paths = [D / "0700-a.md", D / "0700-b.md", D / "0700-c.md"]
        findings = check_docs.adr_number_collisions(paths)
        self.assertEqual(len(findings), 1)
        self.assertIn("used by 3 files", str(findings[0].__dict__))


if __name__ == "__main__":
    unittest.main()
