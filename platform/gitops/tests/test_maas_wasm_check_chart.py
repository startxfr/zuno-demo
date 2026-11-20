"""The in-cluster MaaS wasm check of the connectivity-link chart (WP-314): switch, script copy, least-privilege RBAC, alert.

Run from the repository root:
    python3 platform/gitops/tests/test_maas_wasm_check_chart.py
Needs helm (skipped otherwise); the chart's dependencies are vendored in charts/.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
CHART = REPO / "gitops" / "charts" / "connectivity-link"
SCRIPT = REPO / "platform" / "models" / "check_maas_wasm.py"
NAME = "maas-wasm-check"


def render(*sets: str) -> list:
    args = ["helm", "template", "x", str(CHART)]
    for s in sets:
        args += ["--set", s]
    out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


def ours(docs: list) -> list:
    return [d for d in docs if str(d["metadata"].get("name", "")).startswith(NAME)]


@unittest.skipUnless(shutil.which("helm"), "helm not installed")
class MaasWasmCheckChart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.default = render()
        cls.on = ours(render("maasWasmCheck.enabled=true"))

    def of(self, kind: str) -> list:
        return [d for d in self.on if d["kind"] == kind]

    def test_off_by_default(self):
        self.assertEqual(ours(self.default), [])

    def test_the_objects_rendered_when_on(self):
        kinds = sorted(d["kind"] for d in self.on)
        self.assertEqual(kinds, ["ConfigMap", "CronJob", "PrometheusRule", "Role", "Role", "Role", "RoleBinding", "RoleBinding",
                                 "RoleBinding", "ServiceAccount"])

    def test_the_shipped_script_is_the_repository_script(self):
        shipped = (CHART / "files" / "check_maas_wasm.py").read_text()
        self.assertEqual(shipped, SCRIPT.read_text(), "files/check_maas_wasm.py must be a copy of platform/models/check_maas_wasm.py")
        self.assertEqual(self.of("ConfigMap")[0]["data"]["check_maas_wasm.py"], shipped)

    def test_rbac_is_read_only_and_scoped(self):
        got = {r["metadata"]["namespace"]: r["rules"] for r in self.of("Role")}
        self.assertEqual(got["openshift-ingress"], [{"apiGroups": ["networking.istio.io"], "resources": ["envoyfilters"], "verbs": ["get", "list"]}])
        self.assertEqual(got["kuadrant-system"], [{"apiGroups": ["limitador.kuadrant.io"], "resources": ["limitadors"], "verbs": ["get"]}])
        operator = got["openshift-operators"]
        self.assertIn({"apiGroups": ["apps"], "resources": ["deployments"], "resourceNames": ["kuadrant-operator-controller-manager"],
                       "verbs": ["get"]}, operator)
        self.assertIn({"apiGroups": [""], "resources": ["pods/log"], "verbs": ["get"]}, operator)
        for rules in got.values():
            for rule in rules:
                self.assertTrue(set(rule["verbs"]) <= {"get", "list"}, rule)
                self.assertNotIn("*", rule["resources"] + rule["apiGroups"] + rule["verbs"])
                self.assertNotIn("secrets", rule["resources"])
        for binding in self.of("RoleBinding"):
            self.assertEqual(binding["subjects"], [{"kind": "ServiceAccount", "name": NAME, "namespace": "kuadrant-system"}])

    def test_the_cronjob(self):
        cron = self.of("CronJob")[0]
        self.assertEqual(cron["spec"]["schedule"], "*/15 * * * *")
        self.assertEqual(cron["spec"]["concurrencyPolicy"], "Forbid")
        job = cron["spec"]["jobTemplate"]["spec"]
        self.assertEqual(job["backoffLimit"], 0)  # a failed run is a failed Job, which the alert reads
        pod = job["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], NAME)
        self.assertEqual(pod["restartPolicy"], "Never")
        container = pod["containers"][0]
        self.assertIn("@sha256:", container["image"])
        self.assertEqual(container["command"][:2], ["python3", "/scripts/check_maas_wasm.py"])
        self.assertEqual(container["command"][container["command"].index("--log-window") + 1], "20m")
        self.assertEqual(container["securityContext"]["capabilities"], {"drop": ["ALL"]})
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])

    def test_the_alert(self):
        rule = self.of("PrometheusRule")[0]["spec"]["groups"][0]["rules"][0]
        self.assertEqual(rule["alert"], "ZunoMaasWasmConfigNotApplied")
        self.assertEqual(rule["labels"]["severity"], "warning")
        for metric in ("kube_job_status_failed", "kube_cronjob_status_last_successful_time", "absent("):
            self.assertIn(metric, rule["expr"])
        self.assertIn("2700", rule["expr"])
        self.assertEqual(rule["expr"].count("("), rule["expr"].count(")"))


if __name__ == "__main__":
    unittest.main()
