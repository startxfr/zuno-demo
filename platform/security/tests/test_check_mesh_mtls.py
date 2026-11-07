"""check_mesh_mtls: targeted mTLS and egress firewall rules (ADR-0602 / WP-224).

Each case feeds the rule functions synthetic rendered objects, so no helm is
needed; the real repository is covered by running the check itself in CI.
The namespaces chart's own guards (an exception without `reason:` or with an
empty host list fails `helm template`) are exercised at the end with helm.

Run from the repository root:
    python3 platform/security/tests/test_check_mesh_mtls.py
"""
from __future__ import annotations

import copy
import pathlib
import shutil
import subprocess
import sys
import unittest
import unittest.mock

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_mesh_mtls as cmm  # noqa: E402

CHART = cmm.REPO_ROOT / "gitops" / "charts" / "namespaces"


def pa(namespace, name="default", mode="PERMISSIVE", selector=None, ports=None, reason="router", workload_mode=None):
    spec = {}
    meta = {"name": name, "namespace": namespace, "annotations": {}}
    if selector:
        spec["selector"] = {"matchLabels": selector}
        if workload_mode:
            spec["mtls"] = {"mode": workload_mode}
    else:
        spec["mtls"] = {"mode": mode}
    if ports:
        spec["portLevelMtls"] = {p: {"mode": m} for p, m in ports.items()}
        if reason:
            meta["annotations"][cmm.REASON_ANNOTATION] = reason
    return cmm.Rendered("test", namespace, {"kind": "PeerAuthentication", "metadata": meta, "spec": spec})


def baseline():
    return [pa(ns) for ns in sorted(cmm.MTLS_NAMESPACES)]


def ef(namespace, rules=None, name="default"):
    if rules is None:
        rules = [
            {"type": "Allow", "to": {"dnsName": "keycloak.apps.example.com"}, "ports": [{"protocol": "TCP", "port": 443}]},
            {"type": "Deny", "to": {"cidrSelector": "0.0.0.0/0"}},
        ]
    return cmm.Rendered("test", namespace, {"kind": "EgressFirewall", "metadata": {"name": name}, "spec": {"egress": rules}})


class PeerAuthenticationRules(unittest.TestCase):
    def failures(self, objects):
        findings = cmm.csa.Findings()
        cmm.check_peer_authentications(objects, findings)
        return findings.failures

    def test_the_three_namespace_defaults_pass(self):
        self.assertEqual(self.failures(baseline()), [])

    def test_a_justified_workload_exception_passes(self):
        objects = baseline() + [pa("zuno-auth", "kc", selector={"app": "keycloak"}, ports={8080: "PERMISSIVE"})]
        self.assertEqual(self.failures(objects), [])

    def test_a_peerauthentication_in_another_namespace_fails(self):
        failures = self.failures(baseline() + [pa("redhat-ods-applications")])
        self.assertTrue(any("redhat-ods-applications/default" in f and "outside" in f for f in failures), failures)

    def test_a_missing_namespace_default_fails(self):
        objects = [o for o in baseline() if o.namespace != "zuno-data"]
        self.assertTrue(any(f.startswith("zuno-data: expected one") for f in self.failures(objects)))

    def test_a_disable_namespace_mode_fails(self):
        objects = [o for o in baseline() if o.namespace != "zuno-ai-run"] + [pa("zuno-ai-run", mode="DISABLE")]
        self.assertTrue(any("'DISABLE'" in f for f in self.failures(objects)))

    def test_an_exception_without_reason_fails(self):
        objects = baseline() + [pa("zuno-auth", "kc", selector={"app": "keycloak"}, ports={8080: "PERMISSIVE"}, reason="")]
        self.assertTrue(any("permissive-reason" in f for f in self.failures(objects)))

    def test_a_disable_port_fails(self):
        objects = baseline() + [pa("zuno-auth", "kc", selector={"app": "keycloak"}, ports={8080: "DISABLE"})]
        self.assertTrue(any("may only be PERMISSIVE" in f for f in self.failures(objects)))

    def test_a_workload_mode_override_fails(self):
        objects = baseline() + [pa("zuno-data", "pg", selector={"app": "pg"}, workload_mode="PERMISSIVE")]
        self.assertTrue(any("inherit the namespace mode" in f for f in self.failures(objects)))

    def test_port_level_on_the_namespace_default_fails(self):
        objects = [o for o in baseline() if o.namespace != "zuno-auth"]
        bad = pa("zuno-auth")
        bad.doc["spec"]["portLevelMtls"] = {8080: {"mode": "PERMISSIVE"}}
        bad.doc["metadata"]["annotations"][cmm.REASON_ANNOTATION] = "router"
        failures = self.failures(objects + [bad])
        self.assertTrue(any("without a selector" in f for f in failures), failures)

    def test_two_workload_policies_with_one_selector_fail(self):
        objects = baseline() + [
            pa("zuno-ai-run", "a", selector={"app": "x"}, ports={8080: "PERMISSIVE"}),
            pa("zuno-ai-run", "b", selector={"app": "x"}, ports={9090: "PERMISSIVE"}),
        ]
        self.assertTrue(any("same selector" in f for f in self.failures(objects)))


