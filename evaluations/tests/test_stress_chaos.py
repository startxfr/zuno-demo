"""The chaos disruptions of a stress campaign (WP-311, ADR-0624), offline.

Covers the closed catalogue and its validator, the plan, the AdminNetworkPolicy builder, the load timeline the runner keeps, the
report's correlation of a disruption window with that timeline, and the plan tasks' chaos facts (skipped without ansible).

Run from the repository root:
    python3 evaluations/tests/test_stress_chaos.py
"""
from __future__ import annotations

import copy
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "platform" / "testing"))
sys.path.insert(0, str(REPO / "evaluations" / "tests"))

import stress_chaos as ch  # noqa: E402
import stress_report as rep  # noqa: E402
import stress_runner as sr  # noqa: E402

import yaml  # noqa: E402


class Catalogue(unittest.TestCase):
    def setUp(self):
        self.cat = ch.load_catalogue()

    def test_shipped_catalogue_is_valid(self):
        self.assertEqual(ch.validate(self.cat), [])

    def test_aggressive_profile_lists_only_known_ids(self):
        profile = yaml.safe_load((REPO / "evaluations/stress/profile_aggressive.yaml").read_text())
        known = {d["id"] for d in self.cat["disruptions"]}
        self.assertTrue(profile["chaos"])
        self.assertLessEqual(set(profile["chaos"]), known)

    def test_only_aggressive_has_chaos(self):
        for name in ("smoke", "standard", "soak"):
            profile = yaml.safe_load((REPO / f"evaluations/stress/profile_{name}.yaml").read_text())
            self.assertFalse(profile.get("chaos"), name)

    def test_unknown_app_is_refused(self):
        bad = copy.deepcopy(self.cat)
        bad["disruptions"][0]["selector"] = {"app.kubernetes.io/name": "vault"}
        self.assertTrue(ch.validate(bad))

    def test_unknown_kind_is_refused(self):
        bad = copy.deepcopy(self.cat)
        bad["disruptions"][0]["kind"] = "node-drain"
        self.assertTrue(ch.validate(bad))

    def test_host_outside_the_list_is_refused(self):
        bad = copy.deepcopy(self.cat)
        cut = next(d for d in bad["disruptions"] if d["kind"] == "provider-cut")
        cut["host"] = "example.com"
        self.assertTrue(ch.validate(bad))

    def test_too_long_cut_is_refused(self):
        bad = copy.deepcopy(self.cat)
        cut = next(d for d in bad["disruptions"] if d["kind"] == "provider-cut")
        cut["duration"] = ch.MAX_DURATION + 1
        self.assertTrue(ch.validate(bad))


class Plan(unittest.TestCase):
    def test_order_and_spacing(self):
        cat = ch.load_catalogue()
        steps = ch.plan(cat, ["pod-ai-gateway", "provider-cut-mistral"], start=300, spacing=150)
        self.assertEqual([s["id"] for s in steps], ["pod-ai-gateway", "provider-cut-mistral"])
        first = steps[0]
        self.assertEqual(steps[0]["at"], 300)
        self.assertEqual(steps[1]["at"], 300 + first["recover_within"] + 150)

    def test_unknown_id(self):
        with self.assertRaises(ValueError):
            ch.plan(ch.load_catalogue(), ["nope"])


class Policy(unittest.TestCase):
    def cut(self):
        return next(d for d in ch.load_catalogue()["disruptions"] if d["kind"] == "provider-cut")

    def test_manifest_is_a_narrow_deny(self):
        m = ch.anp_manifest(self.cut(), "aggressive-20261119-100000", ["1.2.3.4/32"])
        self.assertEqual(m["kind"], "AdminNetworkPolicy")
        self.assertEqual(m["metadata"]["labels"]["zuno.io/stress-chaos"], "true")
        self.assertEqual([r["action"] for r in m["spec"]["egress"]], ["Deny"])
        self.assertNotIn("ingress", m["spec"])
        self.assertEqual(m["spec"]["egress"][0]["to"], [{"networks": ["1.2.3.4/32"]}])

    def test_pod_delete_has_no_policy(self):
        pod = next(d for d in ch.load_catalogue()["disruptions"] if d["kind"] == "pod-delete")
        with self.assertRaises(ValueError):
            ch.anp_manifest(pod, "run", ["1.2.3.4/32"])

    def test_run_id_must_be_a_name(self):
        with self.assertRaises(ValueError):
            ch.anp_manifest(self.cut(), "bad run;id", ["1.2.3.4/32"])

    def test_dns_is_injectable(self):
        fake = lambda host, port, **kw: [(2, 1, 6, "", ("9.9.9.9", 443)), (2, 1, 6, "", ("1.1.1.1", 443)), (2, 1, 6, "", ("9.9.9.9", 443))]
        self.assertEqual(ch.resolve_cidrs("api.mistral.ai", fake), ["1.1.1.1/32", "9.9.9.9/32"])
        with self.assertRaises(ValueError):
            ch.resolve_cidrs("bad host", fake)
        with self.assertRaises(ValueError):
            ch.resolve_cidrs("api.mistral.ai", lambda *a, **k: [])


