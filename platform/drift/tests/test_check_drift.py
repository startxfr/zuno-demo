"""check_drift: the judgement of each drift check (ADR-0608 clause 6, WP-241).

The checks read the cluster with `oc`; these cases feed the pure functions the shapes `oc get -o json` returns.

Run from the repository root:
    python3 platform/drift/tests/test_check_drift.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_drift as d  # noqa: E402


def sub(pkg, ns="openshift-operators"):
    return {"metadata": {"namespace": ns, "name": pkg}, "spec": {"name": pkg}}


def obj(ns, name, labels=None, annotations=None, owners=None):
    md = {"namespace": ns, "name": name, "labels": labels or {}, "annotations": annotations or {}}
    if owners:
        md["ownerReferences"] = owners
    return {"metadata": md}


class Subscriptions(unittest.TestCase):
    def test_declared_and_external_pass(self):
        text = "name: job-set\nchannel: stable-v1.0"
        out = d.undeclared_subscriptions([sub("job-set"), sub("eck")], text, {"eck": {"owner": "x"}})
        self.assertEqual(out, [])

    def test_undeclared_is_reported(self):
        out = d.undeclared_subscriptions([sub("nfs-provisioner-operator", "nfs-provisioner")], "name: job-set", {})
        self.assertEqual(len(out), 1)
        self.assertIn("nfs-provisioner-operator [nfs-provisioner]", out[0])


class Storage(unittest.TestCase):
    def test_missing_class_reported_and_placeholders_ignored(self):
        values = "sharedStorageClass: nfs\nstorageClassName: mycluster-default-storageclass\nstorageClass: gp3-csi\n"
        self.assertEqual(d.missing_storage_classes(values, {"gp3-csi", "nfs"}), [])
        out = d.missing_storage_classes(values, {"gp3-csi"})
        self.assertEqual(len(out), 1)
        self.assertIn("storage class nfs", out[0])


class ByHand(unittest.TestCase):
    def test_owned_objects_pass(self):
        items = [obj("zuno-data", "a", labels={"zuno.io/managed-by": "zuno-ansible"}),
                 obj("zuno-data", "b", annotations={"argocd.argoproj.io/tracking-id": "x"}),
                 obj("zuno-data", "c", owners=[{"kind": "Deployment"}]),
                 obj("openshift-ingress", "d")]
        self.assertEqual(d.unowned(items, "networkpolicies"), [])

    def test_hand_applied_and_unowned_reported(self):
        items = [obj("zuno-auth", "strict", labels={"zuno.io/applied-by-hand": "WP-224"}),
                 obj("zuno-auth", "orphan")]
        out = d.unowned(items, "peerauthentications")
        self.assertEqual(len(out), 2)
        self.assertIn("applied-by-hand by WP-224", out[0])
        self.assertIn("orphan is owned by neither", out[1])


class Images(unittest.TestCase):
    def pod(self, image_id, ns="zuno-ai-run", name="p"):
        return {"metadata": {"namespace": ns, "name": name},
                "status": {"containerStatuses": [{"imageID": image_id}]}}

    def test_unpushed_build_reported_only_for_first_party(self):
        pods = [self.pod("image-registry.openshift-image-registry.svc:5000/zuno-ai-build/ai-gateway@sha256:aaa"),
                self.pod("quay.io/vendor/x@sha256:bbb")]
        commits = {"sha256:aaa": "deadbeef00"}
        out = d.image_findings(pods, lambda dg: commits.get(dg, ""), lambda c: False)
        self.assertEqual(len(out), 1)
        self.assertIn("deadbeef00", out[0])
        self.assertEqual(d.image_findings(pods, lambda dg: commits.get(dg, ""), lambda c: True), [])


class Canaries(unittest.TestCase):
    def ns(self, name, wp):
        return {"metadata": {"name": name, "labels": {"zuno.io/canary": "true", "zuno.io/work-package": wp}}}

    def test_open_wp_canary_passes_closed_wp_canary_is_left_over(self):
        states = {"WP-211": "Not started", "WP-242": "Done (2026-11-07)"}
        out = d.leftover_canaries([self.ns("zuno-canary-wp-211", "WP-211"), self.ns("zuno-canary-wp-242", "WP-242")], states)
        self.assertEqual(len(out), 1)
        self.assertIn("zuno-canary-wp-242", out[0])

    def test_unknown_wp_is_left_over(self):
        self.assertEqual(len(d.leftover_canaries([self.ns("zuno-canary-x", "WP-999")], {})), 1)

    def test_tracker_parses(self):
        self.assertIn("WP-242", d.wp_states())


class External(unittest.TestCase):
    def test_the_repository_file_parses_and_names_an_owner(self):
        ext = d.load_external()
        for pkg, e in ext.items():
            self.assertTrue(e.get("owner") and e.get("reason"), pkg)


if __name__ == "__main__":
    unittest.main()
