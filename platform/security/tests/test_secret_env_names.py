"""check_no_hardcoded_secret_values: which env var names are exempt from the
"secret-like names must use secretKeyRef" rule (ADR-0052/ADR-0111).

A `*_PATH` (location of a mounted credential file) and a `*_ENV` (name of another
variable) hold no credential; a literal `*_TOKEN` or `*_PASSWORD` still fails.

Run from the repository root:
    python3 platform/security/tests/test_secret_env_names.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_workload_hardening as hardening  # noqa: E402


def _deployment(env):
    return {"kind": "Deployment", "metadata": {"name": "d"},
            "spec": {"template": {"spec": {"containers": [{"name": "c", "env": env}]}}}}


class SecretEnvNames(unittest.TestCase):
    def _findings(self, env):
        saved = hardening._helm_template
        hardening._helm_template = lambda chart, set_values=None: [_deployment(env)]
        try:
            findings = hardening.Findings()
            hardening.check_no_hardcoded_secret_values("demo", findings)
            return [r for r in findings.results if not r.passed]
        finally:
            hardening._helm_template = saved

    def test_a_path_to_a_mounted_credential_is_not_a_secret(self):
        failures = self._findings([{"name": "MAAS_SA_TOKEN_PATH", "value": "/var/run/secrets/maas/token"}])
        self.assertEqual(failures, [])

    def test_a_meta_variable_naming_another_variable_is_not_a_secret(self):
        failures = self._findings([{"name": "MAAS_GATEWAY_API_KEY_ENV", "value": "MAAS_GATEWAY_API_KEY"}])
        self.assertEqual(failures, [])

    def test_a_literal_credential_still_fails(self):
        for name in ("API_TOKEN", "DB_PASSWORD", "CLIENT_SECRET"):
            failures = self._findings([{"name": name, "value": "hunter2"}])
            self.assertEqual(len(failures), 1, name)

    def test_a_secretkeyref_credential_passes(self):
        env = [{"name": "API_TOKEN", "valueFrom": {"secretKeyRef": {"name": "s", "key": "k"}}}]
        self.assertEqual(self._findings(env), [])


if __name__ == "__main__":
    unittest.main()
