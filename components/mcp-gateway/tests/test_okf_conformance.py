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
                # ADR-0401 / ADR-0406: the optional `delegation` section, ignored by readers that predate it.
                section = json.loads((case / "expected.json").read_text()).get("delegation")
                for name, want in ((section or {}).get("agents") or {}).items():
                    got = store.get(name)
                    self.assertEqual([{"agent": a, "task": t} for a, t in got.delegation_targets], want["targets"], name)
                    self.assertEqual(got.max_depth, want["max_depth"] or 1, name)


class VersionCheck(unittest.TestCase):
    """ADR-0615 clause 5: legacy v0.2/v0.3 without zuno.profile, or okf_version "0.2" with zuno.profile "1.0"."""

    def _bundle(self, agent_version, task_version="v0.2", agent_profile=None, task_profile=None):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "alpha" / "tasks").mkdir(parents=True)
        head = f"okf_version: {agent_version}\n" if agent_version else ""
        profile = f"  profile: {agent_profile}\n" if agent_profile else ""
        (root / "alpha" / "agent.okf.md").write_text(
            f"---\n{head}type: agent\nzuno:\n{profile}  status: active\n  tasks: [ask]\n---\nx\n")
        task_head = f"  profile: {task_profile}\n" if task_profile else ""
        (root / "alpha" / "tasks" / "ask.md").write_text(
            f"---\nokf_version: {task_version}\ntype: task\nzuno:\n{task_head}  allowed_tools: [t]\n---\nx\n")
        return str(root)

    def test_supported_versions_load(self):
        self.assertEqual(hook.LEGACY_OKF_VERSIONS, ("v0.2", "v0.3"))
        self.assertEqual((hook.UPSTREAM_OKF_VERSION, hook.ZUNO_PROFILES), ("0.2", ("1.0",)))
        for version in hook.LEGACY_OKF_VERSIONS:
            self.assertTrue(hook.AgentDeclarationStore(self._bundle(version)).loaded, version)

    def test_profile_10_loads_and_a_mixed_bundle_too(self):
        store = hook.AgentDeclarationStore(self._bundle('"0.2"', '"0.2"', '"1.0"', '"1.0"'))
        self.assertTrue(store.loaded, store.load_error)
        self.assertEqual(store.get("alpha").tasks, {"ask": ["t"]})
        # The version is checked one document at a time.
        self.assertTrue(hook.AgentDeclarationStore(self._bundle('"0.2"', "v0.3", '"1.0"')).loaded)

    def test_the_bundle_root_index_is_not_read(self):
        """Profile bundles carry an index.md whose frontmatter is only okf_version "0.2"."""
        root = pathlib.Path(self._bundle('"0.2"', '"0.2"', '"1.0"', '"1.0"'))
        (root / "alpha" / "index.md").write_text('---\nokf_version: "0.2"\n---\n\n# Alpha\n')
        self.assertTrue(hook.AgentDeclarationStore(str(root)).loaded)

    def test_profile_refusals_are_named_and_clear_every_agent(self):
        for args, needle in (
                (('"0.2"',), "unsupported zuno.profile None"),
                (('"0.2"', "v0.2", '"2.0"'), "unsupported zuno.profile '2.0'"),
                (("0.2", "v0.2", '"1.0"'), "unsupported okf_version 0.2"),  # an unquoted 0.2 is a YAML number
                (("v0.3", "v0.2", '"1.0"'), 'zuno.profile is only valid with okf_version "0.2"'),
                (("v0.2", '"0.2"'), "unsupported zuno.profile None")):  # the task document is checked too
            with self.subTest(args=args):
                store = hook.AgentDeclarationStore(self._bundle(*args))
                self.assertFalse(store.loaded)
                self.assertIn(needle, store.load_error)
                self.assertEqual(store._agents, {})

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
