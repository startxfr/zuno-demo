"""The state drivers and the read-only role generated for them (WP-310, ADR-0624), offline.

Run from the repository root:
    python3 evaluations/tests/test_stress_state.py
"""
from __future__ import annotations

import asyncio
import datetime
import json
import pathlib
import shutil
import subprocess
import sys
import unittest

import httpx
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
STRESS_DIR = REPO / "evaluations" / "stress"
sys.path.insert(0, str(REPO / "platform" / "testing"))
sys.path.insert(0, str(REPO / "platform" / "demo"))
sys.path.insert(0, str(REPO / "evaluations"))

import stress_runner as sr  # noqa: E402
import stress_state as ss  # noqa: E402

sr.load_drivers(STRESS_DIR)

import driver_state as ds  # noqa: E402

EXTRACTED = ss.extract()
RULES_FILE = REPO / "gitops/charts/namespaces/files/stress-reader-rules.yaml"


def covered(assertion: dict, rules: list) -> bool:
    """True when some rule lets the reader do what evaluating `assertion` asks of the API."""
    def grants(group, resource, verb, name=None):
        for r in rules:
            if group in r["apiGroups"] and resource in r["resources"] and verb in r["verbs"]:
                if "resourceNames" not in r or (name is not None and name in r["resourceNames"]):
                    return True
        return False

    if assertion["type"] == "cr":
        group, _ = ss.split_api_version(assertion["api_version"])
        if "name_prefix" in assertion:
            return grants(group, ss.plural(assertion["kind"]), "list")
        return grants(group, ss.plural(assertion["kind"]), "get", assertion["name"])
    if assertion["type"] == "workload":
        return grants("" if assertion["kind"] == "Pod" else "apps", ss.plural(assertion["kind"]), "get", assertion["name"])
    ok = grants("apps", "statefulsets", "get", assertion["controller"])
    return ok and all(grants("argoproj.io", "applications", "get", app["name"]) for app in assertion["apps"])


