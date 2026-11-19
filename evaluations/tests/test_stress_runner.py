"""stress_runner: the plan, the scheduler, the budget guard, the summaries and the first drivers (WP-305, ADR-0624).

Everything is offline: the drivers run against httpx.MockTransport, the scheduler against small fake drivers.

Run from the repository root:
    python3 evaluations/tests/test_stress_runner.py
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import time
import unittest
from unittest import mock

import httpx
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
STRESS_DIR = REPO / "evaluations" / "stress"
sys.path.insert(0, str(REPO / "platform" / "testing"))
sys.path.insert(0, str(REPO / "evaluations"))

import stress_runner as sr  # noqa: E402

sr.load_drivers(STRESS_DIR)


def fake(id="fake", family="tools", mutating=False, fn=None):
    async def run(ctx, i):
        return [sr.row(id, "functional", "ok", family, True, "status=200 fine")]

    return sr.Driver(id=id, family=family, run=fn or run, mutating=mutating)


def plan_of(driver, iterations=1, concurrency=1, duration=0.0, rate=0.0, ramp=0.0, timeout=5.0):
    return sr.Plan(driver=driver, iterations=iterations, concurrency=concurrency, duration=duration, rate=rate, ramp=ramp, timeout=timeout)


def run_plan(plan, guard=None, ctx=None):
    rows = []
    ctx = ctx or sr.Ctx(env={})
    guard = guard or sr.Guard(3, 10)
    stats = asyncio.run(sr.run_plan(plan, ctx, guard, rows.extend))
    return stats, rows, guard


class PlanResolution(unittest.TestCase):
    REG = {d.id: d for d in (fake("a", "tools"), fake("b", "models"), fake("c", "models"), fake("m", "tools", mutating=True))}

    def ids(self, profile, overrides=None):
        chosen, warnings = sr.select_drivers(profile, overrides or {}, self.REG)
        return [d.id for d in chosen], warnings

    def test_all_drivers_when_nothing_is_selected(self):
        ids, warnings = self.ids({})
        self.assertEqual(ids, ["b", "c", "a"])  # by family, then id
        self.assertTrue(any("'m'" in w and "allow_mutating" in w for w in warnings))

    def test_families_include_exclude(self):
        self.assertEqual(self.ids({"families": ["models"]})[0], ["b", "c"])
        self.assertEqual(self.ids({"families": ["models"], "exclude": ["c"]})[0], ["b"])
        self.assertEqual(self.ids({"include": ["a", "c"]})[0], ["c", "a"])

    def test_overrides_win_over_the_profile(self):
        self.assertEqual(self.ids({"families": ["tools"]}, {"families": ["models"]})[0], ["b", "c"])
        self.assertEqual(self.ids({"families": ["tools"]}, {"drivers": "c"})[0], ["c"])

    def test_unknown_driver_is_a_warning_not_an_error(self):
        ids, warnings = self.ids({"include": ["a", "nope"]})
        self.assertEqual(ids, ["a"])
        self.assertIn("unknown driver 'nope'", warnings)

    def test_mutating_driver_runs_only_when_the_profile_allows_it(self):
        self.assertIn("m", self.ids({"allow_mutating": True})[0])

    def test_settings_precedence(self):
        profile = {"defaults": {"iterations": 3, "timeout": 50}, "budget": {"max_tokens": 100},
                   "drivers": {"a": {"iterations": 9}}}
        self.assertEqual(sr.settings(profile, {}, "a")["iterations"], 9)
        self.assertEqual(sr.settings(profile, {}, "b")["iterations"], 3)
        self.assertEqual(sr.settings(profile, {"iterations": 1}, "a")["iterations"], 1)
        self.assertEqual(sr.settings(profile, {"max_tokens": 7}, "a")["max_tokens"], 7)
        self.assertEqual(sr.settings(profile, {}, "a")["max_tokens"], 100)

    def test_sharding_splits_iterations_and_concurrency(self):
        self.assertEqual([sr.shard_split(10, i, 3) for i in range(3)], [4, 3, 3])
        self.assertEqual(sum(sr.shard_split(7, i, 4) for i in range(4)), 7)
        profile = {"defaults": {"iterations": 10, "concurrency": 5, "rate": 2}}
        plans, _ = sr.build_plan(profile, {}, {"a": fake("a")}, shard_index=0, shards=2)
        self.assertEqual((plans[0].iterations, plans[0].concurrency, plans[0].rate), (5, 3, 1.0))

    def test_overrides_parse(self):
        self.assertEqual(sr.parse_overrides(""), {})
        self.assertEqual(sr.parse_overrides('{"iterations": 4, "families": []}'), {"iterations": 4})
        with self.assertRaises(ValueError):
            sr.parse_overrides("not json")
        with self.assertRaises(ValueError):
            sr.parse_overrides("[1]")


class ShippedProfiles(unittest.TestCase):
    def test_every_profile_is_valid_and_names_known_things(self):
        known_families = {d.family for d in sr.REGISTRY.values()} | {"agents"}
        profiles = sorted(STRESS_DIR.glob("profile_*.yaml"))
        self.assertEqual([p.stem for p in profiles], ["profile_aggressive", "profile_smoke", "profile_soak", "profile_standard"])
        for path in profiles:
            data = yaml.safe_load(path.read_text())
            self.assertEqual(data["name"], path.stem.replace("profile_", ""))
            self.assertTrue(set(data["families"]) <= known_families, path.name)
            self.assertIsInstance(data["job"]["deadline_seconds"], int)
            plans, warnings = sr.build_plan(data, {}, sr.REGISTRY)
            self.assertEqual(warnings, [], path.name)
            self.assertTrue(plans or path.stem == "profile_agents", path.name)

    def test_smoke_cannot_drain_a_budget(self):
        smoke = sr.load_profile("smoke", STRESS_DIR)
        s = sr.settings(smoke, {}, "ai-gateway-routing")
        self.assertEqual((s["iterations"], s["concurrency"]), (1, 1))
        self.assertLessEqual(s["max_tokens"], 2000)
        self.assertLessEqual(s["max_429"], 2)

    def test_unknown_profile_is_an_error(self):
        with self.assertRaises(ValueError):
            sr.load_profile("nope", STRESS_DIR)


class Scheduler(unittest.TestCase):
    def test_iterations_run_once_each_and_rows_are_tagged(self):
        stats, rows, _ = run_plan(plan_of(fake(), iterations=5, concurrency=2))
        self.assertEqual((stats.n, stats.ok, stats.err), (5, 5, 0))
        self.assertEqual(sorted(r.id for r in rows), [f"s0.i{i}/ok" for i in range(5)])

    def test_concurrency_is_bounded_and_reached(self):
        seen = {"now": 0, "max": 0}

        async def slow(ctx, i):
            seen["now"] += 1
            seen["max"] = max(seen["max"], seen["now"])
            await asyncio.sleep(0.05)
            seen["now"] -= 1
            return [sr.row("slow", "f", "x", "c", True, "status=200")]

        run_plan(plan_of(fake("slow", fn=slow), iterations=12, concurrency=4))
        self.assertEqual(seen["max"], 4)

    def test_duration_loop_stops_at_the_deadline(self):
        started = time.monotonic()
        stats, _, _ = run_plan(plan_of(fake(), iterations=0, duration=0.3, rate=20))
        self.assertGreaterEqual(time.monotonic() - started, 0.25)
        self.assertTrue(3 <= stats.n <= 10, stats.n)

    def test_rate_cap_spaces_the_starts(self):
        started = time.monotonic()
        run_plan(plan_of(fake(), iterations=5, concurrency=5, rate=20))
        self.assertGreaterEqual(time.monotonic() - started, 0.18)

    def test_ramp_staggers_the_workers(self):
        starts = []

        async def mark(ctx, i):
            starts.append(time.monotonic())
            await asyncio.sleep(0.5)
            return [sr.row("m", "f", "x", "c", True, "status=200")]

        t0 = time.monotonic()
        run_plan(plan_of(fake("m", fn=mark), iterations=4, concurrency=4, ramp=0.4))
        self.assertGreaterEqual(max(starts) - t0, 0.25)

    def test_timeout_and_exception_are_rows_not_crashes(self):
        async def hang(ctx, i):
            await asyncio.sleep(5)

        async def boom(ctx, i):
            raise ValueError("kaput")

        stats, rows, _ = run_plan(plan_of(fake("h", fn=hang), iterations=1, timeout=0.05))
        self.assertEqual((stats.timeouts, stats.err), (1, 1))
        self.assertIn("exceeded", rows[0].detail)
        stats, rows, _ = run_plan(plan_of(fake("b", fn=boom), iterations=1))
        self.assertEqual(stats.err, 1)
        self.assertIn("ValueError: kaput", rows[0].detail)

    def test_a_sync_driver_runs(self):
        def sync(ctx, i):
            return [sr.row("s", "f", "x", "c", True, "status=200")]

        self.assertEqual(run_plan(plan_of(fake("s", fn=sync), iterations=2))[0].ok, 2)

    def test_persona_pool_spreads_the_workers(self):
        personas = []

        async def who(ctx, i):
            personas.append(ctx.persona)
            await asyncio.sleep(0.02)
            return [sr.row("w", "f", "x", "c", True, "status=200")]

        run_plan(plan_of(fake("w", fn=who), iterations=6, concurrency=3), ctx=sr.Ctx(env={}, personas=["p1", "p2", "p3"]))
        self.assertEqual(set(personas), {"p1", "p2", "p3"})


class BudgetGuard(unittest.TestCase):
    def test_guard_counts_consecutive_bad_statuses_only(self):
        g = sr.Guard(3, 10)
        for status in (429, 200, 500, 429):
            g.record(status)
        self.assertFalse(g.tripped)
        g.record(429)
        self.assertTrue(g.tripped)
        self.assertIn("3 consecutive", g.reason)

    def test_guard_total_429_cap(self):
        g = sr.Guard(99, 2)
        g.record(429)
        g.record(200)
        g.record(429)
        self.assertTrue(g.tripped)
        self.assertIn("429", g.reason)

    def test_a_timeout_counts_as_bad(self):
        g = sr.Guard(2, 10)
        g.record(None, timed_out=True)
        g.record(None, timed_out=True)
        self.assertTrue(g.tripped)

    def test_the_driver_stops_when_the_guard_trips(self):
        async def limited(ctx, i):
            return [sr.row("l", "f", "x", "c", False, "status=429 quota")]

        stats, _, guard = run_plan(plan_of(fake("l", fn=limited), iterations=50, concurrency=1), guard=sr.Guard(3, 10))
        self.assertTrue(guard.tripped)
        self.assertEqual(stats.n, 3)
        self.assertEqual(stats.c429, 3)

    def test_token_cap_stops_the_run(self):
        async def spend(ctx, i):
            ctx.add_tokens(60)
            return [sr.row("t", "f", "x", "c", True, "status=200")]

        ctx = sr.Ctx(env={})
        ctx.max_tokens = 100
        stats, _, _ = run_plan(plan_of(fake("t", fn=spend), iterations=20), ctx=ctx)
        self.assertEqual(stats.n, 2)
        self.assertTrue(ctx.token_budget_spent)

    def test_run_all_reports_a_tripped_guard_and_skips_after_the_token_cap(self):
        async def limited(ctx, i):
            ctx.add_tokens(10)
            return [sr.row("l", "f", "x", "c", False, "status=429")]

        emitted = []
        profile = {"name": "t", "defaults": {"iterations": 10}, "budget": {"max_consecutive_failures": 2, "max_tokens": 15}}
        plans = [plan_of(fake("l", fn=limited), iterations=10), plan_of(fake("after"), iterations=3)]
        rows = asyncio.run(sr.run_all(plans, sr.Ctx(env={}), profile, {}, 0, 1, emit=emitted.append))
        ids = [(r.agent, r.id.split("/")[-1]) for r in rows]
        self.assertIn(("l", "budget-guard"), ids)
        self.assertIn(("after", "token-budget"), ids)
        self.assertTrue(any(r.layer == sr.SUMMARY_LAYER and r.agent == "l" and not r.passed for r in rows))
        self.assertTrue(emitted)


class Samplers(unittest.TestCase):
    """WP-309: a sampler is a measurement beside the load, reported once at the end."""

    def sampler(self, finish=None, run=None, interval=0.03):
        async def sample(ctx, i):
            return {"n": i}

        return sr.Driver(id="sat", family="saturation", run=run or sample, sampler=True, interval=interval,
                         finish=finish if finish is not None else (lambda ctx, samples: [sr.row("sat", "saturation", "count", "saturation", True, f"samples={len(samples)}")]))

    def slow_load(self, seconds=0.25):
        async def run(ctx, i):
            await asyncio.sleep(seconds)
            return [sr.row("load", "f", "x", "c", True, "status=200")]

        return fake("load", fn=run)

    def run_all(self, plans, shard=0, shards=1):
        emitted = []
        rows = asyncio.run(sr.run_all(plans, sr.Ctx(env={}), {"name": "t"}, {}, shard, shards, emit=emitted.append))
        return rows, emitted

    def test_the_sampler_runs_beside_the_load_and_reports_once(self):
        rows, _ = self.run_all([plan_of(self.sampler()), plan_of(self.slow_load(), iterations=1)])
        count = next(r for r in rows if r.id.endswith("count"))
        n = int(count.detail.split("=")[1])
        self.assertTrue(4 <= n <= 14, n)  # one at once, one every 30 ms for 250 ms, one at the end
        self.assertEqual([r.agent for r in rows if r.layer == sr.SUMMARY_LAYER], ["load"])  # no load summary for a sampler

    def test_a_run_of_only_a_sampler_still_samples_twice(self):
        rows, _ = self.run_all([plan_of(self.sampler())])
        self.assertGreaterEqual(int(rows[0].detail.split("=")[1]), 2)

    def test_only_shard_zero_samples(self):
        rows, _ = self.run_all([plan_of(self.sampler()), plan_of(self.slow_load(0.05), iterations=1)], shard=1, shards=2)
        self.assertFalse([r for r in rows if r.agent == "sat"])

    def test_a_failing_sample_is_kept_as_a_sample_not_a_crash(self):
        seen = {}

        def finish(ctx, samples):
            seen["errors"] = [s for s in samples if isinstance(s, Exception)]
            return [sr.row("sat", "saturation", "count", "saturation", False, f"errors={len(seen['errors'])}")]

        async def boom(ctx, i):
            raise ValueError("thanos down")

        rows, _ = self.run_all([plan_of(self.sampler(finish=finish, run=boom))])
        self.assertTrue(seen["errors"] and "thanos down" in str(seen["errors"][0]))
        self.assertFalse(rows[0].passed)

    def test_a_sampler_without_finish_or_with_a_broken_one_is_a_failing_row(self):
        rows, _ = self.run_all([plan_of(sr.Driver(id="sat", family="saturation", run=lambda ctx, i: {}, sampler=True, interval=0.02))])
        self.assertIn("finish", rows[0].detail)
        def bad(ctx, samples):
            raise RuntimeError("kaput")
        rows, _ = self.run_all([plan_of(self.sampler(finish=bad))])
        self.assertIn("RuntimeError: kaput", rows[0].detail)

    def test_a_sync_sampler_works(self):
        rows, _ = self.run_all([plan_of(self.sampler(run=lambda ctx, i: {"n": i}))])
        self.assertTrue(rows[0].passed)

    def test_a_profile_may_name_the_persona_pool(self):
        seen = {}

        async def fake_run_all(plans, ctx, *a, **k):
            seen["personas"] = ctx.personas
            return []

        with mock.patch.object(sr, "run_all", fake_run_all):
            sr.main(["--dir", str(STRESS_DIR), "--profile", "aggressive"])
            self.assertEqual(seen["personas"], [f"stress-load-{n:02d}" for n in range(1, 9)])
            with mock.patch.dict("os.environ", {"STRESS_OVERRIDES": '{"personas": ["p9"]}'}):
                sr.main(["--dir", str(STRESS_DIR), "--profile", "aggressive"])
            self.assertEqual(seen["personas"], ["p9"])
            sr.main(["--dir", str(STRESS_DIR), "--profile", "smoke"])
            self.assertEqual(seen["personas"], ["stress-consultant-01"])


class LoadDriversTwice(unittest.TestCase):
    def test_loading_the_same_directory_twice_keeps_the_first_modules_and_registrations(self):
        """Every test file loads the drivers: a second load must not replace the registered functions, or a test that
        patches the module it imported first would patch something the registry no longer calls."""
        module = sys.modules["driver_tools"]
        function = sr.REGISTRY["mcp-tools-by-group"].run
        names = sr.load_drivers(STRESS_DIR)
        self.assertIn("driver_tools.py", names)
        self.assertIs(sys.modules["driver_tools"], module)
        self.assertIs(sr.REGISTRY["mcp-tools-by-group"].run, function)


class Summaries(unittest.TestCase):
    def test_percentile_is_nearest_rank(self):
        self.assertEqual(sr.percentile([], 50), 0.0)
        self.assertEqual(sr.percentile([5], 99), 5)
        values = list(range(1, 101))
        self.assertEqual((sr.percentile(values, 50), sr.percentile(values, 95), sr.percentile(values, 99)), (50, 95, 99))

    def test_summary_row_carries_stats_and_merges_across_shards(self):
        d = fake("a")
        rows = []
        for shard, lat in enumerate(([100.0, 200.0], [300.0, 400.0, 500.0])):
            stats = sr.Stats(n=len(lat), ok=len(lat) - shard, err=shard, c429=shard, lat=lat)
            rows.append(vars(sr.summary_row(d, stats, sr.Guard(3, 10), shard, 2, "5 iteration(s)")))
        self.assertIn("p95=", rows[0]["detail"])
        merged = sr.merge_summaries(rows)
        self.assertEqual(len(merged), 1)
        m = merged[0]
        self.assertEqual((m["n"], m["ok"], m["err"], m["c429"], m["shards"]), (5, 4, 1, 1, 2))
        self.assertEqual(m["p50"], 300)
        self.assertIn("a", sr.render_table(merged))

    def test_summarize_cli_reads_json_lines(self):
        import io
        import contextlib

        d = fake("a")
        line = json.dumps([vars(sr.summary_row(d, sr.Stats(n=1, ok=1, lat=[10.0]), sr.Guard(3, 10), 0, 1, "1"))])
        path = pathlib.Path("/tmp") / f"stress-summ-{time.time_ns()}.json"
        path.write_text("noise\n" + line + "\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(sr.main(["--summarize", str(path)]), 0)
        path.unlink()
        self.assertIn("driver", out.getvalue())
        self.assertIn("\na ", out.getvalue())

    def test_unknown_profile_exits_2(self):
        self.assertEqual(sr.main(["--dir", str(STRESS_DIR), "--profile", "nope"]), 2)


class ContextTagging(unittest.TestCase):
    def test_request_id_and_traffic_header(self):
        ctx = sr.Ctx(env={}, run_id="r1")
        self.assertEqual(ctx.request_id("d", 3), "st-r1-d-3")
        self.assertEqual(ctx.trace_headers("d", 3, "arkos"), {"X-Zuno-Request-Id": "st-r1-d-3-arkos", "X-Zuno-Traffic": "stresstest"})

    def test_token_is_cached_and_signs_in_as_the_stresstest_client(self):
        calls = []

        def handler(request):
            calls.append(request.content.decode())
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 300})

        ctx = sr.Ctx(env={"KEYCLOAK_URL": "https://kc", "EVAL_CLIENT_ID": "zuno-stresstest", "EVAL_CLIENT_SECRET": "s",
                          "DEMO_PERSONA_PASSWORD": "pw"}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

        async def go():
            return await ctx.token("stress-consultant-01"), await ctx.token("stress-consultant-01")

        self.assertEqual(asyncio.run(go()), ("tok", "tok"))
        self.assertEqual(len(calls), 1)
        self.assertIn("client_id=zuno-stresstest", calls[0])
        self.assertIn("username=stress-consultant-01", calls[0])

    def test_token_refusal_names_the_status(self):
        ctx = sr.Ctx(env={"KEYCLOAK_URL": "https://kc"}, client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
        with self.assertRaises(RuntimeError) as cm:
            asyncio.run(ctx.token("p"))
        self.assertIn("status=401", str(cm.exception))


def gateway(handler):
    """A Ctx whose token endpoint always answers and whose other calls go to `handler`."""
    def route(request):
        if "openid-connect/token" in request.url.path:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
        return handler(request)

    return sr.Ctx(env={"KEYCLOAK_URL": "https://kc"}, run_id="t", client=httpx.AsyncClient(transport=httpx.MockTransport(route)))


def one(driver_id, ctx):
    wctx = ctx.for_worker(0)
    return asyncio.run(sr.REGISTRY[driver_id].run(wctx, 0))


class Drivers(unittest.TestCase):
    def test_the_three_first_drivers_are_registered_with_demo_ids(self):
        for demo in ("mcp-tools-by-group", "ai-gateway-routing", "ai-gateway-sovereignty"):
            self.assertIn(demo, sr.REGISTRY)
            self.assertTrue((REPO / "ansible" / "demos" / demo / "demo.yml").is_file(), demo)

    def test_tools_driver_passes_on_a_page(self):
        seen = {}

        def handler(request):
            seen["headers"] = dict(request.headers)
            seen["path"] = request.url.path
            return httpx.Response(200, json={"mcp_server": "confluence", "duration_ms": 12, "result": {"results": [{"id": 1}]}})

        rows = one("mcp-tools-by-group", gateway(handler))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].passed, rows[0].detail)
        self.assertEqual(seen["path"], "/v1/tools/search_confluence/invoke")
        self.assertEqual(seen["headers"]["x-zuno-traffic"], "stresstest")
        self.assertEqual(seen["headers"]["x-zuno-request-id"], "st-t-mcp-tools-by-group-0")
        self.assertIn("status=200", rows[0].detail)

    def test_tools_driver_fails_with_the_status_on_a_refusal(self):
        rows = one("mcp-tools-by-group", gateway(lambda r: httpx.Response(403, text="denied")))
        self.assertFalse(rows[0].passed)
        self.assertIn("status=403", rows[0].detail)
        self.assertEqual(sr.row_status(rows[0]), 403)

    def chat(self, status=200, content="ok", tokens=20):
        def handler(request):
            if "routing-decisions" in request.url.path:
                return httpx.Response(200, json={"provider": "local-maas", "model": "m", "kind": "local", "classification": "C3"})
            if status != 200:
                return httpx.Response(status, text="quota_exceeded")
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {"total_tokens": tokens}})

        return handler

    def test_routing_driver_reads_the_decision_and_reports_tokens(self):
        ctx = gateway(self.chat())
        rows = one("ai-gateway-routing", ctx)
        self.assertTrue(rows[0].passed, rows[0].detail)
        self.assertIn("provider=local-maas", rows[0].detail)
        self.assertEqual(ctx.tokens_used, 20)

    def test_routing_driver_sends_the_stresstest_class(self):
        seen = []
        ctx = gateway(lambda r: (seen.append(dict(r.headers)), self.chat()(r))[1])
        one("ai-gateway-routing", ctx)
        self.assertEqual(seen[0]["x-zuno-quota-class"], "stresstest")
        self.assertEqual(seen[0]["x-zuno-agent"], "open-webui")

    def test_routing_driver_fails_on_429_and_empty_answers(self):
        rows = one("ai-gateway-routing", gateway(self.chat(status=429)))
        self.assertFalse(rows[0].passed)
        self.assertEqual(sr.row_status(rows[0]), 429)
        self.assertFalse(one("ai-gateway-routing", gateway(self.chat(content="  ")))[0].passed)

    def test_sovereignty_driver_passes_when_arkos_stays_local_at_c3(self):
        ctx = gateway(self.chat())
        rows = one("ai-gateway-sovereignty", ctx)
        self.assertTrue(rows[0].passed, rows[0].detail)
        self.assertEqual(ctx.tokens_used, 40)

    def test_sovereignty_driver_fails_when_the_gateway_refuses(self):
        rows = one("ai-gateway-sovereignty", gateway(self.chat(status=429)))
        self.assertFalse(rows[0].passed)
        self.assertEqual(sr.row_status(rows[0]), 429)

    def test_a_guard_stops_a_driver_that_keeps_getting_429(self):
        ctx = gateway(self.chat(status=429))
        stats, _, guard = run_plan(plan_of(sr.REGISTRY["ai-gateway-routing"], iterations=20), guard=sr.Guard(2, 10), ctx=ctx)
        self.assertEqual(stats.n, 2)
        self.assertTrue(guard.tripped)


class Cli(unittest.TestCase):
    def test_list_and_dry_run(self):
        import io
        import contextlib

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(sr.main(["--dir", str(STRESS_DIR), "--list"]), 0)
            self.assertEqual(sr.main(["--dir", str(STRESS_DIR), "--dry-run", "--profile", "smoke"]), 0)
        text = out.getvalue()
        self.assertIn("ai-gateway-sovereignty", text)
        expected = len(sr.build_plan(sr.load_profile("smoke", STRESS_DIR), {}, sr.REGISTRY)[0])
        self.assertIn(f"profile=smoke shard=0/1 drivers={expected}", text)


class SignIn(unittest.TestCase):
    """The shared blocking sign-in helpers: one sign-in per persona, one retry after a pause."""

    def test_retries_once_then_raises(self):
        calls, pauses = [], []

        def refused():
            calls.append(1)
            raise RuntimeError("refused")
        with self.assertRaises(RuntimeError):
            sr.retry_signin(refused, attempts=2, backoff=5, sleep=pauses.append, jitter=lambda: 0.0)
        self.assertEqual((len(calls), pauses), (2, [5]))

    def test_second_attempt_can_succeed(self):
        state = {"n": 0}

        def flaky():
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("bounced")
            return "token"
        self.assertEqual(sr.retry_signin(flaky, sleep=lambda s: None, jitter=lambda: 0.0), "token")

    def test_concurrent_callers_share_one_sign_in(self):
        import threading
        import time as _t
        cache, calls = {}, []

        def slow():
            calls.append(1)
            _t.sleep(0.05)
            return "tok"
        out = []
        threads = [threading.Thread(target=lambda: out.append(sr.cached_signin(cache, ("p", "c"), 60, slow))) for _ in range(6)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual((out, len(calls)), (["tok"] * 6, 1))

    def test_expired_entry_signs_in_again(self):
        cache = {("p",): ("old", 5.0)}
        self.assertEqual(sr.cached_signin(cache, ("p",), 60, lambda: "new", now=lambda: 10.0), "new")


if __name__ == "__main__":
    unittest.main()
