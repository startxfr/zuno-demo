"""The wildcard grants of the zuno-aap-installer ClusterRole may not grow by accident (best-practices audit, lot 2).

gitops/charts/aap-config/templates/clusterrole-installer.yaml gives the AAP installer credential `resources: ["*"]` with the
write verbs on 50 operator API groups (the documented "same trust tier" of the operands its Day 1/2 roles apply or wait on). Narrowing
them needs the audit log of real AAP runs: a resource type taken away by mistake is a 403 in the middle of an install, one per
re-run. So nothing is narrowed here, but the list is FROZEN: adding a group (or a second wildcard rule) fails this test until the
list below is edited on purpose, in the same commit, with the reason in the commit message. Removing a group also fails, so the
file stays the honest inventory.

`operator.openshift.io` (Console, IngressController, DNS, ...) is on the list: the widest grant of it, review it first when narrowing.

Needs helm; skipped otherwise.

Run from the repository root:
    python3 platform/gitops/tests/test_aap_installer_wildcards.py
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
FROZEN = (
    "authorino.kuadrant.io",
    "cert-manager.io",
    "components.platform.opendatahub.io",
    "config.opendatahub.io",
    "dashboard.opendatahub.io",
    "datasciencecluster.opendatahub.io",
    "datasciencepipelinesapplications.opendatahub.io",
    "dscinitialization.opendatahub.io",
    "eventing.keda.sh",
    "extensions.istio.io",
    "extensions.kuadrant.io",
    "features.opendatahub.io",
    "gateway.networking.k8s.io",
    "http.keda.sh",
    "infrastructure.opendatahub.io",
    "jobset.x-k8s.io",
    "k8s.mariadb.com",
    "keda.sh",
    "kuadrant.io",
    "kueue.openshift.io",
    "kueue.x-k8s.io",
    "lightspeed.ansible.com",
    "limitador.kuadrant.io",
    "maas.opendatahub.io",
    "mlflow.kubeflow.org",
    "mlflow.opendatahub.io",
    "modelregistry.opendatahub.io",
    "monitoring.coreos.com",
    "networking.istio.io",
    "nim.opendatahub.io",
    "nvidia.com",
    "ols.openshift.io",
    "opendatahub.io",
    "opentelemetry.io",
    "operator.authorino.kuadrant.io",
    "operator.openshift.io",
    "pipelines.kubeflow.org",
    "policy.sigstore.dev",
    "resource.nvidia.com",
    "rhtas.redhat.com",
    "sailoperator.io",
    "security.istio.io",
    "services.platform.opendatahub.io",
    "serving.kserve.io",
    "telemetry.istio.io",
    "template.openshift.io",
    "tempo.grafana.com",
    "trainer.kubeflow.org",
    "trustyai.opendatahub.io",
    "zuno.zuno.ai",
)


def installer_rules() -> list:
    out = subprocess.run(["helm", "template", "a", str(REPO / "gitops/charts/aap-config"), "--set", "aapConfig.enabled=true"],
                         capture_output=True, text=True, check=True).stdout
    for doc in yaml.safe_load_all(out):
        if doc and doc.get("kind") == "ClusterRole" and doc["metadata"]["name"] == "zuno-aap-installer":
            return doc["rules"]
    raise AssertionError("the ClusterRole zuno-aap-installer is not rendered")


@unittest.skipUnless(shutil.which("helm"), "helm not on PATH")
class Wildcards(unittest.TestCase):
    def test_the_wildcard_groups_are_the_frozen_list(self):
        wild = sorted({g for r in installer_rules() if "*" in (r.get("resources") or []) for g in r.get("apiGroups") or []})
        self.assertEqual(wild, sorted(FROZEN),
                         "the groups granted `resources: [\"*\"]` to zuno-aap-installer changed. Added: "
                         f"{sorted(set(wild) - set(FROZEN))}; removed: {sorted(set(FROZEN) - set(wild))}. Edit FROZEN in this test in "
                         "the same commit and say why in the message.")

    def test_no_wildcard_grant_has_a_wildcard_group_or_verb(self):
        for rule in installer_rules():
            if "*" in (rule.get("resources") or []):
                self.assertNotIn("*", rule["apiGroups"])
                self.assertNotIn("*", rule["verbs"])

    def test_cluster_roles_and_secrets_are_not_wildcarded(self):
        for rule in installer_rules():
            if "*" in (rule.get("resources") or []):
                self.assertFalse({"rbac.authorization.k8s.io", ""} & set(rule["apiGroups"]))


if __name__ == "__main__":
    unittest.main()
