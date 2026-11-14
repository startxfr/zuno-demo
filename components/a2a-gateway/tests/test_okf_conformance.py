"""ADR-0508 / ADR-0615 (WP-263): the OKF reader of this component (app/agent_declarations.py)
against the OKF conformance cases, and its version check.

The a2a-gateway reads the same slice as the mcp-gateway (status, access groups, each task's
allowed tools), so every case is compared with the `mcp_gateway` section of its expected.json.
A refusal clears every agent. The version check is ADR-0615 clause 5: legacy v0.2/v0.3 without
zuno.profile, or okf_version "0.2" (a string) with zuno.profile "1.0".

The cases come from ZUNO_OKF_CONFORMANCE_DIR or, once a release carries them, from the admitted
release (platform/okf/release_cache.py). With none available the case tests are skipped, and
say so.

Run from the component directory:

    cd components/a2a-gateway && python3 -m pytest -q tests/test_okf_conformance.py
"""
from __future__ import annotations

import json
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
SKIP = "no OKF conformance cases (set ZUNO_OKF_CONFORMANCE_DIR); fixture tests not run"


def _case_dirs():
    return sorted(p for p in CASES.iterdir() if p.is_dir()) if CASES else []


class ConformanceCases(unittest.TestCase):
    def test_every_case_loads_as_expected(self):
        if CASES is None:
            self.skipTest(SKIP)
        self.assertTrue(_case_dirs())
        for case in _case_dirs():
            with self.subTest(case=case.name):
                document = json.loads((case / "expected.json").read_text())
                expected = document["mcp_gateway"]
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
                for name, want in (((document.get("delegation") or {}).get("agents")) or {}).items():
                    got = store.get(name)
                    self.assertEqual([{"agent": a, "task": t} for a, t in got.delegation_targets], want["targets"], name)
                    self.assertEqual(got.max_depth, want["max_depth"] or 1, name)

    def test_a_profile_prompt_is_read_without_its_frontmatter(self):
        if CASES is None:
            self.skipTest(SKIP)
        case = CASES / "valid-profile10-full"
        if not case.is_dir():
            self.skipTest("these conformance cases predate profile 1.0 (no valid-profile10-full)")
        prompt = hook.AgentDeclarationStore(str(case / "agents")).get("delta").system_prompt("ask")
        self.assertEqual(prompt, "Answer from the retrieved passages and cite them.")


class VersionCheck(unittest.TestCase):
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
        store = hook.AgentDeclarationStore(self._bundle('"0.2"', '"0.2"', '"1.0"', '"1.0"'))
        self.assertTrue(store.loaded, store.load_error)
        self.assertEqual(store.get("alpha").tasks, {"ask": ["t"]})
        # The version is checked one document at a time: a mixed bundle loads.
        self.assertTrue(hook.AgentDeclarationStore(self._bundle('"0.2"', "v0.3", '"1.0"')).loaded)

    def test_the_bundle_root_index_is_not_read(self):
        root = pathlib.Path(self._bundle('"0.2"', '"0.2"', '"1.0"', '"1.0"'))
        (root / "alpha" / "index.md").write_text('---\nokf_version: "0.2"\n---\n\n# Alpha\n')
        self.assertTrue(hook.AgentDeclarationStore(str(root)).loaded)

    def test_refusals_are_named_and_clear_every_agent(self):
        for args, needle in (
                (("v0.9",), "unsupported okf_version 'v0.9'"),
                ((None,), "missing okf_version"),
                (('"0.2"',), "unsupported zuno.profile None"),
                (('"0.2"', "v0.2", '"2.0"'), "unsupported zuno.profile '2.0'"),
                (("0.2", "v0.2", '"1.0"'), "unsupported okf_version 0.2"),  # an unquoted 0.2 is a YAML number
                (("v0.3", "v0.2", '"1.0"'), 'zuno.profile is only valid with okf_version "0.2"'),
                (("v0.2", "v0.9"), "unsupported okf_version 'v0.9'")):  # the task document is checked too
            with self.subTest(args=args):
                store = hook.AgentDeclarationStore(self._bundle(*args))
                self.assertFalse(store.loaded)
                self.assertIn(needle, store.load_error)
                self.assertEqual(store._agents, {})


if __name__ == "__main__":
    unittest.main()
