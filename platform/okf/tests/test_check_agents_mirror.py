"""Tests for platform/okf/check_agents_mirror.py (WP-158 step 6).

Run from the repository root:
    python3 platform/okf/tests/test_check_agents_mirror.py
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_agents_mirror as mirror  # noqa: E402

AGENT = "---\nokf_version: v0.2\ntype: agent\ntitle: Demo\nzuno: {name: demo, tasks: [ask]}\n---\n"


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class MirrorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.release, self.local = self.tmp / "release", self.tmp / "local"
        for root in (self.release, self.local):
            write(root / "agents/demo/agent.okf.md", AGENT + "## Authorization matrix\n")
            write(root / "agents/demo/tasks/ask.md", "---\ntype: task\n---\nAsk.\n")
            write(root / "policies/tools/tool-policy.yaml", "tools: []\n")
        # what the local copy may legitimately differ in
        write(self.local / "agents/demo/agent.okf.md", AGENT + "## Authorization matrix (older wording)\n")
        write(self.local / "agents/demo/README.md", "local notes\n")
        write(self.local / "agents/demo/deployment/manifest-summary.md", "snapshot\n")
        write(self.local / "agents/demo/tests/test_x.py", "pass\n")
        write(self.release / "policies/limits/limits-policy.yaml", "max_tokens: 8192\n")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_mirror_ignores_generated_body_and_non_runtime_files(self) -> None:
        self.assertEqual(mirror.compare(self.release, self.local), [])

    def test_task_edited_here_is_reported(self) -> None:
        write(self.local / "agents/demo/tasks/ask.md", "---\ntype: task\n---\nAsk differently.\n")
        self.assertEqual(mirror.compare(self.release, self.local),
                         ["agents/demo/tasks/ask.md: differs from the release"])

    def test_frontmatter_and_policy_and_new_agent(self) -> None:
        write(self.local / "agents/demo/agent.okf.md", AGENT.replace("Demo", "Changed"))
        write(self.local / "policies/tools/tool-policy.yaml", "tools: [x]\n")
        write(self.local / "agents/extra/agent.okf.md", AGENT)
        problems = mirror.compare(self.release, self.local)
        self.assertIn("agents/demo/agent.okf.md: frontmatter differs from the release", problems)
        self.assertIn("policies/tools/tool-policy.yaml: differs from the release", problems)
        self.assertTrue(any(p.startswith("agents/extra:") for p in problems))


if __name__ == "__main__":
    unittest.main()
