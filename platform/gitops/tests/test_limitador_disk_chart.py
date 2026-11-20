"""Limitador's counters on a PVC (WP-315): the connectivity-link chart asserts only spec.storage on the operator-owned CR.

Run from the repository root:
    python3 platform/gitops/tests/test_limitador_disk_chart.py
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
APP_D1 = REPO / "gitops" / "apps" / "connectivity-link" / "application-d1.yaml"


def limitadors(*sets: str) -> list:
    args = ["helm", "template", "x", str(CHART)]
    for s in sets:
        args += ["--set", s]
    out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    return [d for d in yaml.safe_load_all(out) if d and d.get("kind") == "Limitador"]


@unittest.skipUnless(shutil.which("helm"), "helm not installed")
class LimitadorDiskChart(unittest.TestCase):
    def test_off_by_default_and_without_kuadrant(self):
        self.assertEqual(limitadors(), [])
        self.assertEqual(limitadors("kuadrant.enabled=true"), [])
        self.assertEqual(limitadors("kuadrant.limitadorDisk.enabled=true"), [])

    def test_only_the_storage_is_asserted(self):
        (cr,) = limitadors("kuadrant.enabled=true", "kuadrant.limitadorDisk.enabled=true")
        self.assertEqual(cr["metadata"]["name"], "limitador")
        self.assertEqual(cr["metadata"]["namespace"], "kuadrant-system")
        # spec.limits belongs to the Kuadrant operator: the chart must never declare it.
        self.assertEqual(list(cr["spec"]), ["storage"])
        disk = cr["spec"]["storage"]["disk"]
        # One quantity, not a map: the CRD types requests as int-or-string (refused live 2026-11-20 16:25Z).
        self.assertEqual(disk["persistentVolumeClaim"]["resources"]["requests"], "1Gi")
        self.assertNotIn("storageClassName", disk["persistentVolumeClaim"])

    def test_argo_never_deletes_the_operator_owned_cr(self):
        (cr,) = limitadors("kuadrant.enabled=true", "kuadrant.limitadorDisk.enabled=true")
        options = cr["metadata"]["annotations"]["argocd.argoproj.io/sync-options"]
        self.assertIn("Prune=false", options)
        self.assertIn("Delete=false", options)

    def test_the_storage_class_is_passed_when_set(self):
        (cr,) = limitadors("kuadrant.enabled=true", "kuadrant.limitadorDisk.enabled=true",
                           "kuadrant.limitadorDisk.storageClassName=gp3-csi")
        self.assertEqual(cr["spec"]["storage"]["disk"]["persistentVolumeClaim"]["storageClassName"], "gp3-csi")

    def test_the_d1_application_turns_it_on(self):
        values = yaml.safe_load(yaml.safe_load(APP_D1.read_text())["spec"]["source"]["helm"]["values"])
        self.assertTrue(values["kuadrant"]["limitadorDisk"]["enabled"])


if __name__ == "__main__":
    unittest.main()
