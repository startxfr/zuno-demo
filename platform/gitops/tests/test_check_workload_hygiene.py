"""check_workload_hygiene: a new workload template without `resources` or a `securityContext` fails, the baseline only shrinks.

Run from the repository root:
    python3 platform/gitops/tests/test_check_workload_hygiene.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_workload_hygiene as chk  # noqa: E402

GOOD = "kind: Deployment\nspec:\n  template:\n    spec:\n      securityContext: {}\n      containers:\n        - resources: {}\n"
NO_SC = "kind: Job\nspec:\n  template:\n    spec:\n      containers:\n        - resources: {}\n"
NO_RES = "kind: CronJob\nspec:\n  jobTemplate:\n    spec:\n      template:\n        spec:\n          securityContext: {}\n"
NOT_A_WORKLOAD = "kind: Service\nspec: {}\n"


def tree(files: dict) -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp(prefix="hygiene-"))
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


class Hygiene(unittest.TestCase):
    def test_a_complete_workload_and_a_non_workload_are_fine(self):
        self.assertEqual(chk.offenders(tree({"a/templates/d.yaml": GOOD, "a/templates/s.yaml": NOT_A_WORKLOAD})), set())

    def test_each_missing_declaration_is_one_offender(self):
        found = chk.offenders(tree({"a/templates/j.yaml": NO_SC, "a/templates/c.yaml": NO_RES}))
        self.assertEqual(found, {("a/templates/j.yaml", "securityContext"), ("a/templates/c.yaml", "resources")})

    def test_a_security_helper_counts_as_the_declaration(self):
        helper = 'kind: Deployment\nspec:\n  template:\n    spec:\n      {{- include "chart.podSecurity" . | nindent 6 }}\n      containers:\n        - resources: {}\n'
        self.assertEqual(chk.offenders(tree({"a/templates/d.yaml": helper})), set())

    def test_nested_template_files_are_scanned(self):
        self.assertEqual(chk.offenders(tree({"a/templates/sub/j.yaml": NO_SC})), {("a/templates/sub/j.yaml", "securityContext")})

    def test_a_new_offender_fails_and_a_baselined_one_does_not(self):
        found = {("a/templates/j.yaml", "securityContext"), ("b/templates/n.yaml", "resources")}
        new, stale = chk.compare(found, {("a/templates/j.yaml", "securityContext")})
        self.assertEqual(len(new), 1)
        self.assertIn("b/templates/n.yaml has no `resources`", new[0])
        self.assertEqual(stale, [])

    def test_a_baseline_line_that_no_longer_applies_fails_so_the_list_only_shrinks(self):
        new, stale = chk.compare(set(), {("a/templates/j.yaml", "securityContext")})
        self.assertEqual(new, [])
        self.assertEqual(len(stale), 1)
        self.assertIn("delete the line", stale[0])

    def test_the_real_tree_matches_its_baseline(self):
        new, stale = chk.compare(chk.offenders(), chk.read_baseline())
        self.assertEqual((new, stale), ([], []))


if __name__ == "__main__":
    unittest.main()
