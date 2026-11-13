"""Tests for check_recovery (WP-248 incident): every layer of a bad recovery is named, a healthy cluster is silent."""
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import check_recovery as r  # noqa: E402


def cond(t, s):
    return {"conditions": [{"type": t, "status": s}]}


def pod(ns, name, ready="True", waiting=None, init_waiting=None):
    st = {"phase": "Running", **cond("Ready", ready)}
    if waiting:
        st["containerStatuses"] = [{"state": {"waiting": {"reason": waiting}}}]
    if init_waiting:
        st["initContainerStatuses"] = [{"state": {"waiting": {"reason": init_waiting}}}]
    return {"metadata": {"namespace": ns, "name": name}, "status": st}


def healthy(args):
    key = " ".join(args)
    if key == "get nodes":
        return {"items": [{"metadata": {"name": "n1"}, "spec": {}, "status": cond("Ready", "True")}]}
    if key == "get machineconfigpools":
        return {"items": [{"metadata": {"name": "worker"}, "status": {**cond("Updated", "True"), "machineCount": 4,
                                                                         "readyMachineCount": 4}}]}
    if key == "get clusteroperators":
        return {"items": [{"metadata": {"name": "auth"}, "status": {"conditions": [
            {"type": "Degraded", "status": "False"}, {"type": "Available", "status": "True"}]}}]}
    if key == "get pods -A":
        return {"items": [pod("zuno-ai-run", "ai-gateway-1")]}
    if args[:3] == ["get", "pods", "-n"] and args[3] == "zuno-registry":
        return {"items": [pod("zuno-registry", "quay-quay-app-1")]}
    if args[:3] == ["get", "route", "-n"]:
        return {"spec": {"host": "quay.example"}}
    if args[:3] == ["get", "endpoints", "-n"]:
        return {"subsets": [{"addresses": [{"ip": "10.0.0.1"}]}]}
    if args[:3] == ["get", "pods", "-n"] and args[3] == "kuadrant-system":
        return {"items": [pod("kuadrant-system", "authorino-abc")]}
    if args[:2] == ["get", "ingresses.config.openshift.io"]:
        return {"spec": {"domain": "apps.example"}}
    raise AssertionError(key)


class RecoveryTests(unittest.TestCase):
    def test_a_healthy_cluster_has_no_finding(self):
        out = r.run([], lambda url: 401, healthy)
        self.assertEqual({k: v for k, v in out.items() if v}, {})

    def test_every_layer_is_named(self):
        def bad(args):
            key = " ".join(args)
            d = healthy(args)
            if key == "get nodes":
                d["items"][0]["spec"] = {"unschedulable": True}
            if key == "get machineconfigpools":
                d["items"][0]["status"] = {**cond("Updated", "False"), "machineCount": 4, "readyMachineCount": 2}
            if key == "get pods -A":
                d["items"] = [pod("zuno-ai-run", "mcp-gateway-1", init_waiting="CrashLoopBackOff"),
                              pod("openshift-cnv", "virt-platform-autopilot-1", waiting="CrashLoopBackOff")]
            if args[:3] == ["get", "pods", "-n"] and args[3] == "zuno-registry":
                d["items"] = [pod("zuno-registry", "quay-quay-app-1", ready="False")]
            if args[:3] == ["get", "endpoints", "-n"]:
                d = {"subsets": None}
            return d
        out = r.run([], lambda url: 503, bad)
        self.assertIn("cordoned", out["nodes"][0])
        self.assertIn("still updating", out["pools"][0])
        self.assertEqual(out["pods"], ["zuno-ai-run/mcp-gateway-1: CrashLoopBackOff"])
        self.assertIn("not Ready", out["quay"][0])
        self.assertIn("no endpoint", out["kuadrant"][0])
        self.assertIn("failed closed", out["maas"][0])

    def test_only_runs_the_named_checks_and_no_http_skips_the_routes(self):
        out = r.run(["maas", "quay"], None, healthy)
        self.assertEqual(set(out), {"maas", "quay"})
        self.assertEqual(out["maas"], [])


if __name__ == "__main__":
    unittest.main()
