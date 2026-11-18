"""check_app_projects: the AppProject split rules (ADR-0602 clause 5, WP-224,
finding C4).

Each case feeds the rule functions synthetic rendered Applications and small
projects, so no helm is needed; the real repository is covered by running
the check itself in CI. Most cases are negative: each one is a way a chart
change could slide a cluster-wide privilege back into a project.

Run from the repository root:
    python3 platform/gitops/tests/test_check_app_projects.py
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_app_projects as cap  # noqa: E402

SERVER = "https://kubernetes.default.svc"
CLUSTER_SCOPED = {"/Namespace", "rbac.authorization.k8s.io/ClusterRoleBinding", "config.openshift.io/OAuth"}


def projects():
    return {
        cap.PLATFORM: {
            "destinations": [{"server": SERVER, "namespace": "zuno-*"}, {"server": SERVER, "namespace": "openshift-config"}],
            "clusterResourceWhitelist": [{"group": "", "kind": "Namespace"},
                                         {"group": "rbac.authorization.k8s.io", "kind": "ClusterRoleBinding"}],
        },
        cap.APPS: {
            "destinations": [{"server": SERVER, "namespace": "zuno-*"}],
            "clusterResourceWhitelist": [],
            "namespaceResourceBlacklist": [{"group": "operators.coreos.com", "kind": "*"},
                                           {"group": "argoproj.io", "kind": "*"}],
        },
        cap.BOOTSTRAP: {
            "destinations": [{"server": SERVER, "namespace": "openshift-gitops"}],
            "clusterResourceWhitelist": [],
            "namespaceResourceWhitelist": [{"group": "argoproj.io", "kind": "Application"}],
        },
    }


def obj(api, kind, name="x", namespace=None):
    meta = {"name": name}
    if namespace:
        meta["namespace"] = namespace
    return {"apiVersion": api, "kind": kind, "metadata": meta}


def app(name, project, destination, docs, sync_options=None):
    return cap.Rendered(name, "test", project, destination, docs, sync_options or [])


DEPLOYMENT = obj("apps/v1", "Deployment")
CRB = obj("rbac.authorization.k8s.io/v1", "ClusterRoleBinding")
SUBSCRIPTION = obj("operators.coreos.com/v1alpha1", "Subscription", namespace="zuno-ai-run")


class AppProjectRules(unittest.TestCase):
    def failures(self, rendered, projs=None):
        findings = cap.Findings()
        projs = projs if projs is not None else projects()
        cap.check_projects(projs, findings)
        used = cap.check_apps(rendered, projs, CLUSTER_SCOPED, findings)
        cap.check_unused_whitelist(projs, used, findings)
        return findings.failures

    def compliant(self):
        return [
            app("zuno-ns-d0", cap.PLATFORM, "zuno-ai-run", [obj("v1", "Namespace"), CRB]),
            app("zuno-web-d1", cap.APPS, "zuno-ai-run", [DEPLOYMENT]),
        ]

    def test_a_compliant_split_passes(self):
        self.assertEqual(self.failures(self.compliant()), [])

    def test_the_legacy_project_is_refused(self):
        failures = self.failures(self.compliant() + [app("zuno-old-d1", "zuno", "zuno-ai-run", [DEPLOYMENT])])
        self.assertTrue(any("project 'zuno' is not one of" in f for f in failures), failures)

    def test_a_workload_rendering_a_clusterrolebinding_fails(self):
        # The C4 path: a workload chart change granting itself cluster-admin.
        failures = self.failures(self.compliant() + [app("zuno-web2-d1", cap.APPS, "zuno-ai-run", [DEPLOYMENT, CRB])])
        self.assertTrue(any("zuno-apps Application renders cluster-scoped" in f for f in failures), failures)

    def test_a_workload_rendering_a_subscription_fails(self):
        failures = self.failures(self.compliant() + [app("zuno-web2-d1", cap.APPS, "zuno-ai-run", [SUBSCRIPTION])])
        self.assertTrue(any("OLM/ArgoCD kinds belong" in f for f in failures), failures)
        self.assertTrue(any("namespaceResourceBlacklist" in f for f in failures), failures)

    def test_a_workload_rendering_an_application_fails(self):
        argo_app = obj("argoproj.io/v1alpha1", "Application", namespace="zuno-ai-run")
        failures = self.failures(self.compliant() + [app("zuno-web2-d1", cap.APPS, "zuno-ai-run", [argo_app])])
        self.assertTrue(any("OLM/ArgoCD kinds belong" in f for f in failures), failures)

    def test_a_cluster_kind_missing_from_the_whitelist_fails(self):
        oauth = obj("config.openshift.io/v1", "OAuth", "cluster")
        failures = self.failures(self.compliant() + [app("zuno-oauth-d1", cap.PLATFORM, "openshift-config", [oauth])])
        self.assertTrue(any("config.openshift.io/OAuth not in AppProject zuno-platform clusterResourceWhitelist" in f
                            for f in failures), failures)

    def test_a_wildcard_whitelist_fails(self):
        projs = projects()
        projs[cap.PLATFORM]["clusterResourceWhitelist"].append({"group": "*", "kind": "*"})
        failures = self.failures(self.compliant(), projs)
        self.assertTrue(any("uses a wildcard" in f for f in failures), failures)

    def test_an_unused_whitelist_entry_fails(self):
        projs = projects()
        projs[cap.PLATFORM]["clusterResourceWhitelist"].append({"group": "config.openshift.io", "kind": "OAuth"})
        failures = self.failures(self.compliant(), projs)
        self.assertTrue(any("config.openshift.io/OAuth is rendered by no Application" in f for f in failures), failures)

    def test_an_unused_entry_is_only_a_note_when_subcharts_are_not_built(self):
        projs = projects()
        projs[cap.PLATFORM]["clusterResourceWhitelist"].append({"group": "config.openshift.io", "kind": "OAuth"})
        findings = cap.Findings()
        cap.check_projects(projs, findings)
        used = cap.check_apps(self.compliant(), projs, CLUSTER_SCOPED, findings)
        cap.check_unused_whitelist(projs, used, findings, unproven=True)
        self.assertEqual(findings.failures, [])
        self.assertTrue(any("not proven unused" in n and "config.openshift.io/OAuth" in n for n in findings.notes), findings.notes)

    def test_a_live_only_kind_may_stay_unused(self):
        projs = projects()
        projs[cap.PLATFORM]["clusterResourceWhitelist"].append({"group": "project.openshift.io", "kind": "Project"})
        self.assertEqual(self.failures(self.compliant(), projs), [])

    def test_a_cluster_kind_whitelisted_for_apps_fails(self):
        projs = projects()
        projs[cap.APPS]["clusterResourceWhitelist"] = [{"group": "", "kind": "Namespace"}]
        failures = self.failures(self.compliant(), projs)
        self.assertTrue(any("zuno-apps: clusterResourceWhitelist must be empty" in f for f in failures), failures)

    def test_apps_without_the_olm_blacklist_fails(self):
        projs = projects()
        projs[cap.APPS]["namespaceResourceBlacklist"] = [{"group": "argoproj.io", "kind": "*"}]
        failures = self.failures(self.compliant(), projs)
        self.assertTrue(any("must refuse operators.coreos.com/*" in f for f in failures), failures)

    def test_a_destination_outside_the_project_fails(self):
        failures = self.failures(self.compliant() + [app("zuno-web2-d1", cap.APPS, "kube-system", [DEPLOYMENT])])
        self.assertTrue(any("destination namespace 'kube-system'" in f for f in failures), failures)
        self.assertTrue(any("lands in namespace 'kube-system'" in f for f in failures), failures)

    def test_an_object_namespace_outside_the_project_fails(self):
        cm = obj("v1", "ConfigMap", namespace="openshift-config")
        failures = self.failures(self.compliant() + [app("zuno-web2-d1", cap.APPS, "zuno-ai-run", [cm])])
        self.assertTrue(any("lands in namespace 'openshift-config'" in f for f in failures), failures)

    def test_an_openshift_gitops_destination_is_refused(self):
        projs = projects()
        projs[cap.APPS]["destinations"].append({"server": SERVER, "namespace": "openshift-*"})
        failures = self.failures(self.compliant(), projs)
        self.assertTrue(any("admits openshift-gitops" in f for f in failures), failures)

    def test_a_noop_app_targeting_openshift_gitops_fails(self):
        failures = self.failures(self.compliant() + [app("zuno-x-d0", cap.APPS, "openshift-gitops", [])])
        self.assertTrue(any("destination namespace 'openshift-gitops'" in f for f in failures), failures)

    def test_create_namespace_in_apps_fails(self):
        failures = self.failures(self.compliant() + [
            app("zuno-web2-d1", cap.APPS, "zuno-ai-run", [DEPLOYMENT], ["CreateNamespace=true"])])
        self.assertTrue(any("CreateNamespace=true" in f for f in failures), failures)

    def test_bootstrap_allowing_more_than_applications_fails(self):
        projs = projects()
        projs[cap.BOOTSTRAP]["namespaceResourceWhitelist"].append({"group": "", "kind": "Secret"})
        failures = self.failures(self.compliant(), projs)
        self.assertTrue(any("exactly argoproj.io/Application" in f for f in failures), failures)

    def test_a_missing_project_fails(self):
        projs = projects()
        del projs[cap.BOOTSTRAP]
        failures = self.failures(self.compliant(), projs)
        self.assertTrue(any("AppProject zuno-bootstrap is missing" in f for f in failures), failures)

    def test_a_crd_declared_cluster_scope_counts(self):
        crd = {"kind": "CustomResourceDefinition",
               "spec": {"scope": "Cluster", "group": "example.com", "names": {"kind": "Widget"}}}
        self.assertEqual(cap.crd_cluster_kinds([crd]), {"example.com/Widget"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
