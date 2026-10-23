"""Tests for platform/supply-chain/admit_okf_bundle.py (WP-160).

The signature path is exercised live against quay.io (WP-160 brief); these
tests cover what needs no registry: validation against the platform
bindings, the promotion diff, the lock file and archive extraction.

Run from the repository root:
    python3 platform/supply-chain/tests/test_admit_okf_bundle.py
"""
from __future__ import annotations

import gzip
import io
import pathlib
import shutil
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import admit_okf_bundle as admit  # noqa: E402

AGENT = """---
okf_version: v0.2
type: agent
title: Demo
zuno:
  name: demo
  tasks: [ask]
  access: {groups: [agent_demo]}
  model: {preferred_classification: C1}
---
"""
TASK = """---
okf_version: v0.2
type: task
title: Ask
zuno:
  allowed_tools: [search_docs]
  allowed_knowledge: [knowledge.tech]
---
"""


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class AdmitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.release = self.tmp / "release"
        write(self.release / "agents/demo/agent.okf.md", AGENT)
        write(self.release / "agents/demo/tasks/ask.md", TASK)
        write(self.release / "policies/tools/tool-policy.yaml",
              "tools:\n  - tool: search_docs\n    capability: knowledge.tech.search\n")
        write(self.release / "policies/models/model-catalog.yaml",
              "models:\n  - {name: local, kind: local}\n  - {name: spare, kind: local}\n")
        write(self.release / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, preferred: [local]}\n")
        platform = self.tmp / "platform"
        write(platform / "provider-routing.yaml", "providers:\n  - {name: local}\n")
        write(platform / "tool-bindings.yaml", "bindings:\n  - capability: knowledge.tech.search\n")
        write(platform / "unifai-values.yaml", "ragSources: []\n")
        write(platform / "redhat-docs.yaml",
              "sources:\n  - {name: rh-x, tags: [knowledge.tech, product:x]}\n")
        self.saved = (admit.PROVIDER_ROUTING_PATH, admit.TOOL_BINDINGS_PATH, admit.UNIFAI_RAG_SOURCE_FILES)
        admit.PROVIDER_ROUTING_PATH = platform / "provider-routing.yaml"
        admit.TOOL_BINDINGS_PATH = platform / "tool-bindings.yaml"
        admit.UNIFAI_RAG_SOURCE_FILES = ((platform / "unifai-values.yaml", "ragSources"),
                                         (platform / "redhat-docs.yaml", "sources"))

    def tearDown(self) -> None:
        admit.PROVIDER_ROUTING_PATH, admit.TOOL_BINDINGS_PATH, admit.UNIFAI_RAG_SOURCE_FILES = self.saved
        shutil.rmtree(self.tmp)

    def copy(self) -> pathlib.Path:
        other = self.tmp / "other"
        shutil.copytree(self.release, other)
        return other


