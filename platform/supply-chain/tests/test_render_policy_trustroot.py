"""WP-178: platform/supply-chain/render_policy_trustroot.py.

Run from the repository root:
    python3 platform/supply-chain/tests/test_render_policy_trustroot.py
"""
from __future__ import annotations

import base64
import json
import pathlib
import ssl
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import render_policy_trustroot as r  # noqa: E402

ROOT = json.loads(r.TRUSTED_ROOT.read_text(encoding="utf-8"))


def decode(text: str) -> str:
    return base64.b64decode(text).decode()


class Render(unittest.TestCase):
    def setUp(self):
        self.keys = yaml.safe_load(r.render(ROOT))["sigstoreKeys"]

    def test_the_committed_chart_file_is_the_rendering_of_the_trusted_root(self):
        self.assertEqual(r.OUTPUT.read_text(encoding="utf-8"), r.render(ROOT))

    def test_every_certificate_chain_is_base64_pem_and_parses(self):
        for entry in self.keys["certificateAuthorities"] + self.keys["timestampAuthorities"]:
            pem = decode(entry["certChain"])
            blocks = [b + "-----END CERTIFICATE-----\n" for b in pem.split("-----END CERTIFICATE-----\n") if b.strip()]
            self.assertGreaterEqual(len(blocks), 1)
            for block in blocks:
                self.assertTrue(ssl.PEM_cert_to_DER_cert(block))

    def test_only_ecdsa_log_keys_are_rendered(self):
        ecdsa = [e for e in ROOT["tlogs"] if e["publicKey"]["keyDetails"] == r.ECDSA]
        self.assertEqual(len(self.keys["tLogs"]), len(ecdsa))
        self.assertLess(len(self.keys["tLogs"]), len(ROOT["tlogs"]), "the Ed25519 Rekor v2 key must be left out")
        for log in self.keys["tLogs"] + self.keys["ctLogs"]:
            self.assertTrue(decode(log["publicKey"]).startswith("-----BEGIN PUBLIC KEY-----"))
            self.assertTrue(log["baseURL"].startswith("https://"))

    def test_the_public_good_instance_is_there(self):
        self.assertIn("https://fulcio.sigstore.dev", [c["uri"] for c in self.keys["certificateAuthorities"]])
        self.assertIn("https://rekor.sigstore.dev", [t["baseURL"] for t in self.keys["tLogs"]])


if __name__ == "__main__":
    unittest.main()
