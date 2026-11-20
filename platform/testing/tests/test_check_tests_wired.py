"""check_tests_wired: which test files a workflow runs, on a small fixture repository, and on the real one.

Run from the repository root:
    python3 platform/testing/tests/test_check_tests_wired.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import textwrap
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import check_tests_wired as c  # noqa: E402


def repo(workflow: str, *tests: str):
    tmp = tempfile.TemporaryDirectory()
    root = pathlib.Path(tmp.name)
    for test in tests:
        (root / test).parent.mkdir(parents=True, exist_ok=True)
        (root / test).write_text("")
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(textwrap.dedent(workflow))
    return tmp, root


class Wiring(unittest.TestCase):
    def unwired(self, workflow: str, *tests: str):
        tmp, root = repo(workflow, *tests)
        with tmp:
            return c.unwired(root, root / ".github" / "workflows")

    def test_a_file_named_by_a_step_is_wired(self):
        self.assertEqual(self.unwired("""
            jobs:
              t:
                steps:
                  - run: python3 platform/a/tests/test_x.py
            """, "platform/a/tests/test_x.py", "platform/a/tests/test_y.py"), ["platform/a/tests/test_y.py"])

    def test_a_directory_named_by_a_step_covers_what_is_below(self):
        self.assertEqual(self.unwired("""
            jobs:
              t:
                steps:
                  - run: python3 -m pytest -q platform/keycloak/tests
            """, "platform/keycloak/tests/test_a.py", "platform/keycloak/tests/deep/test_b.py", "platform/other/test_c.py"),
            ["platform/other/test_c.py"])

    def test_a_working_directory_makes_relative_paths_count(self):
        self.assertEqual(self.unwired("""
            jobs:
              t:
                steps:
                  - working-directory: components/w
                    run: python3 -m pytest -q tests
            """, "components/w/tests/test_a.py", "components/z/tests/test_b.py"), ["components/z/tests/test_b.py"])

    def test_a_job_default_working_directory_counts_too(self):
        self.assertEqual(self.unwired("""
            jobs:
              t:
                defaults: {run: {working-directory: components/w}}
                steps:
                  - run: python3 tests/test_a.py
            """, "components/w/tests/test_a.py"), [])

    def test_node_modules_and_worktrees_are_not_tests_of_the_repository(self):
        tmp, root = repo("jobs: {}", "a/node_modules/x/test_n.py", ".claude/worktrees/w/test_w.py")
        with tmp:
            self.assertEqual(c.test_files(root), [])


class RealRepository(unittest.TestCase):
    def test_every_test_file_is_wired_or_baselined_and_the_baseline_has_no_dead_line(self):
        missing = set(c.unwired())
        baseline = c.load_baseline()
        self.assertEqual(sorted(missing - baseline), [])
        self.assertEqual(sorted(baseline - missing), [])


if __name__ == "__main__":
    unittest.main()
