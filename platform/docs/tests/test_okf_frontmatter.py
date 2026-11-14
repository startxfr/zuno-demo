"""check_docs: the OKF hook `_okf_frontmatter` applies the version dispatch of ADR-0615 clause 5 (WP-263).

Legacy v0.2/v0.3 without zuno.profile, or okf_version "0.2" (a string) with zuno.profile "1.0", are read;
everything else is refused by name, with the file named. platform/okf/tests/test_okf_version_dispatch.py
checks that this copy of the rule agrees with every other reader's.

Run from the repository root:
    python3 platform/docs/tests/test_okf_frontmatter.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_docs  # noqa: E402


def _document(front: str, zuno: str = "") -> pathlib.Path:
    path = pathlib.Path(tempfile.mkdtemp()) / "agent.okf.md"
    path.write_text(f"---\n{front}type: agent\nzuno:\n{zuno}  status: active\n---\nBody.\n", encoding="utf-8")
    return path


class OkfFrontmatter(unittest.TestCase):
    def test_legacy_and_profile_documents_are_read(self):
        for front in ("okf_version: v0.2\n", "okf_version: v0.3\n"):
            with self.subTest(front=front):
                self.assertEqual(check_docs._okf_frontmatter(_document(front))["zuno"]["status"], "active")
        profile = check_docs._okf_frontmatter(_document('okf_version: "0.2"\n', '  profile: "1.0"\n'))
        self.assertEqual((profile["zuno"]["profile"], profile["zuno"]["status"]), ("1.0", "active"))

    def test_other_versions_and_profiles_are_refused_by_name(self):
        for front, needle in (
                ('okf_version: "0.2"\n', "unsupported zuno.profile None"),
                ("okf_version: 0.2\n", "unsupported okf_version 0.2"),  # an unquoted 0.2 is a YAML number
                ("okf_version: v0.9\n", "unsupported okf_version 'v0.9'"),
                ("", "missing okf_version")):
            with self.subTest(front=front):
                path = _document(front)
                with self.assertRaises(ValueError) as caught:
                    check_docs._okf_frontmatter(path)
                self.assertIn(needle, str(caught.exception))
                self.assertIn(str(path), str(caught.exception))

    def test_a_profile_other_than_1_0_or_on_a_legacy_version_is_refused(self):
        for front, profile, needle in (('okf_version: "0.2"\n', '  profile: "2.0"\n', "unsupported zuno.profile '2.0'"),
                                       ("okf_version: v0.3\n", '  profile: "1.0"\n',
                                        'zuno.profile is only valid with okf_version "0.2"')):
            with self.subTest(front=front, profile=profile):
                with self.assertRaises(ValueError) as caught:
                    check_docs._okf_frontmatter(_document(front, profile))
                self.assertIn(needle, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
