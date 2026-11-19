"""check_docs: the "Stress and coverage" table of docs/demo/README.md against the demos and the stress drivers (ADR-0624).

Synthetic README text and id lists; the real tree is covered by running check_docs.py itself in CI.

Run from the repository root:
    python3 platform/docs/tests/test_stress_table.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_docs  # noqa: E402

README = """# Demos

## Stress and coverage

The samplers `saturation` serve all of them, `load-ai-gateway` serves none.

| Demo id | Stress drivers | Status |
|---|---|---|
| dify | `dify`, `dify-state` | replayed |
| vault-pki | `vault-pki-state` | state only |
| claude-code-sovereign | `claude-code-sovereign`, `-state` | replayed |
| five-experiences, three-experiences | the drivers of the scenarios they list | composition |
| agentic-ai, rhoai-end-to-end (workshops) | none | compositions |

## Personas
`not-a-driver` is outside the section.
"""
DEMOS = ["dify", "vault-pki", "claude-code-sovereign", "five-experiences", "three-experiences", "agentic-ai", "rhoai-end-to-end"]
DRIVERS = ["dify", "dify-state", "vault-pki-state", "claude-code-sovereign", "claude-code-sovereign-state", "saturation", "load-ai-gateway"]


def messages(readme=README, demos=DEMOS, drivers=DRIVERS):
    return [f.message for f in check_docs.stress_table_findings(readme, demos, drivers)]


class StressTable(unittest.TestCase):
    def test_a_consistent_table_has_no_finding(self):
        self.assertEqual(messages(), [])

    def test_a_demo_missing_from_the_table_is_named_with_the_file_to_edit(self):
        found = messages(demos=DEMOS + ["new-demo"])
        self.assertEqual(len(found), 1)
        self.assertIn("'new-demo'", found[0])
        self.assertIn("docs/demo/README.md", found[0])

    def test_a_driver_missing_from_the_table_is_named(self):
        found = messages(drivers=DRIVERS + ["multi-gateway"])
        self.assertEqual(len(found), 1)
        self.assertIn("multi-gateway", found[0])
        self.assertIn("evaluations/stress/", found[0])

    def test_a_cited_driver_that_does_not_exist_is_named(self):
        found = messages(drivers=[d for d in DRIVERS if d != "dify-state"])
        self.assertEqual(len(found), 1)
        self.assertIn("`dify-state`", found[0])
        self.assertIn("no stress driver", found[0])

    def test_the_state_shorthand_expands_to_the_demos_own_id(self):
        self.assertIn("claude-code-sovereign-state", DRIVERS)
        self.assertEqual(messages(), [])

    def test_a_missing_section_is_one_finding(self):
        self.assertEqual(len(messages(readme="# Demos\n")), 1)

    def test_ids_outside_the_section_are_ignored(self):
        self.assertNotIn("not-a-driver", " ".join(messages()))

    def test_the_registration_patterns_catch_helpers(self):
        for text, want in (('@register("a-b", family="x")', "a-b"), ('x = _register_proxy("dify", "ns", "E")', "dify"),
                           ("@register(\n    'c-d')", "c-d")):
            self.assertEqual(check_docs.STRESS_DRIVER_RE.findall(text), [want], text)


if __name__ == "__main__":
    unittest.main()