class Extraction(unittest.TestCase):
    def test_plural_follows_the_api_servers_naming(self):
        for kind, expected in (("Deployment", "deployments"), ("Policy", "policies"), ("AuthPolicy", "authpolicies"),
                               ("TokenRateLimitPolicy", "tokenratelimitpolicies"), ("QuayRegistry", "quayregistries"),
                               ("Gateway", "gateways"), ("OLSConfig", "olsconfigs"), ("IstioCNI", "istiocnis"),
                               ("ImageDigestMirrorSet", "imagedigestmirrorsets"), ("MaaSAuthPolicy", "maasauthpolicies"),
                               ("Ingress", "ingresses"), ("Pod", "pods"),
                               ("NemoGuardrails", "nemoguardrails")):  # the CRD names its own plural
            self.assertEqual(ss.plural(kind), expected, kind)

    def test_split_api_version(self):
        self.assertEqual(ss.split_api_version("v1"), ("", "v1"))
        self.assertEqual(ss.split_api_version("cert-manager.io/v1"), ("cert-manager.io", "v1"))

    def test_the_demos_give_assertions_of_the_three_kinds_and_nothing_is_dropped(self):
        demos = EXTRACTED["demos"]
        self.assertGreaterEqual(len(demos), 30)
        self.assertEqual(EXTRACTED["dropped"], 0, "an entry with a Jinja expression cannot be evaluated by a Job: write it plainly")
        kinds = {a["type"] for assertions in demos.values() for a in assertions}
        self.assertEqual(kinds, {"cr", "workload", "argo"})
        self.assertNotIn("world-model-xx", demos)
        self.assertIn("vault-pki", demos)

    def test_extract_reads_the_modes_and_defaults_of_a_demo(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            demo = pathlib.Path(tmp, "d1")
            demo.mkdir()
            (demo / "check.yml").write_text(yaml.safe_dump([
                {"ansible.builtin.include_tasks": "{{ demo_lib }}/cr_ready.yml", "vars": {"cr_ready": [
                    {"api_version": "v1", "kind": "ConfigMap", "name": "c", "namespace": "n", "exists": True},
                    {"api_version": "operators.coreos.com/v1alpha1", "kind": "ClusterServiceVersion", "name_prefix": "x.v", "namespace": "n", "phase": "Succeeded"},
                    {"api_version": "v1", "kind": "ConfigMap", "name": "{{ templated }}", "namespace": "n"}]}},
                {"ansible.builtin.include_tasks": "{{ demo_lib }}/argo_apps.yml", "vars": {"argo_apps": ["a", {"name": "b", "sync": "any"}]}},
                {"ansible.builtin.include_tasks": "{{ demo_lib }}/workloads.yml", "vars": {"workloads": [{"name": "w", "namespace": "n"}, {"name": "p", "namespace": "n", "kind": "Pod"}]}},
                {"ansible.builtin.include_tasks": "{{ demo_lib }}/render.yml"}]))
            (demo / "status.yml").write_text((demo / "check.yml").read_text())  # the same lists twice: counted once
            out = ss.extract(pathlib.Path(tmp))
        a = out["demos"]["d1"]
        self.assertEqual(out["dropped"], 2)  # the templated entry, once per file
        self.assertEqual([x["type"] for x in a], ["cr", "cr", "argo", "workload", "workload"])
        self.assertEqual(a[0], {"type": "cr", "api_version": "v1", "kind": "ConfigMap", "namespace": "n", "name": "c", "exists": True})
        self.assertEqual(a[2], {"type": "argo", "namespace": "openshift-gitops", "controller": "openshift-gitops-application-controller",
                                "max_age": 1800, "apps": [{"name": "a"}, {"name": "b", "sync": "any"}]})
        self.assertEqual(a[4]["kind"], "Pod")


class Role(unittest.TestCase):
    def test_every_assertion_of_every_demo_is_covered_by_the_generated_rules(self):
        rules = ss.rbac_rules(EXTRACTED)
        missing = [(demo, a.get("kind") or a["type"], a.get("name") or a.get("name_prefix"))
                   for demo, assertions in EXTRACTED["demos"].items() for a in assertions if not covered(a, rules)]
        self.assertEqual(missing, [], "a demo check names something the stress reader role does not cover")

    def test_the_role_is_get_only_by_name_without_wildcards_secrets_or_writes(self):
        rules = ss.rbac_rules(EXTRACTED)
        verbs = {v for r in rules for v in r["verbs"]}
        self.assertEqual(verbs, {"get", "list"})
        for r in rules:
            self.assertNotIn("*", r["apiGroups"] + r["resources"] + r["verbs"] + r.get("resourceNames", []))
            self.assertNotIn("secrets", r["resources"])
            self.assertTrue("resourceNames" in r or r["verbs"] == ["get", "list"])  # a get without names would read the kind whole
        lists = [r for r in rules if "list" in r["verbs"]]
        self.assertTrue(all("resourceNames" not in r for r in lists))
        self.assertEqual([r["resources"] for r in lists], [["clusterserviceversions"]])  # the one kind read by name prefix

    def test_the_committed_file_is_what_the_demos_ask_for(self):
        self.assertEqual(RULES_FILE.read_text(), ss.render_rules(EXTRACTED),
                         "run: python3 platform/testing/stress_state.py rbac --write gitops/charts/namespaces/files/stress-reader-rules.yaml")
        self.assertEqual(ss.main(["rbac", "--check", str(RULES_FILE)]), 0)

    def test_a_stale_file_fails_the_check(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".yaml") as fh:
            fh.write("rules: []\n")
            fh.flush()
            self.assertEqual(ss.main(["rbac", "--check", fh.name]), 1)

    def test_a_new_kind_in_a_demo_changes_the_rules(self):
        extra = {"demos": {"x": [{"type": "cr", "api_version": "example.io/v1", "kind": "Thing", "namespace": "n", "name": "t"}]}, "dropped": 0}
        self.assertEqual(ss.rbac_rules(extra), [{"apiGroups": ["example.io"], "resources": ["things"], "resourceNames": ["t"], "verbs": ["get"]}])

    @unittest.skipUnless(shutil.which("helm"), "helm not on PATH")
    def test_the_namespaces_chart_renders_the_role_only_when_switched_on(self):
        chart = str(REPO / "gitops/charts/namespaces")
        base = ["helm", "template", "n", chart, "--set", "policy.enabled=true", "--set", "clusterBaseDomain=apps.test"]
        off = subprocess.run(base, capture_output=True, text=True, check=True).stdout
        self.assertNotIn("zuno-stress-reader", off)
        on = subprocess.run(base + ["--set", "stressReader.enabled=true", "--set", "stressReader.monitoringView=true"], capture_output=True, text=True, check=True).stdout
        docs = [d for d in yaml.safe_load_all(on) if d and d["metadata"]["name"].startswith("zuno-stress-reader")]
        self.assertEqual(sorted(d["kind"] for d in docs), ["ClusterRole", "ClusterRoleBinding", "ClusterRoleBinding", "ServiceAccount"])
        role = next(d for d in docs if d["kind"] == "ClusterRole")
        self.assertEqual(role["rules"], ss.rbac_rules(EXTRACTED))
        no_view = subprocess.run(base + ["--set", "stressReader.enabled=true"], capture_output=True, text=True, check=True).stdout
        self.assertNotIn("monitoring-view", no_view)


class Judging(unittest.TestCase):
    def test_condition_is_the_default_and_expect_is_a_string(self):
        obj = {"status": {"conditions": [{"type": "Ready", "status": "True"}, {"type": "Other", "status": "False"}]}}
        self.assertEqual(ds.judge_cr({"name": "x"}, [obj]), (True, "Ready=True"))
        self.assertEqual(ds.judge_cr({"name": "x", "condition": "Other", "expect": "False"}, [obj]), (True, "Other=False"))
        self.assertEqual(ds.judge_cr({"name": "x", "condition": "Absent"}, [obj]), (False, "Absent=absent"))
        self.assertEqual(ds.judge_cr({"name": "x"}, []), (False, "not found"))

    def test_phase_state_exists_and_parents(self):
        self.assertEqual(ds.judge_cr({"name": "x", "phase": "Ready"}, [{"status": {"phase": "Ready"}}]), (True, "phase Ready"))
        self.assertEqual(ds.judge_cr({"name": "x", "phase": "Ready"}, [{"status": {"phase": "Pending"}}]), (False, "phase Pending"))
        self.assertEqual(ds.judge_cr({"name": "x", "state": "Healthy"}, [{"status": {"state": "Healthy"}}]), (True, "state Healthy"))
        self.assertEqual(ds.judge_cr({"name": "x", "exists": True}, [{}]), (True, "exists"))
        route = {"status": {"parents": [{"conditions": [{"type": "Accepted", "status": "True"}]}, {"conditions": []}]}}
        self.assertEqual(ds.judge_cr({"name": "x", "parents": "Accepted"}, [route]), (True, "Accepted True,absent"))
        bad = {"status": {"parents": [{"conditions": [{"type": "Accepted", "status": "False"}]}]}}
        self.assertFalse(ds.judge_cr({"name": "x", "parents": "Accepted"}, [bad])[0])
        self.assertFalse(ds.judge_cr({"name": "x", "parents": "Accepted"}, [{"status": {}}])[0])

    def test_a_name_prefix_prefers_the_object_in_the_expected_phase_and_names_it(self):
        old = {"metadata": {"name": "op.v1"}, "status": {"phase": "Replacing"}}
        new = {"metadata": {"name": "op.v2"}, "status": {"phase": "Succeeded"}}
        passed, detail = ds.judge_cr({"name_prefix": "op.v", "phase": "Succeeded"}, [old, new])
        self.assertTrue(passed)
        self.assertEqual(detail, "op.v2: phase Succeeded")

    def test_workloads(self):
        self.assertEqual(ds.judge_workload({"kind": "Deployment"}, {"spec": {"replicas": 2}, "status": {"readyReplicas": 2}}), (True, "2/2 ready"))
        self.assertEqual(ds.judge_workload({"kind": "Deployment"}, {"spec": {"replicas": 2}, "status": {"readyReplicas": 1}}), (False, "1/2 ready"))
        self.assertEqual(ds.judge_workload({"kind": "StatefulSet"}, {"spec": {}, "status": {"readyReplicas": 1}}), (True, "1/1 ready"))
        self.assertFalse(ds.judge_workload({"kind": "Deployment"}, {"spec": {"replicas": 0}, "status": {}})[0])  # scaled to zero is not ready
        self.assertEqual(ds.judge_workload({"kind": "Pod"}, {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}), (True, "Ready=True"))
        self.assertEqual(ds.judge_workload({"kind": "Pod"}, {}), (False, "not found"))


def fake_api(objects: dict, denied=()):
    """A mock API server: `objects` maps a path to a body; a path in `denied` answers 403; anything else 404."""
    resources = {
        "/api/v1": [{"name": "pods", "kind": "Pod", "namespaced": True}, {"name": "configmaps", "kind": "ConfigMap", "namespaced": True}],
        "/apis/apps/v1": [{"name": "deployments", "kind": "Deployment", "namespaced": True}, {"name": "statefulsets", "kind": "StatefulSet", "namespaced": True}],
        "/apis/cert-manager.io/v1": [{"name": "clusterissuers", "kind": "ClusterIssuer", "namespaced": False}, {"name": "certificates", "kind": "Certificate", "namespaced": True}],
        "/apis/argoproj.io/v1alpha1": [{"name": "applications", "kind": "Application", "namespaced": True}],
        "/apis/batch/v1": [{"name": "jobs", "kind": "Job", "namespaced": True}],
        "/apis/kagent.dev/v1alpha2": [{"name": "agents", "kind": "Agent", "namespaced": True}],
    }
    seen = []

    def handler(request):
        path = request.url.path
        seen.append(path)
        if path in resources:
            return httpx.Response(200, json={"resources": resources[path]})
        if path in denied:
            return httpx.Response(403, json={"message": "forbidden"})
        if path in objects:
            return httpx.Response(200, json=objects[path])
        return httpx.Response(404, json={})

    return handler, seen


def kube(objects, denied=()):
    handler, seen = fake_api(objects, denied)
    return ds.Kube(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "https://api"), seen


def run(coro):
    return asyncio.run(coro)


READY = {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}


class Evaluation(unittest.TestCase):
    def test_a_kind_is_found_by_discovery_and_read_by_name_at_the_right_path(self):
        k, seen = kube({"/apis/cert-manager.io/v1/clusterissuers/vault-issuer": READY,
                        "/apis/cert-manager.io/v1/namespaces/zuno-auth/certificates/kc": READY})
        rows = run(ds.evaluate(k, "d-state", [
            {"type": "cr", "api_version": "cert-manager.io/v1", "kind": "ClusterIssuer", "name": "vault-issuer", "namespace": ""},
            {"type": "cr", "api_version": "cert-manager.io/v1", "kind": "Certificate", "name": "kc", "namespace": "zuno-auth"}]))
        self.assertEqual([(r.id, r.passed, r.detail) for r in rows], [
            ("clusterissuer/-/vault-issuer", True, "Ready=True"), ("certificate/zuno-auth/kc", True, "Ready=True")])
        self.assertEqual(seen.count("/apis/cert-manager.io/v1"), 1)  # discovery is cached per group version

    def test_a_missing_object_a_refusal_and_an_unserved_kind_are_distinct_rows(self):
        denied = "/apis/cert-manager.io/v1/namespaces/n/certificates/secret-one"
        k, _ = kube({}, denied=(denied,))
        rows = run(ds.evaluate(k, "d-state", [
            {"type": "cr", "api_version": "cert-manager.io/v1", "kind": "Certificate", "name": "absent", "namespace": "n"},
            {"type": "cr", "api_version": "cert-manager.io/v1", "kind": "Certificate", "name": "secret-one", "namespace": "n"},
            {"type": "cr", "api_version": "cert-manager.io/v1", "kind": "Nope", "name": "x", "namespace": "n"}]))
        self.assertEqual(rows[0].detail, "status=404 not found")
        self.assertEqual(sr.row_status(rows[1]), 403)
        self.assertIn("zuno_stress_reader_enabled", rows[1].detail)
        self.assertIn("certificates secret-one", rows[1].detail)
        self.assertEqual(sr.row_status(rows[2]), 404)
        self.assertFalse(any(r.passed for r in rows))

    def test_a_gone_job_and_a_later_phase_object_are_skipped_not_failed(self):
        k, _ = kube({"/apis/batch/v1/namespaces/n/jobs/failed-one": {"status": {"conditions": [{"type": "Failed", "status": "True"}]}}})
        job = {"type": "cr", "api_version": "batch/v1", "kind": "Job", "namespace": "n", "condition": "Complete"}
        agent = {"type": "cr", "api_version": "kagent.dev/v1alpha2", "kind": "Agent", "name": "zuno-diagnose-praxis", "namespace": "zuno-kagent"}
        rows = run(ds.evaluate(k, "multi-gateway-state", [dict(job, name="gone-one"), dict(job, name="failed-one"), agent]))
        self.assertEqual([r.passed for r in rows[:1]], [True])
        self.assertIn("skipped", rows[0].detail)
        self.assertFalse(rows[1].passed)  # an existing Job that did not complete still fails
        self.assertTrue(rows[2].passed)
        self.assertIn("Phase 58", rows[2].detail)
        other = run(ds.evaluate(k, "other-state", [agent]))
        self.assertFalse(other[0].passed)  # the same object missing in another demo is a real 404

    def test_workloads_are_read_by_name_in_their_namespace(self):
        k, _ = kube({"/apis/apps/v1/namespaces/zuno-ai-run/deployments/ai-gateway": {"spec": {"replicas": 2}, "status": {"readyReplicas": 2}},
                     "/api/v1/namespaces/zuno-monitoring/pods/tempo-tempo-0": READY})
        rows = run(ds.evaluate(k, "d-state", [
            {"type": "workload", "kind": "Deployment", "namespace": "zuno-ai-run", "name": "ai-gateway"},
            {"type": "workload", "kind": "Pod", "namespace": "zuno-monitoring", "name": "tempo-tempo-0"},
            {"type": "workload", "kind": "Deployment", "namespace": "zuno-ai-run", "name": "gone"}]))
        self.assertEqual([(r.id, r.passed) for r in rows], [("deployment/zuno-ai-run/ai-gateway", True), ("pod/zuno-monitoring/tempo-tempo-0", True),
                                                             ("deployment/zuno-ai-run/gone", False)])

    def test_a_name_prefix_lists_its_kind_and_filters(self):
        k, seen = kube({"/api/v1/namespaces/n/configmaps": {"items": [{"metadata": {"name": "other"}}, {"metadata": {"name": "op.v2"}, **READY}]}})
        rows = run(ds.evaluate(k, "d-state", [{"type": "cr", "api_version": "v1", "kind": "ConfigMap", "name_prefix": "op.v", "namespace": "n"}]))
        self.assertTrue(rows[0].passed, rows[0].detail)
        self.assertEqual(rows[0].id, "configmap/n/op.v*")
        self.assertIn("/api/v1/namespaces/n/configmaps", seen)

    def argo_unit(self, **kw):
        return {"type": "argo", "namespace": "openshift-gitops", "controller": "openshift-gitops-application-controller", "max_age": 1800,
                "apps": [{"name": "zuno-vault-d1"}], **kw}

    def app(self, sync="Synced", health="Healthy", age=60):
        reconciled = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=age)).isoformat()
        return {"metadata": {"name": "zuno-vault-d1"}, "status": {"sync": {"status": sync}, "health": {"status": health}, "reconciledAt": reconciled}}

    def test_argo_applications_and_the_controller_are_judged_by_the_demos_own_judge(self):
        controller = {"spec": {"replicas": 1}, "status": {"readyReplicas": 1}}
        k, _ = kube({"/apis/argoproj.io/v1alpha1/namespaces/openshift-gitops/applications/zuno-vault-d1": self.app(),
                     "/apis/apps/v1/namespaces/openshift-gitops/statefulsets/openshift-gitops-application-controller": controller})
        rows = run(ds.evaluate(k, "d-state", [self.argo_unit()]))
        self.assertEqual([(r.id, r.passed) for r in rows], [("argo/application-controller", True), ("argo/zuno-vault-d1", True)])
        k, _ = kube({"/apis/argoproj.io/v1alpha1/namespaces/openshift-gitops/applications/zuno-vault-d1": self.app(health="Degraded"),
                     "/apis/apps/v1/namespaces/openshift-gitops/statefulsets/openshift-gitops-application-controller": controller})
        self.assertFalse(run(ds.evaluate(k, "d-state", [self.argo_unit()]))[1].passed)
        k, _ = kube({"/apis/argoproj.io/v1alpha1/namespaces/openshift-gitops/applications/zuno-vault-d1": self.app(age=7200),
                     "/apis/apps/v1/namespaces/openshift-gitops/statefulsets/openshift-gitops-application-controller": controller})
        self.assertIn("stale", run(ds.evaluate(k, "d-state", [self.argo_unit()]))[1].detail)

    def test_argo_refusals_say_what_to_enable(self):
        app = "/apis/argoproj.io/v1alpha1/namespaces/openshift-gitops/applications/zuno-vault-d1"
        sts = "/apis/apps/v1/namespaces/openshift-gitops/statefulsets/openshift-gitops-application-controller"
        k, _ = kube({}, denied=(app, sts))
        rows = run(ds.evaluate(k, "d-state", [self.argo_unit()]))
        self.assertFalse(any(r.passed for r in rows))
        self.assertTrue(all("status=403" in r.detail and "zuno_stress_reader_enabled" in r.detail for r in rows), [r.detail for r in rows])

    def test_a_transport_error_is_a_row_not_a_crash(self):
        def boom(request):
            raise httpx.ConnectError("refused")

        k = ds.Kube(httpx.AsyncClient(transport=httpx.MockTransport(boom)), "https://api")
        rows = run(ds.evaluate(k, "d-state", [{"type": "workload", "kind": "Deployment", "namespace": "n", "name": "w"}]))
        self.assertFalse(rows[0].passed)
        self.assertIn("ConnectError", rows[0].detail)