class ValidateTest(AdmitTestCase):
    def test_servable_release(self) -> None:
        errors, warnings = admit.validate(self.release)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, ["model catalog names 'spare', which provider-routing.yaml does not bind"])

    def test_unbound_model(self) -> None:
        write(self.release / "policies/models/model-catalog.yaml", "models:\n  - {name: local}\n  - {name: big}\n")
        write(self.release / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, preferred: [big]}\n")
        self.assertIn("not bound in provider-routing.yaml", admit.validate(self.release)[0][0])

    def test_model_outside_the_catalog(self) -> None:
        write(self.release / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, prefer: [ghost]}\n")
        self.assertIn("absent from the release's model catalog", admit.validate(self.release)[0][0])

    def test_tool_without_binding(self) -> None:
        write(self.release / "policies/tools/tool-policy.yaml",
              "tools:\n  - tool: search_docs\n    capability: nowhere.do\n")
        self.assertIn("no backend binding", admit.validate(self.release)[0][0])

    def test_tool_absent_from_policy(self) -> None:
        write(self.release / "policies/tools/tool-policy.yaml", "tools: []\n")
        self.assertIn("absent from the release's tool policy", admit.validate(self.release)[0][0])

    def test_tool_bound_by_alias(self) -> None:
        write(self.release / "policies/tools/tool-policy.yaml",
              "tools:\n  - tool: search_docs\n    capability: other.cap\n")
        write(admit.TOOL_BINDINGS_PATH, "bindings:\n  - capability: x.y.z\n    aliases: [search_docs]\n")
        self.assertEqual(admit.validate(self.release)[0], [])

    def test_v03_widening_is_refused_at_admission(self) -> None:
        # ADR-0579 clause 5, re-checked here after the agents repository's CI.
        write(self.release / "agents/demo/agent.okf.md",
              AGENT.replace("okf_version: v0.2", "okf_version: v0.3")
                   .replace("  model: {preferred_classification: C1}\n",
                            "  model: {preferred_classification: C1}\n  limits: {max_tokens: 99999}\n"))
        write(self.release / "policies/limits/limits-policy.yaml", "max_tokens: 8192\n")
        errors = admit.validate(self.release)[0]
        self.assertEqual(len(errors), 1)
        self.assertIn("exceeds the corp ceiling 8192", errors[0])

    def test_unserved_knowledge_domain_is_a_warning(self) -> None:
        # WP-168: nothing serves the domain (no UnifAI source tagged with it).
        # Allowing it grants no access, so the release stays servable.
        write(admit.UNIFAI_RAG_SOURCE_FILES[1][0], "sources:\n  - {name: rh-x, tags: [product:x]}\n")
        errors, warnings = admit.validate(self.release)
        self.assertEqual(errors, [])
        self.assertTrue(any("which no UnifAI RAG source serves" in w for w in warnings), warnings)

    def test_knowledge_domain_served_by_a_rag_source_in_the_chart_values(self) -> None:
        write(admit.UNIFAI_RAG_SOURCE_FILES[1][0], "sources: []\n")
        write(admit.UNIFAI_RAG_SOURCE_FILES[0][0],
              "ragSources:\n  - {name: tech-satellite, tags: [knowledge.tech], type: confluence}\n")
        errors, warnings = admit.validate(self.release)
        self.assertEqual(errors, [])
        self.assertFalse(any("knowledge.tech" in w for w in warnings), warnings)


class DiffTest(AdmitTestCase):
    def test_first_admission_lists_agents(self) -> None:
        self.assertIn("**demo** added", admit.diff(None, self.release))

    def test_no_change(self) -> None:
        self.assertEqual(admit.diff(self.release, self.copy()), "- no change in agents, routing or corp policies")

    def test_task_tools_groups_and_routing(self) -> None:
        new = self.copy()
        write(new / "agents/demo/agent.okf.md", AGENT.replace("[agent_demo]", "[agent_demo, board]"))
        write(new / "agents/demo/tasks/ask.md", TASK.replace("[search_docs]", "[search_docs, web_search]"))
        write(new / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, preferred: [spare, local]}\n")
        text = admit.diff(self.release, new)
        self.assertIn("groups +board", text)
        self.assertIn("ask tools +web_search", text)
        self.assertIn("model routing `demo/ask`: models +spare", text)

    def test_reorder_only(self) -> None:
        write(self.release / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, preferred: [local, spare]}\n")
        new = self.copy()
        write(new / "policies/model-routing/model-routing-policy.yaml",
              "preferences:\n  - {agent: demo, task: ask, preferred: [spare, local]}\n")
        self.assertIn("order now spare, local", admit.diff(self.release, new))

    def test_corp_policy_added_and_changed(self) -> None:
        new = self.copy()
        write(new / "policies/quotas/quota-policy.yaml", "classes: {}\n")
        write(new / "policies/tools/tool-policy.yaml", "tools: []\n")
        text = admit.diff(self.release, new)
        self.assertIn("corp policy `quotas/quota-policy.yaml` added", text)
        self.assertIn("corp policy `tools/tool-policy.yaml` changed", text)


class LockAndArchiveTest(unittest.TestCase):
    def test_lock_round_trip_and_digest_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock = pathlib.Path(tmp) / "agents.lock"
            self.assertIsNone(admit.read_lock(lock))
            ref = "quay.io/zuno/okf-corp@sha256:" + "a" * 64
            admit.write_lock(ref, "v0.1.1", lock)
            self.assertEqual(admit.read_lock(lock), ref)
            with self.assertRaises(admit.AdmissionError):
                admit.write_lock("quay.io/zuno/okf-corp:v0.1.1", "v0.1.1", lock)

    def test_archive_escape_is_refused(self) -> None:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz, tarfile.open(fileobj=gz, mode="w") as tar:
            info = tarfile.TarInfo("../escape.txt")
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(admit.AdmissionError):
                admit._untar(buf.getvalue(), pathlib.Path(tmp) / "out")


if __name__ == "__main__":
    unittest.main()
