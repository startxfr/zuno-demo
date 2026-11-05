"""ADR-0572 clause 4: platform/supply-chain/check_unifai_identity.py.

Run from the repository root:
    python3 platform/supply-chain/tests/test_check_unifai_identity.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_unifai_identity as c  # noqa: E402


class Identity(unittest.TestCase):
    def test_external_identity_passes(self):
        doc = {"zuno_unifai_values": {"stack": {"identity": {"realm": "zuno", "clientId": "unifai"}}}}
        self.assertEqual(c.check_cluster("demo", doc), [])
        self.assertEqual(c.check_cluster("demo", {}), [])

    def test_a_keycloak_identity_in_a_cluster_file_fails(self):
        doc = {"zuno_unifai_values": {"stack": {"identity": {"keycloak": {"enabled": True}}}}}
        findings = c.check_cluster("demo", doc)
        self.assertEqual(len(findings), 1)
        self.assertIn("identity.keycloak", findings[0])

    def test_the_chart_must_declare_external_and_no_keycloak_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            c.REPO_ROOT = root
            tpl = root / "templates"
            tpl.mkdir()
            (tpl / "unifaistack.yaml").write_text("spec:\n  identity:\n    external:\n      url: https://keycloak.x\n")
            self.assertEqual(c.check_chart(tpl), [])
            (tpl / "unifaistack.yaml").write_text("spec:\n  identity:\n    keycloak:\n      enabled: true\n")
            findings = c.check_chart(tpl)
            self.assertEqual(len(findings), 2)  # no external, and a keycloak key
        c.REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

    def test_the_repository_passes(self):
        root = pathlib.Path(__file__).resolve().parents[3]
        out = subprocess.run([sys.executable, str(root / "platform/supply-chain/check_unifai_identity.py")],
                             cwd=root, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)


if __name__ == "__main__":
    unittest.main()