class Drivers(unittest.TestCase):
    def test_one_state_driver_per_demo_with_assertions(self):
        ids = {d.id for d in sr.REGISTRY.values() if d.family == "state"}
        self.assertEqual(ids, {f"{demo}-state" for demo in EXTRACTED["demos"]})
        self.assertEqual(len(ids), len(EXTRACTED["demos"]))
        self.assertFalse(any(d.mutating or d.sampler for d in sr.REGISTRY.values() if d.family == "state"))

    def test_a_driver_runs_the_demos_assertions_through_the_job_client(self):
        objects = {"/apis/cert-manager.io/v1/clusterissuers/vault-issuer": READY}
        handler, _ = fake_api(objects)
        original = ds._client
        ds._client = lambda ctx: httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            rows = run(sr.REGISTRY["vault-pki-state"].run(sr.Ctx(env={}).for_worker(0), 0))
        finally:
            ds._client = original
        self.assertGreaterEqual(len(rows), len(EXTRACTED["demos"]["vault-pki"]))
        by_id = {r.id: r for r in rows}
        self.assertTrue(by_id["clusterissuer/-/vault-issuer"].passed)
        self.assertTrue(all(r.agent == "vault-pki-state" and r.layer == "state" for r in rows))

    def test_the_assertions_are_read_flat_in_the_job(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, "state_assertions.json").write_text(json.dumps({"demos": {"only": [{"type": "workload", "kind": "Pod", "namespace": "n", "name": "p"}]}}))
            self.assertEqual(list(ds.load_assertions({"STRESS_DIR": tmp})), ["only"])
        self.assertGreaterEqual(len(ds.load_assertions({})), 30)

    def test_the_profiles_run_each_state_check_once_and_smoke_has_none(self):
        smoke = sr.build_plan(sr.load_profile("smoke", STRESS_DIR), {}, sr.REGISTRY)[0]
        self.assertFalse([p for p in smoke if p.driver.family == "state"])
        for name in ("standard", "aggressive"):
            plans = [p for p in sr.build_plan(sr.load_profile(name, STRESS_DIR), {}, sr.REGISTRY)[0] if p.driver.family == "state"]
            self.assertEqual(len(plans), len(EXTRACTED["demos"]), name)
            self.assertTrue(all((p.iterations, p.concurrency) == (1, 1) for p in plans), name)

    def test_family_defaults_sit_between_the_budget_and_the_drivers_own_settings(self):
        profile = {"defaults": {"iterations": 5}, "family_defaults": {"state": {"iterations": 1}}, "drivers": {"x": {"iterations": 9}}}
        self.assertEqual(sr.settings(profile, {}, "y", "state")["iterations"], 1)
        self.assertEqual(sr.settings(profile, {}, "x", "state")["iterations"], 9)
        self.assertEqual(sr.settings(profile, {}, "y", "tools")["iterations"], 5)
        self.assertEqual(sr.settings(profile, {"iterations": 2}, "y", "state")["iterations"], 2)

    def test_the_job_runs_as_the_reader_when_switched_on_and_ships_its_inputs(self):
        launch = (REPO / "ansible/roles/day3/tasks/stresstest_campaign_launch.yml").read_text()
        self.assertIn("'zuno-stress-reader' if (zuno_stress_reader_enabled", launch)
        self.assertIn("'acceptance-gate'", launch)
        self.assertIn("state_assertions.json", launch)
        self.assertIn("'argo_health.py'", launch)
        d1 = (REPO / "ansible/roles/namespaces/tasks/install_d1.yml").read_text()
        self.assertIn("stressReader", d1)


if __name__ == "__main__":
    unittest.main()
