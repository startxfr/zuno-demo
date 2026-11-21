"""gitops/charts/chaos against the catalogue (platform/chaos/targets.yaml), offline.

The values half needs only PyYAML: the generated application scenarios in sync with the catalogue, the infra tiers present
and enabled, the node-level scenarios on the labelled node with the infra toleration, the provider-cut allow-list equal to
the catalogue's. The render half needs helm and the two startx dependencies under gitops/charts/chaos/charts/ (21.3.392 is
not on the stable index yet, see the chart README): it skips without them. It renders the chart, checks what a run relies
on, and runs the zuno-provider-cut script with a stub `oc` to compare its AdminNetworkPolicy with the WP-311 shape
(platform/testing/stress_chaos.py anp_manifest).

Run from the repository root:
    python3 platform/chaos/tests/test_chart.py
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "platform" / "chaos"))
sys.path.insert(0, str(REPO / "platform" / "testing"))

import targets as tg  # noqa: E402

CHART = REPO / "gitops" / "charts" / "chaos"
INFRA_TAINT = "node-role.kubernetes.io/infra:NoSchedule"


def values():
    return yaml.safe_load((CHART / "values.yaml").read_text())


class Values(unittest.TestCase):
    def setUp(self):
        self.values = values()
        self.cat = tg.load_catalogue()
        self.pipeline = self.values["pipeline"]["pipeline"]

    def test_generated_scenarios_are_in_sync_with_the_catalogue(self):
        self.assertEqual(tg.generated_block((CHART / "values.yaml").read_text()), tg.render_values(self.cat),
                         "run python3 platform/chaos/targets.py render-values --write")

    def test_every_pod_target_is_an_enabled_application_scenario(self):
        scenarios = self.pipeline["application"]["scenarios"]
        for t in self.cat["targets"]:
            if t["kind"] == "pod-delete":
                self.assertEqual(scenarios[t["id"]], tg.scenario(t), t["id"])
        self.assertNotIn("provider-cut-mistral", scenarios)

    def test_the_generic_application_scenarios_are_off(self):
        scenarios = self.pipeline["application"]["scenarios"]
        for name in ("10-pods", "20-container", "30-service-disruption"):
            self.assertIs(scenarios[name]["enabled"], False, name)

    def test_every_tier_scenario_is_enabled_in_the_chart(self):
        infra = self.pipeline["infra"]["scenarios"]
        for tier, names in self.cat["infra_tiers"].items():
            for name in names:
                self.assertIs(infra.get(name, {}).get("enabled"), True, f"{tier}: {name}")
        self.assertIs(infra["30-node-reboot-worker"]["enabled"], False)

    def test_node_level_scenarios_target_the_labelled_infra_node(self):
        self.assertEqual(self.pipeline["nodeSelector"], "zuno.io/chaos-target=true")
        self.assertEqual(self.pipeline["workloadNamespace"], "zuno-chaos")
        self.assertEqual(self.pipeline["privilegedNamespaces"], ["zuno-chaos"])
        infra = self.pipeline["infra"]["scenarios"]
        cpu, mem = infra["20-hog-cpu-worker"]["content"], infra["21-hog-memory-worker"]["content"]
        net = infra["22-network-latency-worker"]["content"][0]
        self.assertEqual((cpu["cpu-load-percentage"], cpu["duration"], cpu["number-of-nodes"]), (80, 60, 1))
        self.assertEqual((mem["memory-vm-bytes"], mem["duration"], mem["number-of-nodes"]), ("50%", 60, 1))
        self.assertEqual((net["test_duration"], net["instance_count"]), (60, 1))
        for content, key in ((cpu, "node-selector"), (mem, "node-selector"), (net, "label_selector")):
            self.assertEqual(content[key], "${NODE_SELECTOR}")
            self.assertEqual(content["namespace"], "${WORKLOAD_NAMESPACE}")
            self.assertEqual(content["taints"], [INFRA_TAINT])

    def test_critical_alerts_check_stays_off(self):
        self.assertIs(self.pipeline["checkCriticalAlerts"], False)

    def test_one_namespace_and_one_cerberus_url(self):
        url = "http://cerberus.zuno-chaos.svc.cluster.local:8080"
        self.assertEqual(self.values["zuno"]["namespace"], "zuno-chaos")
        self.assertEqual(self.values["cerberus"]["project"]["project"]["name"], "zuno-chaos")
        self.assertEqual(self.values["pipeline"]["project"]["project"]["name"], "zuno-chaos")
        self.assertEqual(self.values["zuno"]["cerberusUrl"], url)
        self.assertEqual(self.pipeline["cerberus"]["url"], url)
        self.assertEqual(self.values["cerberus"]["cerberus"]["allowedNamespaces"], [])
        self.assertEqual(self.values["cerberus"]["cerberus"]["watch_url_routes"], [])

    def test_cerberus_watches_the_namespaces_of_the_targets(self):
        watched = set(self.values["cerberus"]["cerberus"]["watch_namespaces"])
        for t in self.cat["targets"]:
            ns = t.get("namespace") or t["subject"]["namespace"]
            if ns != "redhat-ods-operator":
                self.assertIn(ns, watched, t["id"])

    def test_provider_cut_allow_list_equals_the_catalogue(self):
        cut = self.values["zuno"]["providerCut"]
        self.assertEqual(tuple(cut["allowedHosts"]), tg.ALLOWED_HOSTS)
        self.assertEqual(cut["maxDuration"], tg.MAX_DURATION)
        subjects = {f"{t['subject']['namespace']}|{tg.label_selector(t['subject']['selector'])}"
                    for t in self.cat["targets"] if t["kind"] == "provider-cut"}
        self.assertEqual(set(cut["allowedSubjects"]), subjects)

    def test_parts_are_off_by_default(self):
        self.assertIs(self.values["zuno"]["enabled"], False)
        self.assertIs(self.values["cerberus"]["cerberus"]["enabled"], False)
        self.assertIs(self.pipeline["enabled"], False)

    def test_dependencies_are_the_two_startx_charts_at_one_pinned_version(self):
        chart = yaml.safe_load((CHART / "Chart.yaml").read_text())
        deps = {d["alias"]: (d["name"], d["version"]) for d in chart["dependencies"]}
        self.assertEqual(deps, {"cerberus": ("chaos-cerberus", "21.3.392"), "pipeline": ("chaos-pipeline", "21.3.392")})


def _render_ready():
    return shutil.which("helm") and list((CHART / "charts").glob("chaos-pipeline-*.tgz")) and \
        list((CHART / "charts").glob("chaos-cerberus-*.tgz"))


ON = ["--set", "zuno.enabled=true", "--set", "cerberus.cerberus.enabled=true", "--set", "pipeline.pipeline.enabled=true"]


def render(extra=()):
    out = subprocess.run(["helm", "template", "zuno-chaos-d1", str(CHART), "--namespace", "zuno-chaos", *extra],
                         capture_output=True, text=True, check=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


@unittest.skipUnless(_render_ready(), "needs helm and the 21.3.392 dependencies under gitops/charts/chaos/charts/")
class Render(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = render(ON)
        cls.cat = tg.load_catalogue()

    def get(self, kind, name):
        return next(d for d in self.docs if d["kind"] == kind and d["metadata"]["name"] == name)

    def test_nothing_renders_by_default(self):
        self.assertEqual(render(), [])

    def test_no_pipelinerun_is_rendered(self):
        self.assertFalse([d for d in self.docs if d["kind"] in ("PipelineRun", "TaskRun")])

    def test_everything_lands_in_zuno_chaos(self):
        for d in self.docs:
            if d["kind"] not in ("ClusterRole", "ClusterRoleBinding"):
                self.assertEqual(d["metadata"].get("namespace"), "zuno-chaos", f"{d['kind']}/{d['metadata']['name']}")

    def test_the_objects_a_run_relies_on(self):
        for kind, name in (("Task", "cerberus-check"), ("Task", "krkn-run"), ("Task", "zuno-provider-cut"),
                           ("Task", "zuno-steady-state"), ("Pipeline", "chaos-infra"), ("Pipeline", "chaos-application"),
                           ("Pipeline", "zuno-chaos-provider-cut"), ("ServiceAccount", "chaos-pipeline"),
                           ("Service", "cerberus"), ("ConfigMap", "chaos-pipeline-scenarios")):
            self.assertTrue(self.get(kind, name))

    def test_application_pipeline_offers_exactly_the_pod_targets(self):
        pipeline = self.get("Pipeline", "chaos-application")
        default = next(p for p in pipeline["spec"]["params"] if p["name"] == "scenarios")["default"]
        self.assertEqual(default, sorted(t["id"] for t in self.cat["targets"] if t["kind"] == "pod-delete"))

    def test_infra_pipeline_offers_every_tier_scenario(self):
        pipeline = self.get("Pipeline", "chaos-infra")
        default = next(p for p in pipeline["spec"]["params"] if p["name"] == "scenarios")["default"]
        self.assertEqual(sorted(default), sorted(s for names in self.cat["infra_tiers"].values() for s in names))
        params = {p["name"]: p.get("default") for p in pipeline["spec"]["params"]}
        self.assertEqual(params["node-selector"], "zuno.io/chaos-target=true")
        self.assertEqual(params["workload-namespace"], "zuno-chaos")

    def test_krkn_helper_pods_are_privileged_in_zuno_chaos_only(self):
        bindings = [d for d in self.docs if d["kind"] == "RoleBinding"
                    and d["roleRef"]["name"] == "system:openshift:scc:privileged"]
        self.assertEqual([b["metadata"]["namespace"] for b in bindings], ["zuno-chaos"])

    def test_zuno_task_images_are_pinned_by_digest(self):
        for name in ("zuno-provider-cut", "zuno-steady-state"):
            for step in self.get("Task", name)["spec"]["steps"]:
                self.assertRegex(step["image"], r"@sha256:[0-9a-f]{64}$")

    def test_aap_roles_stay_in_zuno_chaos(self):
        runner = self.get("RoleBinding", "zuno-chaos-runner")
        reader = self.get("RoleBinding", "zuno-chaos-signal-reader")
        self.assertEqual({s["name"] for s in runner["subjects"]}, {"aap-installer"})
        self.assertEqual({s["name"] for s in reader["subjects"]}, {"aap-day0-check", "aap-installer"})
        rules = self.get("Role", "zuno-chaos-signal-reader")["rules"]
        proxy = next(r for r in rules if r["resources"] == ["services/proxy"])
        self.assertEqual(proxy["verbs"], ["get"])
        self.assertTrue(all("cerberus" in n for n in proxy["resourceNames"]))

    def test_provider_cut_grant_is_bound_to_the_pipeline_account_only(self):
        binding = self.get("ClusterRoleBinding", "zuno-chaos-provider-cut")
        self.assertEqual(binding["subjects"], [{"kind": "ServiceAccount", "name": "chaos-pipeline",
                                                "namespace": "zuno-chaos"}])
        rule = self.get("ClusterRole", "zuno-chaos-provider-cut")["rules"]
        self.assertEqual(rule[0]["resources"], ["adminnetworkpolicies"])

    def test_provider_cut_pipeline_reaps_in_finally(self):
        spec = self.get("Pipeline", "zuno-chaos-provider-cut")["spec"]
        reap = next(t for t in spec["finally"] if t["name"] == "reap")
        self.assertIn({"name": "action", "value": "reap"}, reap["params"])
        self.assertEqual([t["name"] for t in spec["tasks"]], ["cerberus-gate", "provider-cut", "steady-state"])

    def _run_cut(self, env):
        step = self.get("Task", "zuno-provider-cut")["spec"]["steps"][0]
        base = {e["name"]: e["value"] for e in step["env"] if not e["value"].startswith("$(")}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            stubs = tmp / "bin"
            stubs.mkdir()
            (stubs / "oc").write_text('#!/bin/bash\necho "oc $*" >> "$SIMDIR/log"\n'
                                      '[ "$1" = apply ] && cp "$3" "$SIMDIR/applied.yaml"\n'
                                      '[ "$1" = get ] && exit 1\nexit 0\n')
            (stubs / "getent").write_text("#!/bin/bash\nprintf '203.0.113.7 STREAM h\\n203.0.113.9 STREAM\\n'\n")
            (stubs / "sleep").write_text("#!/bin/bash\nexit 0\n")
            for f in stubs.iterdir():
                f.chmod(0o755)
            script = tmp / "cut.sh"
            script.write_text(step["script"])
            full = {**os.environ, **base, **env, "SIMDIR": str(tmp), "PATH": f"{stubs}:{os.environ['PATH']}",
                    "RESULT_STATUS": str(tmp / "status"), "RESULT_ADDRESSES": str(tmp / "addresses")}
            proc = subprocess.run(["bash", str(script)], env=full, capture_output=True, text=True)
            applied = yaml.safe_load((tmp / "applied.yaml").read_text()) if (tmp / "applied.yaml").exists() else None
            log = (tmp / "log").read_text() if (tmp / "log").exists() else ""
            return proc, applied, log, (tmp / "status").read_text()

    CUT = {"ACTION": "cut", "RUN_ID": "zuno-chaos-provider-cut-x1", "TARGET_ID": "provider-cut-mistral",
           "HOST": "api.mistral.ai", "SUBJECT_NAMESPACE": "zuno-ai-run",
           "SUBJECT_SELECTOR": "app.kubernetes.io/name=ai-gateway", "DURATION": "120"}

    def test_provider_cut_policy_has_the_wp311_shape_and_is_removed(self):
        import stress_chaos
        proc, applied, log, status = self._run_cut(self.CUT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(status, "passed")
        target = next(t for t in self.cat["targets"] if t["id"] == "provider-cut-mistral")
        expected = stress_chaos.anp_manifest(target, "x1", ["203.0.113.7/32", "203.0.113.9/32"])
        self.assertEqual(applied["spec"], expected["spec"])
        self.assertEqual(applied["metadata"]["labels"]["zuno.io/stress-chaos"], "true")
        self.assertEqual(applied["metadata"]["labels"]["zuno.io/chaos"], "true")
        self.assertIn("oc delete adminnetworkpolicy zuno-chaos-provider-cut-mistral", log)

    def test_provider_cut_refuses_what_the_allow_list_does_not_hold(self):
        for change in ({"HOST": "example.com"}, {"SUBJECT_SELECTOR": "app.kubernetes.io/name=mcp-gateway"},
                       {"DURATION": "301"}, {"DURATION": "0"}, {"TARGET_ID": "../x"}, {"ACTION": "drain"}):
            proc, applied, log, status = self._run_cut({**self.CUT, **change})
            self.assertNotEqual(proc.returncode, 0, change)
            self.assertIsNone(applied, change)
            self.assertEqual(status, "failed", change)

    def test_reap_deletes_every_chaos_policy(self):
        proc, applied, log, status = self._run_cut({"ACTION": "reap", "RUN_ID": "r"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("oc delete adminnetworkpolicy -l zuno.io/chaos=true", log)
        self.assertIsNone(applied)


if __name__ == "__main__":
    unittest.main()
