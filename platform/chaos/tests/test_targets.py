"""The chaos target catalogue (platform/chaos/targets.yaml) and its validator, offline.

Covers the closed list (allow-listed workloads, one pod, bounded recovery, two kinds), the krkn scenarios it renders and the
plan of a run (which pipeline, which scenarios, a provider cut alone). The chart side (the generated values in sync, the
tiers present in the chart) is in test_chart.py.

Run from the repository root:
    python3 platform/chaos/tests/test_targets.py
"""
from __future__ import annotations

import copy
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "platform" / "chaos"))

import targets as tg  # noqa: E402


class Catalogue(unittest.TestCase):
    def setUp(self):
        self.cat = tg.load_catalogue()
        self.probes = tg.golden_path_probes()

    def target(self, cat, ident):
        return next(t for t in cat["targets"] if t["id"] == ident)

    def test_shipped_catalogue_is_valid(self):
        self.assertEqual(tg.validate(self.cat, self.probes), [])

    def test_the_brief_targets_are_all_there(self):
        ids = {t["id"] for t in self.cat["targets"]}
        self.assertEqual(ids, {"pod-ai-gateway", "pod-mcp-gateway", "pod-a2a-gateway", "pod-praxis", "pod-open-webui",
                               "pod-unifai", "pod-keycloak", "pod-kserve-controller", "pod-rhoai-operator",
                               "provider-cut-mistral", "pod-model-gpt-oss"})

    def test_probes_are_read_from_the_golden_path(self):
        self.assertTrue({"sovereignty", "tools", "open-webui", "unifai-tekos", "zuno-code", "delegation-approval"}
                        <= self.probes)

    def test_unknown_probe_is_refused(self):
        bad = copy.deepcopy(self.cat)
        self.target(bad, "pod-praxis")["probe"] = "no-such-moment"
        self.assertTrue(tg.validate(bad, self.probes))

    def test_workload_outside_the_allow_list_is_refused(self):
        bad = copy.deepcopy(self.cat)
        self.target(bad, "pod-praxis")["workload"] = {"kind": "Deployment", "name": "vault"}
        self.assertTrue(tg.validate(bad, self.probes))

    def test_control_plane_namespace_is_refused(self):
        bad = copy.deepcopy(self.cat)
        t = self.target(bad, "pod-praxis")
        t["namespace"] = "openshift-etcd"
        t["workload"] = {"kind": "Deployment", "name": "etcd"}
        self.assertTrue(tg.validate(bad, self.probes))

    def test_the_temporal_worker_is_never_a_target(self):
        bad = copy.deepcopy(self.cat)
        t = self.target(bad, "pod-unifai")
        t["workload"] = {"kind": "Deployment", "name": "unifai-multiagent-temporal-worker"}
        t["name_pattern"] = "^unifai-multiagent-temporal-worker-.*"
        self.assertTrue(tg.validate(bad, self.probes))

    def test_unknown_kind_is_refused(self):
        bad = copy.deepcopy(self.cat)
        self.target(bad, "pod-praxis")["kind"] = "node-drain"
        self.assertTrue(tg.validate(bad, self.probes))

    def test_more_than_one_pod_is_refused(self):
        bad = copy.deepcopy(self.cat)
        self.target(bad, "pod-praxis")["count"] = 2
        self.assertTrue(tg.validate(bad, self.probes))

    def test_recovery_is_bounded(self):
        bad = copy.deepcopy(self.cat)
        self.target(bad, "pod-praxis")["recover_within"] = tg.MAX_RECOVER + 1
        self.assertTrue(tg.validate(bad, self.probes))

    def test_selector_and_name_pattern_are_exclusive(self):
        bad = copy.deepcopy(self.cat)
        self.target(bad, "pod-unifai")["selector"] = {"app": "x"}
        self.assertTrue(tg.validate(bad, self.probes))
        bad = copy.deepcopy(self.cat)
        del self.target(bad, "pod-praxis")["selector"]
        self.assertTrue(tg.validate(bad, self.probes))

    def test_name_pattern_is_anchored_on_the_workload(self):
        bad = copy.deepcopy(self.cat)
        self.target(bad, "pod-unifai")["name_pattern"] = "^unifai-.*"
        self.assertTrue(tg.validate(bad, self.probes))

    def test_set_based_selector_is_refused(self):
        bad = copy.deepcopy(self.cat)
        self.target(bad, "pod-praxis")["selector"] = {"app.kubernetes.io/name": "praxis,app!=x"}
        self.assertTrue(tg.validate(bad, self.probes))

    def test_selector_verified_is_required(self):
        bad = copy.deepcopy(self.cat)
        del self.target(bad, "pod-praxis")["selector_verified"]
        self.assertTrue(tg.validate(bad, self.probes))

    def test_unverified_selectors_are_the_ones_to_check_live(self):
        unverified = {t["id"] for t in self.cat["targets"]
                      if t["kind"] == "pod-delete" and not t["selector_verified"]}
        self.assertEqual(unverified, {"pod-unifai", "pod-kserve-controller", "pod-rhoai-operator"})

    def test_provider_cut_host_outside_the_list_is_refused(self):
        bad = copy.deepcopy(self.cat)
        self.target(bad, "provider-cut-mistral")["host"] = "example.com"
        self.assertTrue(tg.validate(bad, self.probes))

    def test_provider_cut_duration_is_bounded(self):
        bad = copy.deepcopy(self.cat)
        self.target(bad, "provider-cut-mistral")["duration"] = tg.MAX_DURATION + 1
        self.assertTrue(tg.validate(bad, self.probes))

    def test_provider_cut_subject_is_the_ai_gateway_only(self):
        bad = copy.deepcopy(self.cat)
        self.target(bad, "provider-cut-mistral")["subject"]["selector"] = {"app.kubernetes.io/name": "mcp-gateway"}
        self.assertTrue(tg.validate(bad, self.probes))

    def test_duplicate_id_is_refused(self):
        bad = copy.deepcopy(self.cat)
        bad["targets"].append(copy.deepcopy(self.target(bad, "pod-praxis")))
        self.assertTrue(tg.validate(bad, self.probes))

    def test_a_node_reboot_is_in_no_tier(self):
        bad = copy.deepcopy(self.cat)
        bad["infra_tiers"]["hog"].append("30-node-reboot-worker")
        self.assertTrue(tg.validate(bad, self.probes))

    def test_infra_tiers_are_the_three_of_the_brief(self):
        self.assertEqual(self.cat["infra_tiers"], {
            "pods": ["10-pods-monitoring", "11-pods-ingress", "12-pods-apiserver"],
            "hog": ["20-hog-cpu-worker", "21-hog-memory-worker"],
            "latency": ["22-network-latency-worker"]})


