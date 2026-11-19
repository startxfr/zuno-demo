# WP-305: Build the stress runner core and the profiles

- **State:** Repo work in review (2026-11-19, committed locally, not pushed); the live proof is WP-307's smoke run, through make and AAP, with the owner's go
- **ADRs:** ADR-0624 (to be written by the reviewer: it extends ADR-0058 and ADR-0555)
- **Depends on:** none
- **Related:** WP-306, WP-307, WP-308, WP-309
- **Target:** v0.17
- **Estimated files touched:** ~10: platform/testing/stress_runner.py, evaluations/stress/ (3 drivers, 4 profiles), evaluations/tests/test_stress_runner.py

## Goal

A replayable scenario driver can be run at a tunable aggressiveness, and the run reports per driver what happened, without ever draining a shared model budget.

## Steps

1. `platform/testing/stress_runner.py`, one asyncio runner (httpx, no `oc`):
   - a driver registry: `@register(id, family, ...)` on `run(ctx, i) -> rows`, one driver per demo id (`ansible/demos/<id>`);
   - the plan: a profile, overridden by `STRESS_OVERRIDES` (iterations, concurrency, duration, rate, ramp, timeout, families, drivers, shards, personas, max_tokens), selects the drivers and the knobs of each;
   - the scheduler: iterations or a duration loop, a semaphore-free worker pool of `concurrency`, a rate cap, a ramp and a timeout per iteration; an exception or a timeout is a failing row;
   - sharding: an Indexed Job shard takes its share of the iterations and of the concurrency, and its own slice of the persona pool;
   - the budget guard: a driver stops after `max_consecutive_failures` consecutive 429/5xx/timeouts or `max_429` rejections, and the run stops once the drivers have reported `max_tokens` tokens.
2. Rows are `Day2Result` rows (platform/testing/day2_report.py), printed one JSON array per line so the existing collector reads them. The HTTP status of a call is written as `status=NNN` in the detail, which is what the guard and the report read. One summary row per driver and shard carries n, ok, err, 429, 5xx, p50/p95/p99 and the latencies; `--summarize` merges the shards into one table.
3. Requests carry `X-Zuno-Request-Id: st-<run>-<driver>-<n>` and `X-Zuno-Traffic: stresstest` (the gateways read the header in WP-306; until then it is ignored).
4. Profiles `evaluations/stress/profile_{smoke,standard,aggressive,soak}.yaml`: families, defaults, a `budget` block (the guard), a `job` block (deadline, wait). `smoke` is one call of each driver under a 1500-token cap.
5. Three first drivers, on the zuno-stresstest client and the stresstest quota class (a small, fail-closed budget): `mcp-tools-by-group` (search_confluence through the mcp-gateway REST path), `ai-gateway-routing` (a zuno-code call, routing decision read back), `ai-gateway-sovereignty` (Arkos kept local at C3, a Tekos control call). They reuse the golden-path judges (`judge_tool`, `judge_sovereignty`).
6. Offline unit tests: `python3 evaluations/tests/test_stress_runner.py` (plan, sharding, scheduler, guard, summaries, drivers against `httpx.MockTransport`).

## Acceptance

- `python3 evaluations/tests/test_stress_runner.py` passes; `python3 platform/docs/check_docs.py` passes.
- `python3 platform/testing/stress_runner.py --dir evaluations/stress --dry-run --profile aggressive` prints the plan of a shard.
- A driver that keeps getting 429 stops after the guard's limit and says so in a row; a run with `max_tokens` set stops at the cap.
- Live (WP-307): `make d3 stresstest PROFILE=smoke` returns one row per driver and leaves the ai-gateway ServiceAccount's MaaS counter unchanged.
- Not in this package: the dedicated identity and budget (WP-306), the other drivers (WP-308 to WP-310), chaos (WP-311), the soak report (WP-312). The lightspeed driver needs the OpenShift Lightspeed API's own auth from a Job (a ServiceAccount token with a role on the service) and moves to WP-308.
