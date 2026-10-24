"""ADR-0508 / WP-51: the admission OKF reader (platform/supply-chain/
admit_okf_bundle.py `agents_view`, also behind generate_stack_config.py)
against the OKF conformance cases.

Every case of the conformance set (zuno-demo-agents/conformance/cases) is read
through `agents_view` and compared with the `admission` section of its
expected.json (the `version` field comes from okf-index.json, which the cases
do not carry, so it is left out of the comparison). The cases come from
ZUNO_OKF_CONFORMANCE_DIR or the admitted release; with none available the case
tests are skipped, and say so.

Run from the repository root:
    python3 platform/okf/tests/test_okf_conformance.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform" / "okf"))

import release_cache  # noqa: E402

admit = release_cache.admit
CASES = release_cache.conformance_dir()
SKIP = "no OKF conformance cases (set ZUNO_OKF_CONFORMANCE_DIR); fixture tests not run"


def _case_dirs():
    return sorted(p for p in CASES.iterdir() if p.is_dir()) if CASES else []


class ConformanceCases(unittest.TestCase):
    def test_every_case_reads_as_expected(self):
        if CASES is None:
            self.skipTest(SKIP)
        self.assertTrue(_case_dirs())
        for case in _case_dirs():
            with self.subTest(case=case.name):
                expected = json.loads((case / "expected.json").read_text())["admission"]
                if expected["error"] is not None:
                    # The contract is a refusal naming the cause; the type differs
                    # (ValueError for content, OSError for a missing task file).
                    with self.assertRaises((ValueError, OSError)) as caught:
                        admit.agents_view(case)
                    self.assertIn(expected["error"], str(caught.exception))
                    continue
                view = admit.agents_view(case)
                for agent in view.values():
                    agent.pop("version")
                self.assertEqual(view, expected["agents"])


class DelegationNarrowing(unittest.TestCase):
    """The admission narrowing rule (platform/supply-chain/okf_narrowing.py) on the `delegation` section
    of the cases: valid cases pass, `narrowing-` cases raise the expected finding. The ceiling comes from a
    temporary corp policy, because the pinned release may predate `max_delegation_depth`."""

    def test_narrowing_findings_match_the_cases(self):
        if CASES is None:
            self.skipTest(SKIP)
        sys.path.insert(0, str(ROOT / "platform" / "supply-chain"))
        import okf_narrowing

        policies = pathlib.Path(tempfile.mkdtemp())
        (policies / "limits").mkdir()
        (policies / "limits" / "limits-policy.yaml").write_text("max_delegation_depth: 2\n")
        corp = okf_narrowing.Corp(policies)
        for case in _case_dirs():
            section = json.loads((case / "expected.json").read_text()).get("delegation")
            if section is None:
                continue
            with self.subTest(case=case.name):
                findings = [f for b in sorted((case / "agents").iterdir())
                            for f in okf_narrowing.check_bundle(b, corp, case)]
                needle = section.get("narrowing_error")
                if needle is None:
                    self.assertEqual(findings, [])
                else:
                    self.assertTrue(any(needle in f for f in findings), findings)


class VersionCheck(unittest.TestCase):
    def _release(self, version):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "agents" / "alpha" / "tasks").mkdir(parents=True)
        head = f"okf_version: {version}\n" if version else ""
        (root / "agents" / "alpha" / "agent.okf.md").write_text(
            f"---\n{head}type: agent\nzuno:\n  status: active\n  tasks: [ask]\n---\nx\n")
        (root / "agents" / "alpha" / "tasks" / "ask.md").write_text(
            "---\nokf_version: v0.2\ntype: task\nzuno:\n  allowed_tools: [t]\n---\nx\n")
        return root

    def test_supported_versions_read(self):
        self.assertEqual(admit.SUPPORTED_OKF_VERSIONS, ("v0.2", "v0.3"))
        for version in admit.SUPPORTED_OKF_VERSIONS:
            self.assertIn("alpha", admit.agents_view(self._release(version)))

    def test_unsupported_missing_and_frontmatterless_are_refused_by_name(self):
        for version, needle in (("v0.9", "unsupported okf_version 'v0.9'"), (None, "missing okf_version")):
            with self.assertRaises(ValueError) as caught:
                admit.agents_view(self._release(version))
            self.assertIn(needle, str(caught.exception))
        release = self._release("v0.2")
        (release / "agents" / "alpha" / "agent.okf.md").write_text("# prose only\n")
        with self.assertRaises(ValueError):
            admit.agents_view(release)


if __name__ == "__main__":
    unittest.main()
