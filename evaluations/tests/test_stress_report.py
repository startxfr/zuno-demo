"""The campaign report and the Limitador counters sampler (WP-312, ADR-0624), offline.

Run from the repository root:
    python3 evaluations/tests/test_stress_report.py
"""
from __future__ import annotations

import io
import json
import contextlib
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
STRESS_DIR = REPO / "evaluations" / "stress"
sys.path.insert(0, str(REPO / "platform" / "testing"))
sys.path.insert(0, str(REPO / "evaluations"))

import stress_report as rep  # noqa: E402
import stress_runner as sr  # noqa: E402

sr.load_drivers(STRESS_DIR)

import driver_counters as cnt  # noqa: E402


def summary(driver, n, ok, lat, c429=0, guard="", shard=0, shards=1):
    stats = {"n": n, "ok": ok, "err": n - ok, "c429": c429, "c5xx": 0, "timeouts": 0, "lat": lat, "guard": guard}
    return {"agent": driver, "layer": sr.SUMMARY_LAYER, "id": f"summary:s{shard}of{shards}", "category": "summary", "passed": ok == n and not guard,
            "detail": "x | " + json.dumps(stats), "duration_ms": 0}


def result(driver, ok=True, detail="status=200", layer="functional", id="r", category="models"):
    return {"agent": driver, "layer": layer, "id": id, "category": category, "passed": ok, "detail": detail, "duration_ms": 5}


class Report(unittest.TestCase):
    def rows(self):
        return [result("a"), result("a", ok=False, detail="status=429 quota", id="s0.i1/chat"), summary("a", 4, 3, [100, 200, 300, 400], c429=1),
                result("b"), summary("b", 2, 2, [50, 60]),
                result("a", ok=False, detail="stopped: 3 consecutive 429/5xx/timeouts", layer="stress", id="budget-guard", category="guard")]

    def test_the_report_merges_the_shards_and_lists_what_went_wrong(self):
        rows = self.rows() + [summary("a", 2, 2, [500, 600], shard=1, shards=2)]
        report = rep.build_report(rows, {"run_id": "r1", "profile": "smoke"})
        a = next(d for d in report["drivers"] if d["driver"] == "a")
        self.assertEqual((a["n"], a["ok"], a["err"], a["c429"], a["shards"]), (6, 5, 1, 1, 2))
        self.assertAlmostEqual(a["err_rate"], 1 / 6, places=3)
        self.assertEqual(report["failure_count"], 1)
        self.assertEqual(report["failures"][0]["id"], "s0.i1/chat")
        self.assertEqual(len(report["guards"]), 1)
        self.assertEqual(report["verdict"], "ATTENTION")

    def test_a_clean_run_says_so(self):
        report = rep.build_report([result("a"), summary("a", 1, 1, [10])])
        self.assertEqual((report["verdict"], report["failure_count"], report["guards"]), ("CLEAN", 0, []))

    def test_sampler_rows_are_sorted_into_their_sections_and_a_saturated_signal_needs_attention(self):
        rows = [summary("a", 1, 1, [10]),
                result("saturation", ok=False, detail="max=8 SATURATED (limit 4)", layer="saturation", id="vllm requests waiting", category="saturation"),
                result("saturation", ok=True, detail="max=0.2", layer="saturation", id="vllm kv-cache usage", category="saturation"),
                result("limitador-counters", ok=True, detail="moved +900 tokens", layer="counters", id="isolation", category="counters")]
        report = rep.build_report(rows)
        self.assertEqual([s["passed"] for s in report["saturation"]], [False, True])
        self.assertEqual(len(report["counters"]), 1)
        self.assertEqual(report["failure_count"], 0)  # a saturated signal is not a failing request
        self.assertEqual(report["verdict"], "ATTENTION")
        text = rep.render_text(report)
        self.assertIn("SATURATED vllm requests waiting", text)
        self.assertIn("LIMITADOR COUNTERS", text)

    def test_parse_rows_reads_json_array_lines_and_ignores_noise(self):
        text = "pip noise\n" + json.dumps([result("a")]) + "\nnot json [\n" + json.dumps([result("b"), result("c")]) + "\n"
        self.assertEqual([r["agent"] for r in rep.parse_rows(text)], ["a", "b", "c"])
        self.assertEqual(len(rep.parse_rows(json.dumps([result("a")]))), 1)
        self.assertEqual(rep.parse_rows(""), [])

    def test_failures_are_capped_with_the_total_kept(self):
        rows = [result("a", ok=False, detail=f"status=500 {i}", id=f"i{i}") for i in range(35)]
        report = rep.build_report(rows)
        self.assertEqual((len(report["failures"]), report["failure_count"]), (rep.FAILURE_LIMIT, 35))
        self.assertIn("and 15 more", rep.render_text(report))