class Timeline(unittest.TestCase):
    def test_runner_buckets_are_ten_seconds(self):
        self.assertEqual(sr.TIMELINE_BUCKET, 10)

    def test_merge_adds_buckets_of_shards(self):
        import json

        def row(tl, shard):
            stats = {"n": 2, "ok": 2, "err": 0, "c429": 0, "c5xx": 0, "timeouts": 0, "lat": [0.1], "guard": "", "tl": tl}
            return {"agent": "d", "layer": sr.SUMMARY_LAYER, "id": f"summary:s{shard}of2", "category": "summary", "passed": True,
                    "detail": "x | " + json.dumps(stats), "duration_ms": 0}
        merged = sr.merge_summaries([row([[100, 2, 0]], 0), row([[100, 1, 1], [110, 3, 0]], 1)])
        self.assertEqual(merged[0]["timeline"], [[100, 3, 1], [110, 3, 0]])


class Effects(unittest.TestCase):
    def timeline(self, errors_between):
        """Buckets 0..590 step 10, one iteration each, failing when the bucket is inside errors_between."""
        lo, hi = errors_between
        return {b: [1, 1 if lo <= b <= hi else 0] for b in range(0, 600, 10)}

    def test_failures_during_and_recovery(self):
        tl = self.timeline((300, 340))
        e = rep.chaos_effects(tl, 300, 330)
        self.assertEqual(e["before"][1], 0)
        self.assertGreater(e["during"][1], 0)
        self.assertEqual(e["recovered_after_s"], 20)

    def test_never_recovers(self):
        tl = self.timeline((300, 590))
        self.assertIsNone(rep.chaos_effects(tl, 300, 330)["recovered_after_s"])

    def test_no_effect(self):
        tl = self.timeline((9999, 9999))
        e = rep.chaos_effects(tl, 300, 330)
        self.assertEqual(e["during"][1], 0)
        self.assertEqual(e["recovered_after_s"], 0)

    def test_report_marks_unrecovered_chaos_as_attention(self):
        rows = [{"agent": "tools", "layer": "tools", "id": "t", "passed": True, "detail": ""},
                {"agent": "chaos-pod-x", "layer": "chaos", "id": "pod-x", "passed": False,
                 "detail": "window=300-330 not whole after 240s"}]
        report = rep.build_report(rows, {})
        self.assertEqual(len(report["chaos"]), 1)
        self.assertIsNone(report["chaos"][0]["effects"])
        self.assertIn("CHAOS", rep.render_text(report))
        self.assertIn("DID NOT RECOVER", rep.render_text(report))


class Wiring(unittest.TestCase):
    def test_makefile_sends_the_confirmation(self):
        make = (REPO / "Makefile").read_text()
        self.assertIn("stress_chaos_confirm", make)
        self.assertIn("CHAOS_CONFIRM", make)

    def test_campaign_plan_knows_chaos(self):
        plan = (REPO / "ansible/roles/day3/tasks/stresstest_campaign_plan.yml").read_text()
        for needle in ("_stress_chaos_ids", "_stress_chaos_confirmed", "stress_chaos_confirm"):
            self.assertIn(needle, plan)

    def test_chaos_rbac_is_off_by_default(self):
        values = yaml.safe_load((REPO / "gitops/charts/aap-config/values.yaml").read_text())
        self.assertIs(values["chaosRbac"]["enabled"], False)


if __name__ == "__main__":
    unittest.main()
