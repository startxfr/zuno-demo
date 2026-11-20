"""The guard of the image-proof test namespace (ADR-0624 / WP-310): a ValidatingAdmissionPolicy that denies every pod CREATE there
unless it is a dry run, plus a deny-all NetworkPolicy, both rendered only with stressImageProof.guard.enabled.

The policy expression is checked offline by a tiny evaluator of the ONE form it may take, `request.dryRun == true` (no CEL
library is installed in CI); the test fails if the expression changes to anything else, which then needs a real CEL check.

Run from the repository root:
    python3 platform/gitops/tests/test_stress_image_proof_guard.py
Needs helm (skipped otherwise).
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
CHART = REPO / "gitops" / "charts" / "namespaces"
NS = "zuno-stress-admission"
BASE = ["policy.enabled=true", "clusterBaseDomain=apps.test", "stressReader.enabled=true", "stressImageProof.enabled=true"]


def render(*sets: str) -> list:
    args = ["helm", "template", "n", str(CHART)]
    for s in sets:
        args += ["--set", s]
    out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


def evaluate(expression: str, request: dict) -> bool:
    """`request.dryRun == true` and nothing else."""
    if not re.fullmatch(r"request\.dryRun == true", expression):
        raise AssertionError(f"the guard expression is no longer the one this test can evaluate: {expression!r}")
    return request.get("dryRun") is True


def guard_objects(docs: list) -> list:
    return [d for d in docs if d["kind"] in ("ValidatingAdmissionPolicy", "ValidatingAdmissionPolicyBinding")
            or (d["kind"] == "NetworkPolicy" and d["metadata"].get("namespace") == NS)]


@unittest.skipUnless(shutil.which("helm"), "helm not installed")
class Guard(unittest.TestCase):
    def test_off_by_default_and_the_render_is_unchanged_without_it(self):
        self.assertEqual(guard_objects(render(*BASE)), [])
        self.assertEqual(guard_objects(render("policy.enabled=true", "clusterBaseDomain=apps.test", "stressImageProof.guard.enabled=true")), [])

    def test_the_policy_denies_every_create_but_a_dry_run(self):
        docs = guard_objects(render(*BASE, "stressImageProof.guard.enabled=true"))
        self.assertEqual(sorted(d["kind"] for d in docs), ["NetworkPolicy", "ValidatingAdmissionPolicy", "ValidatingAdmissionPolicyBinding"])
        policy = next(d for d in docs if d["kind"] == "ValidatingAdmissionPolicy")["spec"]
        self.assertEqual(policy["failurePolicy"], "Fail")
        self.assertEqual(policy["matchConstraints"]["resourceRules"],
                         [{"apiGroups": [""], "apiVersions": ["v1"], "operations": ["CREATE"], "resources": ["pods"]}])
        (validation,) = policy["validations"]
        self.assertTrue(evaluate(validation["expression"], {"dryRun": True}))
        self.assertFalse(evaluate(validation["expression"], {"dryRun": False}))
        self.assertFalse(evaluate(validation["expression"], {}))

    def test_the_binding_denies_and_covers_only_the_test_namespace(self):
        docs = guard_objects(render(*BASE, "stressImageProof.guard.enabled=true"))
        policy = next(d for d in docs if d["kind"] == "ValidatingAdmissionPolicy")
        binding = next(d for d in docs if d["kind"] == "ValidatingAdmissionPolicyBinding")["spec"]
        self.assertEqual(binding["policyName"], policy["metadata"]["name"])
        self.assertEqual(binding["validationActions"], ["Deny"])
        self.assertEqual(binding["matchResources"]["namespaceSelector"], {"matchLabels": {"kubernetes.io/metadata.name": NS}})

    def test_the_network_policy_denies_all_traffic(self):
        spec = next(d for d in guard_objects(render(*BASE, "stressImageProof.guard.enabled=true")) if d["kind"] == "NetworkPolicy")["spec"]
        self.assertEqual(spec["podSelector"], {})
        self.assertEqual(sorted(spec["policyTypes"]), ["Egress", "Ingress"])
        self.assertNotIn("ingress", spec)
        self.assertNotIn("egress", spec)

    def test_the_project_admits_the_two_kinds_and_the_ansible_switch_defaults_off(self):
        project = (REPO / "ansible/roles/argocd/kustomize/appproject/appproject-platform.yaml").read_text()
        for kind in ("ValidatingAdmissionPolicy", "ValidatingAdmissionPolicyBinding"):
            self.assertIn(f"{{group: admissionregistration.k8s.io, kind: {kind}}}", project)
        self.assertIn("zuno_stress_image_proof_guard_enabled | default(false)", (REPO / "ansible/roles/namespaces/tasks/install_d1.yml").read_text())
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        self.assertIs(values["stressImageProof"]["guard"]["enabled"], False)


if __name__ == "__main__":
    unittest.main()
