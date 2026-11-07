"""check_secret_access: the per-namespace SecretStore rules (ADR-0602 clause 2,
WP-223, finding C2).

Each case feeds the rule function synthetic rendered objects and a small
table, so no helm is needed; the real repository is covered by running the
check itself in CI.

Run from the repository root:
    python3 platform/vault/tests/test_check_secret_access.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_secret_access as csa  # noqa: E402

SERVER = "https://zuno-vault.zuno-vault.svc:8200"


def store(namespace, name="vault", role=None, sa="vault-reader", server=SERVER):
    return csa.Source("test", namespace, {
        "kind": "SecretStore",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {"provider": {"vault": {
            "server": server, "path": "zuno", "version": "v2",
            "auth": {"kubernetes": {"mountPath": "kubernetes", "role": role or f"ns-{namespace}",
                                    "serviceAccountRef": {"name": sa}}},
        }}},
    })


def externalsecret(namespace, keys, ref=None, name="es", data_from=None):
    spec = {
        "secretStoreRef": ref if ref is not None else {"kind": "SecretStore", "name": "vault"},
        "data": [{"secretKey": f"k{i}", "remoteRef": {"key": key, "property": "p"}} for i, key in enumerate(keys)],
    }
    if data_from:
        spec["dataFrom"] = data_from
    return csa.Source("test", namespace, {"kind": "ExternalSecret", "metadata": {"name": name}, "spec": spec})


class SecretAccessRules(unittest.TestCase):
    def failures(self, sources, table):
        findings = csa.Findings()
        csa.check_sources(sources, table, findings)
        return findings.failures

    def test_a_compliant_namespace_passes(self):
        table = {"zuno-auth": ["keycloak/admin", "redis/session-store"]}
        sources = [store("zuno-auth"), externalsecret("zuno-auth", ["keycloak/admin", "redis/session-store"])]
        self.assertEqual(self.failures(sources, table), [])

    def test_a_clustersecretstore_reference_fails(self):
        table = {"zuno-ai-run": ["smtp/technical"]}
        ref = {"kind": "ClusterSecretStore", "name": "vault-backend"}
        failures = self.failures([store("zuno-ai-run"), externalsecret("zuno-ai-run", ["smtp/technical"], ref=ref)], table)
        self.assertTrue(any("ClusterSecretStore" in f and "store ref" in f for f in failures), failures)

    def test_a_store_with_another_name_fails(self):
        table = {"zuno-ai-run": ["smtp/technical"]}
        ref = {"kind": "SecretStore", "name": "other"}
        failures = self.failures([store("zuno-ai-run"), externalsecret("zuno-ai-run", ["smtp/technical"], ref=ref)], table)
        self.assertTrue(any("store ref" in f for f in failures), failures)

    def test_a_key_outside_the_namespace_list_fails(self):
        # The C2 attack: an ExternalSecret in zuno-ai-run asking for the Keycloak admin.
        table = {"zuno-ai-run": ["smtp/technical"], "zuno-auth": ["keycloak/admin"]}
        sources = [store("zuno-ai-run"), store("zuno-auth"),
                   externalsecret("zuno-ai-run", ["smtp/technical", "keycloak/admin"]),
                   externalsecret("zuno-auth", ["keycloak/admin"])]
        failures = self.failures(sources, table)
        self.assertTrue(any("'keycloak/admin' not granted to zuno-ai-run" in f for f in failures), failures)

    def test_a_namespace_missing_from_the_table_fails(self):
        failures = self.failures([externalsecret("zuno-rogue", ["keycloak/admin"])], {})
        self.assertTrue(any("zuno-rogue" in f and "no entry" in f for f in failures), failures)

    def test_a_key_repeating_the_mount_fails(self):
        table = {"openshift-lightspeed": ["zuno/lightspeed/mcp-token"]}
        failures = self.failures([store("openshift-lightspeed"),
                                  externalsecret("openshift-lightspeed", ["zuno/lightspeed/mcp-token"])], table)
        self.assertTrue(any("repeats the mount" in f for f in failures), failures)

    def test_an_unused_grant_fails(self):
        table = {"zuno-auth": ["keycloak/admin", "keycloak/console"]}
        failures = self.failures([store("zuno-auth"), externalsecret("zuno-auth", ["keycloak/admin"])], table)
        self.assertTrue(any("'keycloak/console' is read by no ExternalSecret" in f for f in failures), failures)

    def test_a_table_namespace_without_a_store_fails(self):
        table = {"zuno-auth": ["keycloak/admin"]}
        failures = self.failures([externalsecret("zuno-auth", ["keycloak/admin"])], table)
        self.assertTrue(any("exactly one rendered SecretStore" in f and "found 0" in f for f in failures), failures)

    def test_two_stores_in_one_namespace_fail(self):
        table = {"zuno-auth": ["keycloak/admin"]}
        failures = self.failures([store("zuno-auth"), store("zuno-auth"),
                                  externalsecret("zuno-auth", ["keycloak/admin"])], table)
        self.assertTrue(any("found 2" in f for f in failures), failures)

    def test_a_store_borrowing_another_namespace_role_fails(self):
        table = {"zuno-ai-run": ["smtp/technical"]}
        failures = self.failures([store("zuno-ai-run", role="ns-zuno-auth"),
                                  externalsecret("zuno-ai-run", ["smtp/technical"])], table)
        self.assertTrue(any("Vault role must be ns-zuno-ai-run" in f for f in failures), failures)

    def test_stores_disagreeing_on_the_server_fail(self):
        table = {"a": ["x/y"], "b": ["x/y"]}
        failures = self.failures([store("a"), store("b", server="http://elsewhere:8200"),
                                  externalsecret("a", ["x/y"]), externalsecret("b", ["x/y"])], table)
        self.assertTrue(any("disagree on the Vault server" in f for f in failures), failures)

    def test_a_rendered_clustersecretstore_fails(self):
        css = csa.Source("test", "", {"kind": "ClusterSecretStore", "metadata": {"name": "vault-backend"}, "spec": {}})
        failures = self.failures([css], {})
        self.assertTrue(any("ClusterSecretStore vault-backend rendered" in f for f in failures), failures)

    def test_a_prefix_grant_covers_extract_and_find(self):
        table = {"zuno-ai-run": ["providers/*"]}
        data_from = [{"extract": {"key": "providers/openai"}}, {"find": {"path": "providers", "name": {"regexp": ".*"}}}]
        sources = [store("zuno-ai-run"), externalsecret("zuno-ai-run", ["providers/gemini"], data_from=data_from)]
        self.assertEqual(self.failures(sources, table), [])

    def test_a_find_needs_a_prefix_grant(self):
        table = {"zuno-ai-run": ["providers/openai"]}
        data_from = [{"find": {"path": "providers"}}]
        sources = [store("zuno-ai-run"), externalsecret("zuno-ai-run", ["providers/openai"], data_from=data_from)]
        failures = self.failures(sources, table)
        self.assertTrue(any("'providers/*' not granted" in f for f in failures), failures)

    def test_a_generator_only_externalsecret_reads_no_store(self):
        gen = csa.Source("test", "zuno-ai-run", {"kind": "ExternalSecret", "metadata": {"name": "marker"}, "spec": {
            "dataFrom": [{"sourceRef": {"generatorRef": {"kind": "Password", "name": "marker"}}}]}})
        table = {"zuno-ai-run": ["smtp/technical"]}
        self.assertEqual(self.failures([gen, store("zuno-ai-run"), externalsecret("zuno-ai-run", ["smtp/technical"])], table), [])

    def test_a_per_entry_store_ref_is_checked_too(self):
        es = externalsecret("zuno-ai-run", ["smtp/technical"])
        es.doc["spec"]["data"][0]["sourceRef"] = {"storeRef": {"kind": "ClusterSecretStore", "name": "vault-backend"}}
        failures = self.failures([store("zuno-ai-run"), es], {"zuno-ai-run": ["smtp/technical"]})
        self.assertTrue(any("store ref" in f for f in failures), failures)


if __name__ == "__main__":
    unittest.main(verbosity=2)