class Trend(unittest.TestCase):
    def report(self, run_id, p95, err_ok, profile="standard"):
        lat = [p95] * 10
        return rep.build_report([summary("a", 10, err_ok, lat)], {"run_id": run_id, "profile": profile})

    def test_compare_flags_a_slower_p95_or_more_errors(self):
        previous = self.report("standard-20261119-100000", 1000, 10)
        self.assertFalse(rep.compare(self.report("x", 1200, 10), previous)[0]["regressed"])
        slow = rep.compare(self.report("x", 1600, 10), previous)[0]
        self.assertTrue(slow["regressed"])
        self.assertAlmostEqual(slow["p95_ratio"], 1.6)
        self.assertTrue(rep.compare(self.report("x", 1000, 9), previous)[0]["regressed"])
        self.assertEqual(rep.compare(self.report("x", 1000, 10), None), [])

    def test_a_driver_missing_from_the_previous_run_is_not_compared(self):
        other = rep.build_report([summary("z", 1, 1, [5])], {"run_id": "p", "profile": "standard"})
        self.assertEqual(rep.compare(self.report("x", 1000, 10), other), [])

    def test_the_newest_run_of_the_same_profile_is_the_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            for run_id, profile in (("standard-20261118-090000", "standard"), ("standard-20261119-090000", "standard"),
                                    ("smoke-20261119-100000", "smoke"), ("standard-20261119-110000", "standard")):
                rep.save_trend(self.report(run_id, 100, 10, profile), directory)
            previous = rep.load_previous(directory, "standard", "standard-20261119-110000")
            self.assertEqual(previous["run_id"], "standard-20261119-090000")  # not itself, not another profile
            self.assertIsNone(rep.load_previous(directory, "soak", "x"))
            self.assertIsNone(rep.load_previous(directory / "absent", "standard", "x"))

    def test_a_run_id_that_is_not_a_name_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                rep.save_trend(self.report("../escape", 1, 1), pathlib.Path(tmp))

    def test_the_trend_is_in_both_renderings(self):
        previous = self.report("a-1", 1000, 10)
        current = self.report("a-2", 2000, 8)
        diff = rep.compare(current, previous)
        self.assertIn("REGRESSED a: p95 1000ms -> 2000ms (x2.00), errors 0.0% -> 20.0%", rep.render_text(current, diff))
        self.assertIn("**REGRESSED** a", rep.render_markdown(current, diff))


