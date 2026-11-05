"""platform/olm/audit_operator_updates.py. Run from the repository root:
    python3 platform/olm/tests/test_audit_operator_updates.py
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import audit_operator_updates as a  # noqa: E402


def sub(pkg, channel, installed, ns="openshift-operators", source="redhat-operators", approval="Automatic"):
    return {"metadata": {"namespace": ns, "name": pkg},
            "spec": {"name": pkg, "source": source, "channel": channel, "installPlanApproval": approval},
            "status": {"installedCSV": installed, "state": "AtLatestKnown"}}


def pm(pkg, channels, source="redhat-operators"):
    return {"metadata": {"name": pkg}, "status": {"catalogSource": source,
            "channels": [{"name": n, "currentCSV": c} for n, c in channels.items()]}}


def csv_requiring(name, ns, required):
    props = [{"type": "olm.package.required", "value": {"packageName": p, "versionRange": r}} for p, r in required]
    return {"metadata": {"name": name, "namespace": ns,
                         "annotations": {"operatorframework.io/properties": json.dumps({"properties": props})}}}


def row(rows, pkg):
    return next(r for r in rows if r["package"] == pkg)


class Versions(unittest.TestCase):
    def test_version_of(self):
        self.assertEqual(a.version_of("rhods-operator.3.5.2"), "3.5.2")
        self.assertEqual(a.version_of("aap-operator.v2.7.0-0.1793214862"), "2.7.0-0.1793214862")
        self.assertEqual(a.version_of("rhods-operator.3.6.0-ea.2"), "3.6.0-ea.2")
        self.assertEqual(a.version_of("nfd.4.22.0-202610271454"), "4.22.0-202610271454")
        self.assertIsNone(a.version_of(None))

    def test_prerelease_sorts_before_release_and_build_after(self):
        k = a.version_key
        self.assertLess(k("3.6.0-ea.2"), k("3.6.0"))
        self.assertGreater(k("3.6.0-ea.2"), k("3.5.2"))
        self.assertGreater(k("26.6.7-opr.3"), k("26.6.7"))
        self.assertGreater(k("1.10.0"), k("1.9.4"))
        self.assertGreater(k("26.6.7-opr.3"), k("26.6.7-opr.1"))


class Audit(unittest.TestCase):
    def doc(self, **over):
        doc = {"subscriptions": [], "packagemanifests": [], "installplans": [], "csvs": []}
        doc.update(over)
        return doc

    def test_at_head_with_no_newer_channel_is_ok(self):
        rows = a.audit(self.doc(subscriptions=[sub("tempo-product", "stable", "tempo-operator.v0.22.0-5")],
                                packagemanifests=[pm("tempo-product", {"stable": "tempo-operator.v0.22.0-5"})]))
        self.assertEqual(rows[0]["findings"], [])

    def test_pending_installplan_named(self):
        doc = self.doc(
            subscriptions=[sub("rhods-operator", "stable-3.5", "rhods-operator.3.5.0", ns="redhat-ods-operator", approval="Manual")],
            packagemanifests=[pm("rhods-operator", {"stable-3.5": "rhods-operator.3.5.2", "eus-3.5": "rhods-operator.3.5.2",
                                                    "beta": "rhods-operator.3.6.0-ea.2", "stable": "rhods-operator.2.25.8"})],
            installplans=[{"metadata": {"namespace": "redhat-ods-operator", "name": "install-q6xqx"},
                           "spec": {"approved": False, "clusterServiceVersionNames": ["rhods-operator.3.5.1"]},
                           "status": {"phase": "RequiresApproval"}}])
        r = a.audit(doc)[0]
        self.assertEqual(r["channel_head"], "3.5.2")
        self.assertIn("3.5.0 -> 3.5.2 in channel stable-3.5 (pending InstallPlan)", r["findings"])
        self.assertEqual(r["pending_installplans"], ["install-q6xqx:rhods-operator.3.5.1"])
        # older channels (2.25.8) and channels sharing the current head (eus-3.5) are not "newer"
        self.assertEqual(r["newer_channels"], [{"channel": "beta", "head": "3.6.0-ea.2", "prerelease": True}])

    def test_dependency_pinned_by_another_csv(self):
        doc = self.doc(
            subscriptions=[sub("rhcl-operator", "stable", "rhcl-operator.v1.4.3"),
                           sub("authorino-operator", "stable", "authorino-operator.v1.4.3")],
            packagemanifests=[pm("rhcl-operator", {"stable": "rhcl-operator.v1.4.3", "stable-1.4": "rhcl-operator.v1.4.4",
                                                   "stable-1.5": "rhcl-operator.v1.5.0"}),
                              pm("authorino-operator", {"stable": "authorino-operator.v1.4.4"})],
            csvs=[csv_requiring("rhcl-operator.v1.4.3", "openshift-operators", [("authorino-operator", "1.4.3")])])
        rows = a.audit(doc)
        rhcl, auth = row(rows, "rhcl-operator"), row(rows, "authorino-operator")
        self.assertEqual([c["head"] for c in rhcl["newer_channels"]], ["1.5.0", "1.4.4"])
        self.assertIn("newer channel stable-1.5 -> 1.5.0", rhcl["findings"])
        self.assertIn("1.4.3 -> 1.4.4 in channel stable (pinned by rhcl-operator.v1.4.3 requires 1.4.3)", auth["findings"])

    def test_homonym_in_another_catalog_is_not_used(self):
        doc = self.doc(subscriptions=[sub("limitador-operator", "stable", "limitador-operator.v1.4.2")],
                       packagemanifests=[pm("limitador-operator", {"stable": "limitador-operator.v0.11.0"},
                                            source="community-operators")])
        r = a.audit(doc)[0]
        self.assertIsNone(r["channel_head"])
        self.assertIn("not served by catalog redhat-operators", r["findings"][0])

    def test_missing_channel_reported(self):
        doc = self.doc(subscriptions=[sub("kueue-operator", "stable-v1.3", "kueue-operator.v1.3.2")],
                       packagemanifests=[pm("kueue-operator", {"stable-v1.5": "kueue-operator.v1.5.0"})])
        r = a.audit(doc)[0]
        self.assertTrue(any("channel stable-v1.3 is not published" in f for f in r["findings"]))
        self.assertEqual(r["newer_channels"][0]["head"], "1.5.0")


class Main(unittest.TestCase):
    def run_main(self, doc, *argv):
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(doc) if not isinstance(doc, str) else doc)), \
                mock.patch.object(sys, "stdout", out):
            rc = a.main(list(argv))
        return rc, out.getvalue()

    def test_exit_codes(self):
        ok = {"subscriptions": [sub("x", "stable", "x.v1.0.0")], "packagemanifests": [pm("x", {"stable": "x.v1.0.0"})]}
        self.assertEqual(self.run_main(ok)[0], 0)
        upd = {"subscriptions": [sub("x", "stable", "x.v1.0.0")], "packagemanifests": [pm("x", {"stable": "x.v1.0.1"})]}
        self.assertEqual(self.run_main(upd)[0], 1)
        self.assertEqual(self.run_main("not json")[0], 2)

    def test_known_good_format(self):
        ok = {"subscriptions": [sub("x", "stable", "x.v1.0.0")], "packagemanifests": [pm("x", {"stable": "x.v1.0.0"})]}
        rc, out = self.run_main(ok, "--format", "known-good", "--cluster", "demo333")
        self.assertIn("cluster: demo333", out)
        self.assertIn('version: "1.0.0"', out)


if __name__ == "__main__":
    unittest.main()
