"""The shared-budget protections of the stress campaign (2026-11-19, ADR-0624), offline.

The standard run of 2026-11-19 left the shared ai-gateway ServiceAccount's MaaS counter at 1,002,556 / 1,000,000 and broke
`make d2 check agents`: the per-agent Jobs and the experience drivers ride that counter. What is guarded here:
  - the `agents` family is opt-in, the five stress twins are in /zuno-loadtest (the root fix, live after a keycloak roll);
  - the experience drivers are capped at one iteration and a guard skips a driver when the shared counter is above max_used;
  - the isolation row warns when the shared ServiceAccount moved more than 10% of its window budget;
  - the wait loop of the per-agent Jobs treats a deleted Job as terminal.

Run from the repository root:
    python3 evaluations/tests/test_stress_budget.py
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
STRESS_DIR = REPO / "evaluations" / "stress"
sys.path.insert(0, str(REPO / "platform" / "testing"))
sys.path.insert(0, str(REPO / "evaluations"))

import stress_runner as sr  # noqa: E402

sr.load_drivers(STRESS_DIR)

import driver_counters as cnt  # noqa: E402

EXPERIENCES = ("open-webui", "open-webui-zuno-code", "open-webui-zuno-wesh", "dify", "kagent", "blender-3d", "claude-code-sovereign",
               "maas-portal-api-keys", "identity-personas", "multi-gateway")


def counter(identity: str, limit: int, remaining: int, name: str = "tokens") -> dict:
    return {"limit": {"name": name, "max_value": limit}, "remaining": remaining, "set_variables": {"user": identity}}


class Profiles(unittest.TestCase):
    def profile(self, name):
        return yaml.safe_load((STRESS_DIR / f"profile_{name}.yaml").read_text())

    def test_the_experience_drivers_are_capped_at_one_iteration_with_the_guard_declared(self):
        for name in ("standard", "aggressive"):
            profile = self.profile(name)
            for driver in EXPERIENCES:
                self.assertEqual(profile["drivers"][driver]["iterations"], 1, (name, driver))
                self.assertEqual(profile["drivers"][driver]["concurrency"], 1, (name, driver))
            guard = profile["shared_budget_guard"]
            self.assertEqual(guard["max_used"], 0.5)
            self.assertLessEqual({"experiences", "unifai", "guardrails"}, set(guard["families"]))

    def test_the_agents_family_is_in_no_profile(self):
        for name in ("smoke", "standard", "aggressive", "soak", "mutating"):
            self.assertNotIn("agents", self.profile(name)["families"], name)

    @unittest.skip("2026-11-19 owner split: the keycloak part (/zuno-loadtest on the stress twins) waits for his go; remove this skip when it lands")
    def test_the_stress_twins_are_in_the_loadtest_group(self):
        values = yaml.safe_load((REPO / "gitops/charts/keycloak/values.yaml").read_text())
        twins = {p["username"]: p for p in values["evalPersonas"] if p["username"].startswith("stress-") and p["username"] != "stress-mutate-01"}
        for name in ("stress-consultant-01", "stress-sale-01", "stress-adv-01", "stress-finance-01", "stress-board-01"):
            self.assertIn("/zuno-loadtest", twins[name].get("extraGroups") or [], name)
        self.assertIn("/zuno-loadtest", values["evalPersonasExtraGroups"])


class Guard(unittest.TestCase):
    PROFILE = {"shared_budget_guard": {"families": ["experiences", "unifai"], "max_used": 0.5}}

    def test_the_verdict(self):
        v = sr.shared_budget_verdict
        self.assertEqual(v(self.PROFILE, "experiences", [0.2]), "")
        self.assertEqual(v(self.PROFILE, "experiences", [None]), "")           # unknown: the run goes on
        self.assertEqual(v(self.PROFILE, "models", [0.99]), "")                # not a family the guard watches
        self.assertEqual(v({}, "experiences", [0.99]), "")                     # no guard declared
        self.assertIn("50%", v(self.PROFILE, "experiences", [0.5]))
        self.assertIn("98%", v(self.PROFILE, "unifai", [0.1, 0.98]))

    def test_a_spent_shared_budget_skips_the_family_and_says_so(self):
        ran = []

        async def run(ctx, i):
            ran.append(1)
            return [sr.row("exp", "functional", "ok", "experiences", True, "status=200")]
        plans = [sr.Plan(driver=sr.Driver(id="exp", family="experiences", run=run), iterations=1, concurrency=1, duration=0.0,
                         rate=0.0, ramp=0.0, timeout=5.0),
                 sr.Plan(driver=sr.Driver(id="tool", family="tools", run=run), iterations=1, concurrency=1, duration=0.0,
                         rate=0.0, ramp=0.0, timeout=5.0)]
        saved = list(sr.SHARED_BUDGET_PROBES)
        sr.SHARED_BUDGET_PROBES[:] = [lambda ctx: 0.8]
        try:
            rows = asyncio.run(sr.run_all(plans, sr.Ctx(env={}), dict(self.PROFILE, name="t"), {}, 0, 1, emit=lambda r: None))
        finally:
            sr.SHARED_BUDGET_PROBES[:] = saved
        skipped = [r for r in rows if r.id == "shared-budget"]
        self.assertEqual([(r.agent, r.passed) for r in skipped], [("exp", False)])
        self.assertIn("80% spent", skipped[0].detail)
        self.assertEqual(len(ran), 1)  # only the `tools` driver ran

    def test_a_failing_probe_does_not_stop_the_run(self):
        async def run(ctx, i):
            return [sr.row("exp", "functional", "ok", "experiences", True, "status=200")]

        def broken(ctx):
            raise OSError("limitador unreachable")
        plan = sr.Plan(driver=sr.Driver(id="exp", family="experiences", run=run), iterations=1, concurrency=1, duration=0.0,
                       rate=0.0, ramp=0.0, timeout=5.0)
        saved = list(sr.SHARED_BUDGET_PROBES)
        sr.SHARED_BUDGET_PROBES[:] = [broken]
        try:
            rows = asyncio.run(sr.run_all([plan], sr.Ctx(env={}), dict(self.PROFILE, name="t"), {}, 0, 1, emit=lambda r: None))
        finally:
            sr.SHARED_BUDGET_PROBES[:] = saved
        self.assertFalse([r for r in rows if r.id == "shared-budget"])
        self.assertTrue(any(r.id.endswith("ok") and r.passed for r in rows))

    def test_an_unreadable_shared_budget_is_one_warning_row_and_the_drivers_run(self):
        ran = []

        async def run(ctx, i):
            ran.append(1)
            return [sr.row("exp", "functional", "ok", "experiences", True, "status=200")]
        plans = [sr.Plan(driver=sr.Driver(id=f"exp{n}", family="experiences", run=run), iterations=1, concurrency=1, duration=0.0,
                         rate=0.0, ramp=0.0, timeout=5.0) for n in range(3)]
        saved = list(sr.SHARED_BUDGET_PROBES)
        sr.SHARED_BUDGET_PROBES[:] = [lambda ctx: None]
        try:
            rows = asyncio.run(sr.run_all(plans, sr.Ctx(env={}), dict(self.PROFILE, name="t"), {}, 0, 1, emit=lambda r: None))
        finally:
            sr.SHARED_BUDGET_PROBES[:] = saved
        warnings = [r for r in rows if r.id == "shared-budget-unknown"]
        self.assertEqual(len(warnings), 1)  # once per run, not per driver
        self.assertFalse(warnings[0].passed)
        self.assertIn("SKIPPED", warnings[0].detail)
        self.assertEqual(len(ran), 3)

    def test_the_counters_driver_registers_its_probe(self):
        self.assertIn(cnt.shared_budget_probe, sr.SHARED_BUDGET_PROBES)


class Fractions(unittest.TestCase):
    def test_spent_and_moved_fractions_of_the_shared_account_only(self):
        first = {"ns": [counter(cnt.SHARED_SA, 1000, 900), counter(cnt.STRESS_SA, 1000, 100)]}
        last = {"ns": [counter(cnt.SHARED_SA, 1000, 600), counter(cnt.STRESS_SA, 1000, 0)]}
        self.assertAlmostEqual(cnt.spent_fraction(last), 0.4)
        self.assertAlmostEqual(cnt.moved_fraction(first, last), 0.3)
        self.assertAlmostEqual(cnt.moved_fraction(first, last, cnt.STRESS_SA), 0.1)
        self.assertIsNone(cnt.spent_fraction({"ns": [counter(cnt.STRESS_SA, 10, 5)]}))

    def finish(self, shared_moved):
        first = {"ns": [counter(cnt.SHARED_SA, 1000, 1000), counter(cnt.STRESS_SA, 1000, 1000)]}
        last = {"ns": [counter(cnt.SHARED_SA, 1000, 1000 - shared_moved), counter(cnt.STRESS_SA, 1000, 900)]}
        rows = cnt.finish_counters(None, [first, last])
        return next(r for r in rows if r.id == "isolation")

    def test_the_isolation_row_warns_above_ten_percent(self):
        quiet = self.finish(50)
        self.assertTrue(quiet.passed)
        self.assertNotIn("WARNING", quiet.detail)
        loud = self.finish(300)
        self.assertFalse(loud.passed)
        self.assertTrue(loud.detail.startswith("WARNING"))
        self.assertIn("30%", loud.detail)


class SkippedByDesign(unittest.TestCase):
    def test_a_saas_scenario_under_a_closed_class_is_skipped_not_failed(self):
        import stress_report as rep
        rows = [{"agent": "tekos", "layer": "scenario", "id": "21", "category": "scenario", "passed": False, "duration_ms": 1,
                 "detail": "status=502 mistral-codestral: not reached through MaaS, skipped for closed quota class 'loadtest'"},
                {"agent": "tekos", "layer": "scenario", "id": "22", "category": "scenario", "passed": False, "duration_ms": 1,
                 "detail": "status=500 a real failure"}]
        report = rep.build_report(rows, {})
        self.assertEqual([f["id"] for f in report["failures"]], ["22"])
        self.assertEqual([f["id"] for f in report["skipped_by_design"]], ["21"])
        self.assertTrue(report["skipped_by_design"][0]["detail"].startswith("skipped: SaaS under loadtest"))
        self.assertIn("SKIPPED BY DESIGN (1)", rep.render_text(report))

    def test_the_profiles_say_so(self):
        for name in ("standard", "aggressive"):
            text = (STRESS_DIR / f"profile_{name}.yaml").read_text()
            self.assertIn("skipped: SaaS under loadtest", text)


class WaitLoop(unittest.TestCase):
    def test_a_deleted_job_is_terminal(self):
        text = (REPO / "ansible/roles/day3/tasks/stresstest_job_wait_one.yml").read_text()
        self.assertIn("| length) == 0 or", text)
        self.assertIn("job-missing", text)
        # the pod lookup, the log fetch and the parse run only when the Job exists (they index resources[0])
        self.assertGreaterEqual(text.count("(_day2_stress_job.resources | default([])) | length > 0"), 3)


if __name__ == "__main__":
    unittest.main()
