"""Argo CD Applications are judged alive, not from a stale status (ADR-0616 clause 9; demo333 incident of 2026-11-15:
rehearsals passed for 14 minutes after the Argo CD instance had been deleted).

Run from the repository root:
    python3 platform/demo/tests/test_argo_health.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import argo_health as a  # noqa: E402

NOW = "2026-11-15T01:50:00Z"


def app(name, sync="Synced", health="Healthy", reconciled="2026-11-15T01:48:00Z"):
    status = {"sync": {"status": sync}, "health": {"status": health}}
    if reconciled:
        status["reconciledAt"] = reconciled
    return {"metadata": {"name": name}, "status": status}


def controller(ready=1, replicas=1):
    return {"metadata": {"name": "openshift-gitops-application-controller"}, "spec": {"replicas": replicas},
            "status": {"readyReplicas": ready}}


def judge(**kw):
    data = {"wanted": ["zuno-a"], "applications": [app("zuno-a")], "statefulsets": [controller()], "argocds": [],
            "now": NOW, "demo_id": "x", "layer": "status"}
    data.update(kw)
    return {r["id"]: r for r in a.judge(data)}


class Alive(unittest.TestCase):
    def test_controller_ready_and_fresh_status_pass(self):
        rows = judge()
        self.assertTrue(rows["argo/application-controller"]["passed"])
        self.assertTrue(rows["argo/zuno-a"]["passed"])
        self.assertEqual(rows["argo/zuno-a"]["detail"], "Synced/Healthy, reconciled 2 min ago")

    def test_argocd_cr_counts_when_no_statefulset_is_found(self):
        self.assertTrue(judge(statefulsets=[], argocds=[{"metadata": {"name": "openshift-gitops"},
                                                           "status": {"phase": "Available"}}])["argo/zuno-a"]["passed"])
        self.assertTrue(judge(statefulsets=[], argocds=[{"metadata": {"name": "g"}, "status": {
            "applicationController": "Running", "phase": "Pending"}}])["argo/zuno-a"]["passed"])

    def test_expectations(self):
        rows = judge(wanted=[{"name": "zuno-a", "sync": "any"}, "zuno-b", "zuno-c"],
                     applications=[app("zuno-a", sync="OutOfSync"), app("zuno-b", health="Degraded")])
        self.assertTrue(rows["argo/zuno-a"]["passed"])
        self.assertFalse(rows["argo/zuno-b"]["passed"])
        self.assertEqual(rows["argo/zuno-c"]["detail"], "absent/absent")


class NotAlive(unittest.TestCase):
    def test_instance_deleted_fails_every_application(self):
        rows = judge(statefulsets=[], argocds=[])
        self.assertFalse(rows["argo/application-controller"]["passed"])
        self.assertIn("Argo CD is not running: the Applications' status is stale",
                      rows["argo/application-controller"]["detail"])
        self.assertFalse(rows["argo/zuno-a"]["passed"])
        self.assertEqual(rows["argo/zuno-a"]["detail"],
                         "Synced/Healthy (stored), Argo CD is not running: the Applications' status is stale")

    def test_controller_not_ready(self):
        self.assertFalse(judge(statefulsets=[controller(ready=0)])["argo/zuno-a"]["passed"])
        self.assertFalse(judge(statefulsets=[controller(ready=0, replicas=0)])["argo/zuno-a"]["passed"])
        self.assertFalse(judge(statefulsets=[], argocds=[{"metadata": {"name": "g"}, "status": {"phase": "Failed"}}])
                         ["argo/zuno-a"]["passed"])

    def test_stale_reconciled_at(self):
        row = judge(applications=[app("zuno-a", reconciled="2026-11-15T01:00:00Z")])["argo/zuno-a"]
        self.assertFalse(row["passed"])
        self.assertEqual(row["detail"], "Synced/Healthy, reconciled 50 min ago (stale: over 30 min)")
        self.assertTrue(judge(applications=[app("zuno-a", reconciled="2026-11-15T01:00:00Z")], max_age=3600)
                        ["argo/zuno-a"]["passed"])
        self.assertTrue(judge(applications=[app("zuno-a", reconciled="2026-11-15T01:20:00Z")])["argo/zuno-a"]["passed"])

    def test_never_reconciled(self):
        row = judge(applications=[app("zuno-a", reconciled=None)])["argo/zuno-a"]
        self.assertFalse(row["passed"])
        self.assertIn("never reconciled", row["detail"])


class Cli(unittest.TestCase):
    def test_stdin_to_rows(self):
        data = {"wanted": ["zuno-a"], "applications": [app("zuno-a")], "statefulsets": [controller()], "now": NOW,
                "max_age": "1800", "demo_id": "guardrails", "layer": "status"}
        done = subprocess.run([sys.executable, str(HERE.parent / "argo_health.py")], input=json.dumps(data),
                              stdout=subprocess.PIPE, universal_newlines=True, check=True)
        rows = json.loads(done.stdout)
        self.assertEqual([r["id"] for r in rows], ["argo/application-controller", "argo/zuno-a"])
        self.assertEqual(rows[1]["agent"], "guardrails")
        self.assertTrue(all(r["passed"] for r in rows))


if __name__ == "__main__":
    unittest.main()