class EgressFirewallRules(unittest.TestCase):
    def failures(self, objects):
        findings = cmm.csa.Findings()
        cmm.check_egress_firewalls(objects, findings)
        return findings.failures

    def both(self):
        return [ef(ns) for ns in sorted(cmm.EGRESS_NAMESPACES)]

    def test_both_namespaces_pass(self):
        self.assertEqual(self.failures(self.both()), [])

    def test_a_missing_firewall_fails(self):
        with unittest.mock.patch.object(cmm, "egress_deferred", return_value=""):
            failures = self.failures([ef("zuno-ai-run")])
        self.assertTrue(any(f.startswith("zuno-unifai: no EgressFirewall") for f in failures))

    def test_a_deliberately_deferred_firewall_passes_with_its_reason(self):
        with unittest.mock.patch.object(cmm, "egress_deferred", return_value="pending its rehearsal"):
            self.assertEqual(self.failures([ef("zuno-ai-run")]), [])

    def test_zuno_ai_run_can_never_be_deferred(self):
        self.assertEqual(cmm.egress_deferred("zuno-ai-run"), "")
        self.assertTrue(any(f.startswith("zuno-ai-run: no EgressFirewall") for f in self.failures([ef("zuno-unifai")])))

    def test_no_final_deny_fails(self):
        rules = [{"type": "Allow", "to": {"dnsName": "api.mistral.ai"}}]
        failures = self.failures([ef("zuno-ai-run", rules), ef("zuno-unifai")])
        self.assertTrue(any("does not end with Deny 0.0.0.0/0" in f for f in failures), failures)

    def test_an_allow_all_rule_fails(self):
        rules = [{"type": "Allow", "to": {"cidrSelector": "0.0.0.0/0"}}, {"type": "Deny", "to": {"cidrSelector": "0.0.0.0/0"}}]
        self.assertTrue(any("allows 0.0.0.0/0" in f for f in self.failures([ef("zuno-ai-run"), ef("zuno-unifai", rules)])))

    def test_a_deny_only_firewall_fails(self):
        rules = [{"type": "Deny", "to": {"cidrSelector": "0.0.0.0/0"}}]
        self.assertTrue(any("allows nothing" in f for f in self.failures([ef("zuno-ai-run", rules), ef("zuno-unifai")])))

    def test_a_second_firewall_or_wrong_name_fails(self):
        failures = self.failures(self.both() + [ef("zuno-ai-run", name="extra")])
        self.assertTrue(any("must be named default" in f for f in failures), failures)
        self.assertTrue(any("2 EgressFirewalls" in f for f in failures), failures)


@unittest.skipUnless(shutil.which("helm"), "helm not installed")
class ChartGuards(unittest.TestCase):
    """The namespaces chart refuses an exception without a reason and an empty host list."""

    def render(self, mutate):
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        values = copy.deepcopy(values)
        values["policy"]["enabled"] = True
        values["clusterBaseDomain"] = "apps.example.com"
        mutate(values)
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".yaml") as fh:
            yaml.safe_dump(values, fh)
            fh.flush()
            return subprocess.run(["helm", "template", "t", str(CHART), "-f", fh.name], capture_output=True, text=True)

    @staticmethod
    def entry(values, name):
        return next(e for e in values["platformNamespaces"] if e["name"] == name)

    def test_the_chart_renders(self):
        proc = self.render(lambda v: None)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        kinds = [d.get("kind") for d in yaml.safe_load_all(proc.stdout) if isinstance(d, dict)]
        self.assertIn("EgressFirewall", kinds)

    def test_an_exception_without_reason_does_not_render(self):
        def drop_reason(values):
            self.entry(values, "zuno-auth")["peerAuthentication"]["exceptions"][0].pop("reason")
        proc = self.render(drop_reason)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("reason is required", proc.stderr)

    def test_an_unknown_mode_does_not_render(self):
        def disable(values):
            self.entry(values, "zuno-data")["peerAuthentication"]["mode"] = "DISABLE"
        self.assertNotEqual(self.render(disable).returncode, 0)

    def test_an_empty_host_list_does_not_render(self):
        def empty(values):
            self.entry(values, "zuno-ai-run")["egressFirewall"]["hosts"] = []
        proc = self.render(empty)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("egressFirewall.hosts is empty", proc.stderr)

    def test_salesforce_needs_its_instance_host(self):
        def enable(values):
            self.entry(values, "zuno-ai-run")["egressFirewall"]["salesforce"] = {"enabled": True, "instanceHost": ""}
        proc = self.render(enable)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("instanceHost is required", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