class Scenarios(unittest.TestCase):
    def setUp(self):
        self.cat = tg.load_catalogue()

    def test_a_label_target_kills_one_pod_of_its_namespace(self):
        s = tg.scenario(next(t for t in self.cat["targets"] if t["id"] == "pod-keycloak"))
        config = s["content"][0]["config"]
        self.assertEqual(s["type"], "pod_disruption_scenarios")
        self.assertEqual(config["namespace_pattern"], "^zuno-auth$")
        self.assertEqual(config["label_selector"],
                         "app.kubernetes.io/instance=zuno,app.kubernetes.io/managed-by=keycloak-operator")
        self.assertEqual(config["kill"], 1)
        self.assertEqual(config["krkn_pod_recovery_time"], 300)
        self.assertNotIn("name_pattern", config)

    def test_a_name_target_has_no_label_selector(self):
        config = tg.scenario(next(t for t in self.cat["targets"] if t["id"] == "pod-unifai"))["content"][0]["config"]
        self.assertEqual(config["name_pattern"], "^unifai-multiagent-be-.*")
        self.assertNotIn("label_selector", config)

    def test_no_placeholder_is_left_for_the_pipeline_parameters(self):
        block = tg.render_values(self.cat)
        self.assertNotIn("${", block)

    def test_the_provider_cut_is_not_an_application_scenario(self):
        self.assertNotIn("provider-cut-mistral:", tg.render_values(self.cat))

    def test_the_block_carries_its_markers(self):
        block = tg.render_values(self.cat)
        self.assertTrue(block.strip().startswith(tg.BEGIN))
        self.assertTrue(block.strip().endswith(tg.END))


class Plan(unittest.TestCase):
    def setUp(self):
        self.cat = tg.load_catalogue()

    def test_infra_tier(self):
        p = tg.plan(self.cat, "infra", tier="pods")
        self.assertEqual(p["pipeline"], "chaos-infra")
        self.assertEqual(p["scenarios"], ["10-pods-monitoring", "11-pods-ingress", "12-pods-apiserver"])

    def test_unknown_tier_is_refused(self):
        with self.assertRaises(ValueError):
            tg.plan(self.cat, "infra", tier="reboot")

    def test_pod_targets_share_one_application_run_in_the_chart_order(self):
        p = tg.plan(self.cat, "platform", targets=["pod-mcp-gateway", "pod-ai-gateway"])
        self.assertEqual(p["pipeline"], "chaos-application")
        self.assertEqual(p["scenarios"], ["pod-ai-gateway", "pod-mcp-gateway"])
        self.assertEqual([t["id"] for t in p["targets"]], ["pod-mcp-gateway", "pod-ai-gateway"])

    def test_a_provider_cut_goes_to_the_zuno_pipeline(self):
        p = tg.plan(self.cat, "platform", targets=["provider-cut-mistral"])
        self.assertEqual(p["pipeline"], "zuno-chaos-provider-cut")
        self.assertEqual(p["params"]["host"], "api.mistral.ai")
        self.assertEqual(p["params"]["subject-selector"], "app.kubernetes.io/name=ai-gateway")
        self.assertEqual(p["params"]["duration"], "120")

    def test_a_provider_cut_runs_alone(self):
        with self.assertRaises(ValueError):
            tg.plan(self.cat, "platform", targets=["provider-cut-mistral", "pod-ai-gateway"])

    def test_unknown_or_repeated_or_empty_targets_are_refused(self):
        for targets in (["pod-vault"], ["pod-praxis", "pod-praxis"], [], [""]):
            with self.assertRaises(ValueError, msg=targets):
                tg.plan(self.cat, "platform", targets=targets)

    def test_cli_plan_and_show(self):
        import contextlib
        import io
        import json
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(tg.main(["show", "pod-praxis", "--json"]), 0)
        self.assertEqual(json.loads(out.getvalue())["namespace"], "zuno-ai-gateways")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tg.main(["plan", "--kind", "platform", "--targets", "pod-vault"]), 2)
        self.assertIn("unknown target", err.getvalue())


if __name__ == "__main__":
    unittest.main()
