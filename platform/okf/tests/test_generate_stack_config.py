"""Tests for platform/okf/generate_stack_config.py (WP-164).

Run from the repository root:
    python3 platform/okf/tests/test_generate_stack_config.py
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import generate_stack_config as gen  # noqa: E402
import yaml  # noqa: E402

AGENT = """---
okf_version: v0.2
type: agent
title: {name}
zuno:
  name: {name}
  tasks: [one, two]
  access: {{groups: [agent_{name}]}}
  model: {{preferred_classification: C2}}
---
"""
TASK = """---
okf_version: v0.2
type: task
title: t
zuno:
  allowed_tools: {tools}
  allowed_knowledge: {domains}
---
"""


class GenerateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = pathlib.Path(tempfile.mkdtemp())
        for name in ("beta", "alpha"):
            agent = self.dir / "agents" / name
            (agent / "tasks").mkdir(parents=True)
            (agent / "agent.okf.md").write_text(AGENT.format(name=name))
            (agent / "tasks" / "one.md").write_text(TASK.format(tools="[web_search]", domains="[knowledge.tech]"))
            (agent / "tasks" / "two.md").write_text(TASK.format(tools="[search_confluence, web_search]",
                                                                domains="[]"))
        (self.dir / "okf-index.json").write_text(json.dumps({
            "release": "0.2.0", "channel": "release",
            "agents": [{"name": n, "version": "1.0.0", "okfVersion": "v0.2",
                        "reference": f"quay.io/zuno/okf-{n}@sha256:{c * 64}"}
                       for n, c in (("alpha", "a"), ("beta", "b"))],
        }))

    def tearDown(self) -> None:
        shutil.rmtree(self.dir)

    def test_derived_configuration(self) -> None:
        config = gen.build(self.dir, "quay.io/zuno/okf-corp@sha256:" + "c" * 64)
        self.assertEqual(config["release"], "0.2.0")
        self.assertEqual(config["keycloak"]["groups"], ["agent_alpha", "agent_beta"])
        alpha = config["agents"]["alpha"]
        self.assertEqual(alpha["toolCapabilities"], ["search_confluence", "web_search"])
        self.assertEqual(alpha["knowledgeDomains"], ["knowledge.tech"])
        self.assertEqual(alpha["tasks"], ["one", "two"])
        self.assertEqual([b["name"] for b in config["unifai"]["bundles"]], ["alpha", "beta"])
        bundle = config["unifai"]["bundles"][0]
        self.assertTrue(bundle["reference"].endswith("a" * 64))
        self.assertEqual(bundle["ceilings"], {"toolCapabilities": ["search_confluence", "web_search"],
                                              "knowledgeDomains": ["knowledge.tech"],
                                              "minClassification": "C2"})

    def test_render_is_stable_and_alias_free(self) -> None:
        text = gen.render(gen.build(self.dir, None))
        self.assertEqual(text, gen.render(gen.build(self.dir, None)))
        self.assertNotIn("&id", text)
        self.assertTrue(text.startswith("# GENERATED"))
        self.assertEqual(yaml.safe_load(text)["agents"]["beta"]["version"], "1.0.0")

    def test_no_release_pinned(self) -> None:
        config = gen.build(None, None)
        self.assertEqual(config["unifai"]["bundles"], [])
        self.assertIsNone(config["release"])
        self.assertIn("publish", config["unifai"]["verify"]["keyless"]["subjectRegExp"])

    def test_keyless_identity_comes_from_identity_yaml(self) -> None:
        keyless = gen.build(self.dir, None)["unifai"]["verify"]["keyless"]
        self.assertEqual(keyless["issuer"], "https://token.actions.githubusercontent.com")
        self.assertTrue(keyless["subjectRegExp"].endswith("publish\\.yml@refs/tags/v"))


if __name__ == "__main__":
    unittest.main()
