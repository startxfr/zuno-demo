# WP-309: Push the platform with concurrent load and read its saturation

- **State:** Repo work in review (2026-11-19, committed in the `wp306-coder` worktree on branch `wp308-coder`, not pushed); the live proof and the monitoring grant are the reviewer's, with the owner's go and a notice to zuno-demo-cluster
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)
- **Depends on:** [WP-305](wp-305-build-the-stress-runner-core-and-profiles.md), [WP-306](wp-306-give-the-stress-runs-their-own-identity-and-budget.md), [WP-307](wp-307-launch-the-stress-campaign-as-an-indexed-job.md), [WP-308](wp-308-replay-the-demo-scenarios-as-stress-drivers.md)
- **Related:** WP-311, WP-312, WP-313
- **Target:** v0.17
- **Estimated files touched:** ~8: the runner, one driver file, three profiles, the campaign launch task, the tests

## Goal

The aggressive profile pushes the platform with real concurrent load, and the run says where it saturates: which queue grew, which cache filled, which gateway slowed down, how many database connections it held.

## Steps

1. **Load drivers** (`evaluations/stress/driver_load.py`, family `load`):
   - `load-unifai-scenarios` replays the message-bearing scenarios of `evaluations/<agent>/scenarios.yaml` (the active agents, `STRESS_LOAD_AGENTS`, default tekos, arkos and comage; 46 KB of YAML for the six, shipped in the Job ConfigMap as `<agent>-scenarios.yaml`) as concurrent UnifAI turns, one fresh session each, round-robin and offset by worker. It replaces the sequential `day2_bulk.py` loop for campaigns; the per-agent Jobs and their `BULK=` pass are untouched;
   - `load-ai-gateway` posts chat completions straight on the ai-gateway Service with the same prompts;
   - `load-mcp-gateway` calls `search_confluence` through the REST path with varied queries.
   They ask for the quota class in `STRESS_QUOTA_CLASS` (`stress_quota_class` for make and AAP; default `stresstest`, the small fail-closed one; set `loadtest` once the policy of WP-306 defines it; empty sends no header and the persona's group decides).
2. **A sampler in the runner** (`platform/testing/stress_runner.py`): a driver registered with `sampler=True, finish=...` is a measurement, not a load. It is called at the start, every `interval` seconds beside the other drivers, and once at the end, on shard 0 only; its samples are not rows, and `finish(ctx, samples)` returns the final rows. An exception raised by a sample is kept and reported, never a crash.
3. **The `saturation` sampler** reads through Thanos, with the Job's own token (or `THANOS_TOKEN`), the series the dashboards plot: `vllm:num_requests_waiting`, `vllm:num_requests_running`, `vllm:kv_cache_usage_perc`, the p95 of `istio_request_duration_milliseconds_bucket` for the ai-gateway and the mcp-gateway at the sidecars, and `pg_stat_database_numbackends`. One row per signal: max, mean, the number of samples and `SATURATED (limit …)` when the max crossed its limit (4 waiting requests, 90 % of the KV cache, 10 s at the p95, 160 of the 200 Postgres connections: first values, tuned after the first runs). A signal with no series is a passing row that says so.
4. **Profiles**: `aggressive` adds `load` and `saturation` and names the persona pool of WP-306 (`personas: [stress-load-01 … 08]`, a profile may now carry it; an explicit override still wins), with a ramp and 400 calls at concurrency 8 on the two gateways and 40 UnifAI turns at concurrency 4 (a turn is a whole agent run, 300 s timeout). `standard` and `soak` add the sampler only. `smoke` is unchanged.

## Not done, and why

- **a2a-gateway load**: its caller contract is a signed agent chain over the A2A protocol, not a plain REST call; it needs a driver of its own with the chain headers, and the gateway is single replica by design (ADR-0101), so the number worth measuring is its p95 under the UnifAI load, which the sampler already reads at the sidecar.
- **MaaS direct per model**: the ai-gateway reaches MaaS with the stress class's own credential (WP-306): a driver holding a MaaS token would test a path no user takes. The per-route counters are read in Limitador.
- **Praxis chains and fallback**: Praxis is reachable only from the experience-client namespaces, and it injects its own credential, so load through it spends the Praxis budget. The Praxis drivers of WP-308 stay at one request at a time.

## Acceptance

Offline, done: `python3 evaluations/tests/test_stress_runner.py` (49: the sampler runs beside the load, reports once, samples on shard 0 only, survives a failing sample, a profile names its persona pool), `python3 evaluations/tests/test_stress_drivers.py` (44: the corpus and its round-robin, each load driver's request and verdict, the saturation signals and rows, the 401 and 403 refusals), `python3 platform/docs/check_docs.py`, the Ansible expression that ships the scenario files checked offline.

Live, with the owner's go, in this order:

1. Grant the Job's ServiceAccount the right to read Prometheus, which is a cluster-wide read the owner decides: `oc adm policy add-cluster-role-to-user cluster-monitoring-view -z acceptance-gate -n zuno-ai-run` (the sampler says so when Thanos answers 401 or 403).
2. The persona pool of WP-306 (the Keycloak Job has run) and, ideally, the `loadtest` class (WP-306's agents release).
3. `make d3 stresstest PROFILE=aggressive FAMILIES=load,saturation DRIVERS=load-ai-gateway,saturation CONCURRENCY=2 ITERATIONS=20` first, then widen. Read the table (`make d3 stresstest-collect`): the p95 and error columns of the load drivers, and the `saturation` rows for what moved.
4. Re-run the golden-path probes of Open WebUI, Dify and kagent during the run: none may answer 429 (the isolation of WP-306 under real load).

## Open points

- The saturation limits are guesses until a run shows where the models actually queue (qwen35-9b has `max-num-seqs=4`, so its queue starts at 4 concurrent turns).
- The p95 is read at the destination sidecar of the two gateways, which includes the model call; a per-model p95 needs the `model` label of `zuno_model_call_duration_ms` (WP-313).
