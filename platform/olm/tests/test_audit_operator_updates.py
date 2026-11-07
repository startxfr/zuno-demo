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



class KnownGoodGate(unittest.TestCase):
    """ADR-0607 clauses 1 and 8 (WP-240)."""

    def rows(self, *subs):
        doc = {"subscriptions": list(subs), "packagemanifests": [
            pm("rhods-operator", {"beta": "rhods-operator.3.6.0-ea.2"}),
            pm("grafana-operator", {"v5": "grafana-operator.v5.26.0"}, source="community-operators"),
            pm("unifai-operator", {"alpha": "unifai-operator.v0.1.64"}, source="unifai-operator-catalog")]}
        return a.audit(doc)

    def known(self, *entries):
        return {"operators": [{"package": p, "namespace": n, "version": v} for p, n, v in entries]}

    def test_classes(self):
        self.assertEqual(a.support_class("redhat-operators", "beta", "3.6.0-ea.2"), "early-access")
        self.assertEqual(a.support_class("unifai-operator-catalog", "alpha", "0.1.64"), "alpha")
        self.assertEqual(a.support_class("claw-operator-catalog", "staging", "0.0.227-commit-f5aa592"), "staging")
        self.assertEqual(a.support_class("community-operators", "v5", "5.25.0"), "community")
        self.assertEqual(a.support_class("redhat-operators", "stable", "0.22.0-5"), "ga")

    def test_matching_set_passes(self):
        rows = self.rows(sub("rhods-operator", "beta", "rhods-operator.3.6.0-ea.2", ns="redhat-ods-operator"))
        self.assertEqual(a.compare_known_good(rows, self.known(("rhods-operator", "redhat-ods-operator", "3.6.0-ea.2"))), [])

    def test_pre_ga_drift_fails(self):
        rows = self.rows(sub("unifai-operator", "alpha", "unifai-operator.v0.1.64", source="unifai-operator-catalog"))
        out = a.compare_known_good(rows, self.known(("unifai-operator", "openshift-operators", "0.1.63")))
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("FAIL unifai-operator"))

    def test_community_drift_is_info(self):
        rows = self.rows(sub("grafana-operator", "v5", "grafana-operator.v5.26.0", source="community-operators"))
        out = a.compare_known_good(rows, self.known(("grafana-operator", "openshift-operators", "5.25.0")))
        self.assertTrue(out[0].startswith("INFO grafana-operator"))

    def test_unrecorded_and_missing_fail(self):
        rows = self.rows(sub("rhods-operator", "beta", "rhods-operator.3.6.0-ea.2", ns="redhat-ods-operator"))
        out = a.compare_known_good(rows, self.known(("eck", "openshift-operators", "3.5.0")))
        self.assertTrue(any("not in the known-good set" in f for f in out))
        self.assertTrue(any("eck" in f and "not installed" in f for f in out))

    def test_against_exit_code_and_class_in_file(self):
        doc = {"subscriptions": [sub("unifai-operator", "alpha", "unifai-operator.v0.1.64", source="unifai-operator-catalog")],
               "packagemanifests": [pm("unifai-operator", {"alpha": "unifai-operator.v0.1.64"}, source="unifai-operator-catalog")]}
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write('operators:\n  - package: unifai-operator\n    namespace: openshift-operators\n    version: "0.1.63"\n')
        rc, out = Main.run_main(self, doc, "--against", fh.name)
        self.assertEqual(rc, a.EXIT_KNOWN_GOOD_DRIFT)
        rc, out = Main.run_main(self, doc, "--format", "known-good")
        self.assertIn("class: alpha", out)

if __name__ == "__main__":
    unittest.main()
