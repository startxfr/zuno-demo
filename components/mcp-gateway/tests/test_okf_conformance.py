"""ADR-0508 / WP-51: the OKF reader of this component (app/agent_declarations.py)
against the OKF conformance cases.

Every case of the conformance set (zuno-demo-agents/conformance/cases, see its
README) is loaded through AgentDeclarationStore and compared with the
`mcp_gateway` section of its expected.json. Also pins the startup version check:
only the supported okf_version values load, and a refusal clears every agent.

The cases come from ZUNO_OKF_CONFORMANCE_DIR or, once a release carries them,
from the admitted release (platform/okf/release_cache.py). With none available
the case tests are skipped, and say so.

Run from the component directory:

    cd components/mcp-gateway && python3 tests/test_okf_conformance.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "platform" / "okf"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import release_cache  # noqa: E402
from app import agent_declarations as hook  # noqa: E402

CASES = release_cache.conformance_dir()


def _case_dirs():
    return sorted(p for p in CASES.iterdir() if p.is_dir()) if CASES else []


class ConformanceCases(unittest.TestCase):
    def test_cases_are_available(self):
        if CASES is None:
            self.skipTest("no OKF conformance cases (set ZUNO_OKF_CONFORMANCE_DIR); fixture tests not run")
        self.assertTrue(_case_dirs())

    def test_every_case_loads_as_expected(self):
        if CASES is None:
            self.skipTest("no OKF conformance cases (set ZUNO_OKF_CONFORMANCE_DIR); fixture tests not run")
        for case in _case_dirs():
            with self.subTest(case=case.name):
                expected = json.loads((case / "expected.json").read_text())["mcp_gateway"]
                store = hook.AgentDeclarationStore(str(case / "agents"))
                if expected["load_error"] is not None:
                    self.assertIsNotNone(store.load_error, "the bundle must be refused")
                    self.assertIn(expected["load_error"], store.load_error)
                    self.assertFalse(store.loaded)
                    self.assertEqual(store._agents, {})
                    continue
                self.assertIsNone(store.load_error)
                self.assertEqual(sorted(store._agents), sorted(expected["agents"]))
                for name, want in expected["agents"].items():
                    got = store.get(name)
                    self.assertEqual(
                        {"status": got.status, "access_groups": got.access_groups, "tasks": got.tasks}, want, name
                    )


class VersionCheck(unittest.TestCase):
    def _bundle(self, agent_version, task_version="v0.2"):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "alpha" / "tasks").mkdir(parents=True)
        head = f"okf_version: {agent_version}\n" if agent_version else ""
        (root / "alpha" / "agent.okf.md").write_text(
            f"---\n{head}type: agent\nzuno:\n  status: active\n  tasks: [ask]\n---\nx\n")
        (root / "alpha" / "tasks" / "ask.md").write_text(
            f"---\nokf_version: {task_version}\ntype: task\nzuno:\n  allowed_tools: [t]\n---\nx\n")
        return str(root)

    def test_supported_versions_load(self):
        self.assertEqual(hook.SUPPORTED_OKF_VERSIONS, ("v0.2", "v0.3"))
        for version in hook.SUPPORTED_OKF_VERSIONS:
            self.assertTrue(hook.AgentDeclarationStore(self._bundle(version)).loaded, version)

    def test_unsupported_and_missing_versions_are_refused_by_name(self):
        for version, needle in (("v0.9", "unsupported okf_version 'v0.9'"), ("v0.1", "unsupported okf_version 'v0.1'"),
                                (None, "missing okf_version")):
            store = hook.AgentDeclarationStore(self._bundle(version))
            self.assertFalse(store.loaded, version)
            self.assertIn(needle, store.load_error)

    def test_a_task_document_is_version_checked_too(self):
        store = hook.AgentDeclarationStore(self._bundle("v0.2", task_version="v0.9"))
        self.assertIn("unsupported okf_version 'v0.9'", store.load_error)


if __name__ == "__main__":
    unittest.main()
