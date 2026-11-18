"""The Open WebUI entries that keep the Zuno tools off the SaaS models of Praxis (ADR-0619 update of 2026-11-19).

    python3 platform/praxis/tests/test_open_webui_no_tools.py

Tests the pure part of ansible/roles/open_webui/files/model_overrides.py (what entry is written, when) and that the
role's ids follow the SaaS names of the Praxis chart. The part that talks to Open WebUI's database runs in its pod.
"""
from __future__ import annotations

import importlib.util
import pathlib
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("model_overrides", ROOT / "ansible/roles/open_webui/files/model_overrides.py")
mo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mo)

PUBLIC = {"principal_type": "user", "principal_id": "*", "permission": "read"}


class Desired(unittest.TestCase):
    def test_a_new_entry_has_no_tools_and_stays_public(self):
        entry = mo.desired("praxis.claude", None)
        self.assertEqual(entry["meta"]["toolIds"], [])
        self.assertEqual(entry["access_grants"], [PUBLIC])
        self.assertIsNone(entry["base_model_id"])
        self.assertEqual(entry["name"], "praxis.claude")
        self.assertTrue(entry["is_active"])

    def test_an_existing_entry_keeps_its_other_fields(self):
        existing = {"id": "praxis.claude", "name": "Claude (Praxis)", "base_model_id": None,
                    "meta": {"toolIds": ["server:mcp:zuno-mcp"], "description": "kept", "capabilities": {"vision": True}},
                    "params": {"temperature": 0.3}, "is_active": False,
                    "access_grants": [{"id": "g1", "principal_type": "group", "principal_id": "abc",
                                       "permission": "read", "resource_type": "model"}]}
        entry = mo.desired("praxis.claude", existing)
        self.assertEqual(entry["meta"], {"toolIds": [], "description": "kept", "capabilities": {"vision": True}})
        self.assertEqual(entry["params"], {"temperature": 0.3})
        self.assertEqual(entry["name"], "Claude (Praxis)")
        self.assertFalse(entry["is_active"])
        self.assertEqual(entry["access_grants"],
                         [{"principal_type": "group", "principal_id": "abc", "permission": "read"}, PUBLIC])


class NeedsWrite(unittest.TestCase):
    def test_missing_or_with_tools_or_private(self):
        self.assertTrue(mo.needs_write(None))
        self.assertTrue(mo.needs_write({"meta": {}, "access_grants": [PUBLIC]}))
        self.assertTrue(mo.needs_write({"meta": {"toolIds": ["x"]}, "access_grants": [PUBLIC]}))
        self.assertTrue(mo.needs_write({"meta": {"toolIds": []}, "access_grants": []}))

    def test_done_once(self):
        self.assertFalse(mo.needs_write({"meta": {"toolIds": []}, "access_grants": [dict(PUBLIC, id="g")]}))


class RoleIds(unittest.TestCase):
    def test_the_role_reads_the_saas_names_of_the_praxis_chart(self):
        saas = yaml.safe_load((ROOT / "gitops/charts/praxis/values.yaml").read_text())["saas"]
        self.assertEqual({saas["claude"]["name"], saas["codestral"]["name"]}, {"claude", "codestral-latest"})
        task = (ROOT / "ansible/roles/open_webui/tasks/install.yml").read_text()
        self.assertIn("gitops/charts/praxis/values.yaml", task)
        self.assertIn("files/model_overrides.py", task)


if __name__ == "__main__":
    unittest.main()