class Cli(unittest.TestCase):
    def run_cli(self, rows, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), tempfile.NamedTemporaryFile("w", suffix=".json") as fh:
            fh.write("\n".join(json.dumps([r]) for r in rows))
            fh.flush()
            code = rep.main(["--rows", fh.name, *args])
        return code, out.getvalue(), err.getvalue()

    def test_it_writes_the_trend_and_the_evidence_only_when_asked_and_always_exits_zero(self):
        rows = [result("a"), summary("a", 1, 1, [10])]
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = self.run_cli(rows, "--run-id", "smoke-1", "--profile", "smoke")
            self.assertEqual(code, 0)
            self.assertIn("verdict=CLEAN", out)
            self.assertEqual(err, "")
            code, out, err = self.run_cli(rows, "--run-id", "smoke-2", "--profile", "smoke", "--trend-dir", tmp + "/t", "--evidence-dir", tmp + "/e")
            self.assertTrue(pathlib.Path(tmp, "t", "stress-smoke-2.json").is_file())
            evidence = pathlib.Path(tmp, "e", "stress-smoke-2.md").read_text()
            self.assertIn("# Stress campaign smoke-2", evidence)
            self.assertIn("review it, then commit it", err)
            code, out, err = self.run_cli(rows, "--run-id", "smoke-3", "--profile", "smoke", "--trend-dir", tmp + "/t")
            self.assertIn("TREND", out)  # smoke-2 is the baseline of smoke-3

    def test_an_unwritable_directory_never_loses_the_report(self):
        code, out, err = self.run_cli([summary("a", 1, 1, [10])], "--run-id", "x-1", "--profile", "x", "--trend-dir", "/proc/nope/trend")
        self.assertEqual(code, 0)
        self.assertIn("STRESS REPORT", out)
        self.assertIn("not saved", err)

    def test_json_and_markdown_formats(self):
        rows = [summary("a", 1, 1, [10])]
        self.assertIn('"verdict": "CLEAN"', self.run_cli(rows, "--format", "json")[1])
        self.assertTrue(self.run_cli(rows, "--run-id", "m-1", "--format", "markdown")[1].startswith("# Stress campaign m-1"))

    def test_it_runs_as_a_script_without_httpx(self):
        proc = subprocess.run([sys.executable, "-I", str(REPO / "platform/testing/stress_report.py"), "--rows", "-"],
                              input=json.dumps([summary("a", 1, 1, [10])]), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("STRESS REPORT", proc.stdout)


def counter(name, max_value, remaining, userid, **extra):
    return {"limit": {"name": name, "max_value": max_value}, "remaining": remaining, "set_variables": {"descriptors[0]['auth.identity.userid']": userid, **extra}}


class CountersSampler(unittest.TestCase):
    def test_it_is_a_sampler_of_its_own_family_and_the_profiles_use_it(self):
        d = sr.REGISTRY["limitador-counters"]
        self.assertTrue(d.sampler and d.finish is not None)
        self.assertEqual((d.family, d.interval), ("counters", 60.0))
        for name in ("standard", "aggressive", "soak"):
            plans = sr.build_plan(sr.load_profile(name, STRESS_DIR), {}, sr.REGISTRY)[0]
            self.assertIn("limitador-counters", [p.driver.id for p in plans], name)
        smoke = sr.build_plan(sr.load_profile("smoke", STRESS_DIR), {}, sr.REGISTRY)[0]
        self.assertNotIn("limitador-counters", [p.driver.id for p in smoke])

    def test_namespaces_come_from_the_metrics_labels(self):
        text = 'authorized_calls{limitador_namespace="zuno-ai-run/r1"} 4\nlimited_calls{limitador_namespace="zuno-ai-run/r2"} 1\n' \
               'authorized_calls{limitador_namespace="zuno-ai-run/r1"} 9\nlimitador_up 1\n'
        self.assertEqual(cnt.namespaces_of(text), ["zuno-ai-run/r1", "zuno-ai-run/r2"])
        self.assertEqual(cnt.namespaces_of("limitador_up 1"), [])

    def test_identity_is_the_service_account_in_the_variables(self):
        self.assertEqual(cnt.identity_of(counter("l", 10, 10, "system:serviceaccount:zuno-ai-run:ai-gateway-stress")), cnt.STRESS_SA)
        self.assertEqual(cnt.identity_of({"set_variables": {"a": "alice"}}), "alice")
        self.assertEqual(cnt.identity_of({}), "")

    def test_moved_by_identity_counts_consumption_between_two_reads(self):
        first = {"ns": [counter("tokens-a", 1000, 900, cnt.SHARED_SA)]}
        last = {"ns": [counter("tokens-a", 1000, 850, cnt.SHARED_SA),        # +50 on an existing counter
                       counter("tokens-b", 500, 440, cnt.STRESS_SA),        # +60 on a counter new in `last`
                       counter("tokens-c", 500, 500, cnt.STRESS_SA)]}       # unused
        moved = cnt.moved_by_identity(first, last)
        self.assertEqual(moved[cnt.SHARED_SA]["tokens"], 50)
        self.assertEqual(moved[cnt.STRESS_SA], {"tokens": 60, "limits": ["ns:tokens-b"]})

    def finish(self, samples):
        return {r.id: r for r in cnt.finish_counters(None, samples)}

    def test_the_isolation_row_states_both_numbers(self):
        first = {"ns": [counter("a", 1000, 1000, cnt.SHARED_SA), counter("b", 1000, 1000, cnt.STRESS_SA)]}
        last = {"ns": [counter("a", 1000, 1000, cnt.SHARED_SA), counter("b", 1000, 700, cnt.STRESS_SA)]}
        rows = self.finish([first, last])
        self.assertIn("stress ServiceAccount +300 tokens, shared ai-gateway ServiceAccount +0 tokens", rows["isolation"].detail)
        self.assertNotIn("did not move", rows["isolation"].detail)
        self.assertTrue(all(r.passed for r in rows.values()))

    def test_a_stress_counter_that_did_not_move_is_said(self):
        first = {"ns": [counter("a", 1000, 1000, cnt.SHARED_SA)]}
        rows = self.finish([first, first])
        self.assertIn("the stress counter did not move", rows["isolation"].detail)

    def test_no_counter_at_all_is_one_failing_row_that_names_the_shim(self):
        rows = self.finish([{"ns": []}, {"ns": []}])
        self.assertFalse(rows["no-counter"].passed)
        self.assertIn("wasm shim", rows["no-counter"].detail)

    def test_an_unreachable_limitador_is_one_row_that_says_how_to_read_it_anyway(self):
        rows = self.finish([ConnectionError("connection refused")] * 2)
        self.assertFalse(rows["sampler"].passed)
        self.assertIn("port-forward", rows["sampler"].detail)

    def test_the_job_ships_the_reader(self):
        launch = (REPO / "ansible/roles/day3/tasks/stresstest_campaign_launch.yml").read_text()
        self.assertIn("'quota_counters_probe.py'", launch)
        self.assertTrue((REPO / "platform/testing/quota_counters_probe.py").is_file())


class Wiring(unittest.TestCase):
    def test_the_collect_task_calls_the_report_and_the_coverage_stage(self):
        collect = (REPO / "ansible/roles/day3/tasks/stresstest_campaign_collect.yml").read_text()
        self.assertIn("platform/testing/stress_report.py", collect)
        self.assertIn("dashboard_coverage.py", collect)
        self.assertIn("--check-only", collect)

    def test_the_longer_profiles_end_with_the_coverage_stage_and_smoke_does_not(self):
        import yaml

        flags = {n: (yaml.safe_load((STRESS_DIR / f"profile_{n}.yaml").read_text()).get("job") or {}).get("coverage", False)
                 for n in ("smoke", "standard", "aggressive", "soak")}
        self.assertEqual(flags, {"smoke": False, "standard": True, "aggressive": True, "soak": True})


if __name__ == "__main__":
    unittest.main()
