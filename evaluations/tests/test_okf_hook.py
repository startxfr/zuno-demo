#!/usr/bin/env python3
"""ADR-0508 / WP-51: the evaluations' OKF hook (evaluations/common/okf_release.py
`agent_declaration` and `task_declarations`) against the OKF conformance cases,
plus its version check.

Every case is read through the hook and compared with the `mcp_gateway` section
of its expected.json (status and each task's allowed_tools); refusal cases must
raise an error naming the cause. The cases come from ZUNO_OKF_CONFORMANCE_DIR or
the admitted release; with none available the case test is skipped, and says so.

Run directly:

    cd evaluations && python3 tests/test_okf_hook.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "evaluations" / "common"))
sys.path.insert(0, str(REPO / "platform" / "okf"))

import okf_release as hook  # noqa: E402
import release_cache  # noqa: E402

CASES = release_cache.conformance_dir()


class ConformanceCases(unittest.TestCase):
    def test_every_case_reads_as_expected(self):
        if CASES is None:
            self.skipTest("no OKF conformance cases (set ZUNO_OKF_CONFORMANCE_DIR); fixture tests not run")
        for case in sorted(p for p in CASES.iterdir() if p.is_dir()):
            with self.subTest(case=case.name):
                expected = json.loads((case / "expected.json").read_text())["mcp_gateway"]
                agents = sorted(p.name for p in (case / "agents").iterdir())
                if expected["load_error"] is not None:
                    with self.assertRaises((ValueError, OSError)) as caught:
                        for agent in agents:
                            hook.task_declarations(case, agent)
                    self.assertIn(expected["load_error"], str(caught.exception))
                    continue
                self.assertEqual(agents, sorted(expected["agents"]))
                for agent, want in expected["agents"].items():
                    tasks = hook.task_declarations(case, agent)
                    self.assertEqual(hook.agent_declaration(case, agent).get("status"), want["status"])
                    self.assertEqual({t: z.get("allowed_tools", []) for t, z in tasks.items()}, want["tasks"])


class VersionCheck(unittest.TestCase):
    def _root(self, agent_version, task_version="v0.2"):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "agents" / "alpha" / "tasks").mkdir(parents=True)
        head = f"okf_version: {agent_version}\n" if agent_version else ""
        (root / "agents" / "alpha" / "agent.okf.md").write_text(
            f"---\n{head}type: agent\nzuno:\n  status: active\n  tasks: [ask]\n---\nx\n")
        (root / "agents" / "alpha" / "tasks" / "ask.md").write_text(
            f"---\nokf_version: {task_version}\ntype: task\nzuno:\n  allowed_tools: [t]\n---\nx\n")
        return root

    def test_supported_versions_read(self):
        self.assertEqual(hook.SUPPORTED_OKF_VERSIONS, ("v0.2", "v0.3"))
        for version in hook.SUPPORTED_OKF_VERSIONS:
            self.assertEqual(hook.task_declarations(self._root(version), "alpha"), {"ask": {"allowed_tools": ["t"]}})

    def test_unsupported_missing_and_frontmatterless_are_refused_by_name(self):
        for version, needle in (("v0.9", "unsupported okf_version 'v0.9'"), (None, "missing okf_version")):
            with self.assertRaises(ValueError) as caught:
                hook.agent_declaration(self._root(version), "alpha")
            self.assertIn(needle, str(caught.exception))
        root = self._root("v0.2")
        (root / "agents" / "alpha" / "agent.okf.md").write_text("# prose\n")
        with self.assertRaises(ValueError):
            hook.agent_declaration(root, "alpha")

    def test_a_task_file_beside_the_listed_ones_is_read_and_checked_too(self):
        root = self._root("v0.2")
        (root / "agents" / "alpha" / "tasks" / "extra.md").write_text("---\nokf_version: v0.9\n---\nx\n")
        with self.assertRaises(ValueError):
            hook.task_declarations(root, "alpha")

    def test_a_listed_task_with_no_file_is_an_error_not_a_skip(self):
        root = self._root("v0.2")
        (root / "agents" / "alpha" / "tasks" / "ask.md").unlink()
        with self.assertRaises(OSError):
            hook.task_declarations(root, "alpha")


if __name__ == "__main__":
    unittest.main()
