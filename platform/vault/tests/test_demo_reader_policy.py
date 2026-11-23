"""demo-reader: the presenter's read-only Vault UI identity (ADR-0628, WP-331).

The policy is what can reach the screen of a public demo and its GIF, so it is
checked as text: read and list only, no secret value (zuno/data), no sudo, no
Transit operation that uses a key, and the role that carries it lives 30
minutes at most, bound to one ServiceAccount the vault role creates.

Run from the repository root:
    python3 platform/vault/tests/test_demo_reader_policy.py
"""
from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
CONFIGURE = ROOT / "ansible/roles/vault/kustomize/configure"
POLICY = CONFIGURE / "vault-demo-reader.hcl"
SCRIPT = CONFIGURE / "configure.sh"
KUSTOMIZATION = CONFIGURE / "kustomization.yaml"
CONFIGURE_JOB = ROOT / "ansible/roles/vault/tasks/run_configure_job.yml"

PATH_RE = re.compile(r'path\s+"([^"]+)"\s*\{\s*capabilities\s*=\s*\[([^\]]*)\]\s*\}', re.S)
ALLOWED = {"read", "list"}


def policy_paths(text: str) -> dict[str, set[str]]:
    """path -> capabilities, from the policy text with its comments removed."""
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    paths = {m.group(1): {c.strip().strip('"') for c in m.group(2).split(",") if c.strip()}
             for m in PATH_RE.finditer(body)}
    # Every `path` stanza must have been understood: a stanza this parser missed is not checked.
    assert len(paths) == body.count("path "), "a path stanza of the policy was not parsed"
    return paths


class Policy(unittest.TestCase):
    def setUp(self):
        self.paths = policy_paths(POLICY.read_text(encoding="utf-8"))

    def test_read_and_list_only(self):
        for path, caps in self.paths.items():
            self.assertTrue(caps, path)
            self.assertLessEqual(caps, ALLOWED, f"{path}: {sorted(caps - ALLOWED)}")

    def test_no_secret_value_can_be_read(self):
        for path in self.paths:
            self.assertFalse(path.startswith("zuno/data"), path)
            self.assertNotIn("*", path.split("/")[0], path)   # no glob over a whole engine
            self.assertNotEqual(path, "zuno/*")

    def test_no_transit_operation_with_a_key(self):
        for path in self.paths:
            if path.startswith("transit/"):
                self.assertTrue(path in ("transit/keys", "transit/keys/*"), path)

    def test_no_sys_path_that_needs_sudo_or_writes(self):
        for path in self.paths:
            if path.startswith("sys/"):
                self.assertFalse(path.startswith(("sys/audit", "sys/storage", "sys/raw", "sys/seal",
                                                  "sys/rotate", "sys/leases", "sys/tools")), path)

    def test_the_tour_is_covered(self):
        for path in ("zuno/metadata/*", "transit/keys", "pki/roles", "auth/kubernetes/role", "sys/policies/acl"):
            self.assertIn(path, self.paths)


class Role(unittest.TestCase):
    def test_role_is_bound_and_short_lived(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("vault policy write demo-reader /policies/vault-demo-reader.hcl", script)
        m = re.search(r"vault write auth/kubernetes/role/demo-reader((?:[^\n]*\\\n)*[^\n]*)", script)
        self.assertIsNotNone(m)
        args = dict(a.split("=", 1) for a in m.group(1).replace("\\\n", " ").split() if "=" in a)
        self.assertEqual(args, {
            "bound_service_account_names": "vault-demo-reader",
            "bound_service_account_namespaces": "zuno-vault",
            "policies": "demo-reader",
            "ttl": "30m",
            "max_ttl": "30m",
        })

    def test_policy_file_is_mounted_and_service_account_created(self):
        self.assertIn("- vault-demo-reader.hcl", KUSTOMIZATION.read_text(encoding="utf-8"))
        self.assertIn("    - vault-demo-reader\n", CONFIGURE_JOB.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
