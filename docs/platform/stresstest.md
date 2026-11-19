# Running the stresstest

[ADR-0624](../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md) (work packages WP-305 to
WP-313). The Day 3 stresstest is a **campaign** of drivers that replay the demo scenarios, combined by a named profile,
run as in-cluster Jobs under their own identity and budget. It extends the per-agent stresstest of
[ADR-0058](../adr/0058-aggregate-existing-test-content-into-a-bulk-interaction-stresstest.md) and
[ADR-0555](../adr/0555-parallel-and-quota-exhaustive-day3-stresstest.md), which stay as the `agents` family. It is
informational: it never feeds a deployment or a release gate, it runs only on demand, and every live campaign needs the
owner's go and a notice to the cluster session.

Status when this page was written (2026-11-19): the repository work of WP-305 to WP-313 is in review; the live proofs
(smoke run through `make` and through AAP, isolation of the budgets, chaos) are still to be made with the owner's go.
Read the state of each work package in [the roadmap](../roadmap/implementation-roadmap.md) before relying on a part of
this page.

## What a campaign is

- **A driver** replays one demo scenario's real calls (the golden-path moment, its API calls, its read-only state
  checks) over in-cluster HTTP with Keycloak tokens, without `oc`. It returns rows in the shape of
  `platform/testing/day2_report.py`. Drivers are `evaluations/stress/driver_*.py`; the demo they replay is named by the
  driver id (a bare id is the golden moment, `<id>-state` the state check, `load-*` the load drivers). The table of
  [stress and coverage](../demo/README.md#stress-and-coverage) lists them.
- **A family** groups drivers: `agents` (the per-agent Jobs of ADR-0555), `tools`, `models`, `unifai`, `guardrails`,
  `experiences`, `state`, `load`, `saturation` (a sampler: vLLM queue and KV cache, gateway p95, Postgres backends) and
  `counters` (a sampler of the Limitador counters). `quota` (the `quotas` driver) spends a persona's budget until a 429
  and is in no profile. `chaos` is not a family: it is the disruptions of the `aggressive` profile, below.
- **A campaign** is one Indexed Job `zuno-stress-<profile>-<stamp>` (for example `zuno-stress-smoke-20261119-143000`),
  one pod per shard, with a deadline and a TTL of one day, launched the same way from `make` and from AAP. The runner is
  `platform/testing/stress_runner.py`; the drivers and profiles travel in the ConfigMap `zuno-stress-scripts`, rebuilt
  from the repository at every launch. The runner exits 0 whatever the rows say: a failing driver is a row, never a
  crash.
- **A budget guard** protects the shared model budgets: a driver stops after `max_consecutive_failures` consecutive
  429 or 5xx answers (or timeouts), after `max_429` rejected calls, and the run stops once the drivers reported
  `max_tokens` tokens. A tripped guard is a failing row that says so.

## The four profiles

Defined in `evaluations/stress/profile_<name>.yaml` (first values, to be tuned after the first live runs).

| Profile | Families | Rate and size | Budget guard | Deadline |
|---|---|---|---|---|
| `smoke` | tools, models, unifai, guardrails | each driver once, concurrency 1, 1 shard | 2 failures in a row, 2 x 429, 1,500 tokens | 15 min, waits |
| `standard` | agents, tools, models, unifai, guardrails, experiences, state, saturation, counters | 3 iterations at concurrency 2 (the experience drivers 2 iterations at concurrency 1), state once | 3 in a row, 5 x 429, 20,000 tokens | 45 min, waits, with the dashboard coverage |
| `aggressive` | the standard families plus `load` | the load pool of 8 personas, 60 iterations at concurrency 8 with a 60 s ramp, 2 shards; `load-ai-gateway` and `load-mcp-gateway` 400 iterations, `load-unifai-scenarios` 40 at concurrency 4 | 5 in a row, 20 x 429, 100,000 tokens | 60 min, waits, with the coverage |
| `soak` | tools, models, saturation, counters | about 2 requests a minute per driver for 4 hours (`rate` 0.033, `duration` 14400) | 5 in a row, 30 x 429, 300,000 tokens | 4 h 20 min, asynchronous: it prints a run id |

`smoke` is the first thing to run after any roll. `aggressive` lists six disruptions (see [Chaos](#chaos)); they run
only when the operator types the profile name again.

## Launch

From a workstation logged in to the cluster:

```sh
make d3 stresstest PROFILE=smoke
make d3 stresstest PROFILE=standard CONCURRENCY=4 FAMILIES=tools,models
make d3 stresstest PROFILE=soak                       # asynchronous: prints the run id
make d3 stresstest PROFILE=aggressive CHAOS_CONFIRM=aggressive   # load AND disruptions
make d3 stresstest-collect RUN=soak-20261119-014500   # read one campaign (default: the newest)
```

Overrides, all optional: `ITERATIONS`, `CONCURRENCY`, `DURATION` (seconds), `SHARDS`, `FAMILIES` (comma list),
`DRIVERS` (comma list of driver ids). Without `PROFILE=`, `make d3 stresstest` runs the older per-agent stresstest
(`BULK`, `CLEANUP`, `SEQUENTIAL`). `CHAOS_CONFIRM=<the profile name again>` is the only way to inflict disruptions:
without it a profile that lists them runs its load and nothing else.

Through AAP: the Job Template `zuno-day3-stresstest` (gated by the launch RBAC of WP-103, credential
`zuno-aap-installer`) takes the same values as extra variables: `stress_profile`, `stress_iterations`,
`stress_concurrency`, `stress_duration`, `stress_shards`, `stress_families`, `stress_drivers`, `stress_chaos_confirm` (the profile name again, for the
disruptions), and `stress_wait` to wait or not. The Template `zuno-day3-stresstest-collect` (read-only, credential `zuno-cluster-reader`) takes the run id.
The launch is asynchronous, so the AAP job ends when the Job is created unless the profile or `stress_wait` asks to
wait.

## What the switches of the cluster do

These are in `ansible/clusters/demo333.yml` (each is the owner's decision, 2026-11-19) and in the roles that read them.

| Switch | Effect |
|---|---|
| `zuno_ai_gateway_stress_credentials: true` | The ai-gateway chooses its MaaS credential by quota class. The classes `stresstest` and `loadtest` reach MaaS with the ServiceAccount `zuno-ai-run/ai-gateway-stress` and its own `<model>-load` MaaSSubscriptions (models chart, `altGatewayPeers.stress`), never with the ai-gateway's own ServiceAccount, whose budget Open WebUI, Dify, kagent, OpenClaw and the acceptance gate share. Needs the ai-gateway image built from 01079893 or later |
| `zuno_ai_gateway_quota_loadtest_group: zuno-loadtest` | Members of the Keycloak group `/zuno-loadtest` run in the quota class `loadtest`. Inert until an admitted agents release defines the class in `policies/quotas/quota-policy.yaml` |
| `zuno_stress_clients_enabled: true` | The Dify and kagent token proxies admit the stress Job's pods, so the Job can replay those clients' path |
| `zuno_stress_reader_enabled: true` | The Job runs as the ServiceAccount `zuno-stress-reader` (namespaces chart, `stressReader`): get-only on the objects the demos' state checks name, generated from the demos' own lists, no Secret, no write. Without it the Job runs as `acceptance-gate` and every state row fails with `status=403` and says what to enable |
| `zuno_stress_reader_monitoring_view: true` | Adds the built-in `cluster-monitoring-view` to that ServiceAccount, for the `saturation` and `counters` samplers |
| `chaosRbac.enabled` (chart `aap-config`, default off) | Gives the AAP execution identity the cluster role the disruptions need: delete one pod of the listed applications, create and delete an AdminNetworkPolicy. Needed to run `aggressive` with chaos through AAP; from `make`, your own login does it. The variable that sets it from `ansible/clusters/` was not found in the repository when this page was written |

## Identities and budgets

- **`stress-consultant-01`**: the default persona of the runner (`STRESS_PERSONAS`), a copy of consultant-01 in
  `/zuno-evaluation`, signed in through the confidential client `zuno-stresstest`. Quota class `stresstest`
  (a cap, not a load: it proves a limit).
- **`stress-load-01` to `stress-load-08`**: the load pool, in `/zuno-evaluation` and in `/zuno-loadtest`. A budget is
  keyed by persona (WP-190), so a concurrency of N wants N personas. They exist after the Keycloak personas Job has
  run; without it each worker fails to sign in. Quota class `loadtest`.
- **`ai-gateway-stress`** and the `<model>-load` subscriptions: the MaaS side of both classes, with its own limit
  (200,000 tokens an hour per model in the work package's proposal; the numbers are the owner's decision). The traffic
  carries `X-Zuno-Traffic: stresstest`, recorded as the span attribute `zuno.traffic` on `model_call`, `guardrails_observe`
  and `tool_invoke` (search `{ span.zuno.traffic = "stresstest" }` in Tempo). It is never a metric label or an authorization
  input.
- **Praxis caveat.** Praxis is a second MaaS consumer with its own ServiceAccount and subscriptions, and it injects
  its own credential whatever token the caller sends. Stress traffic through Praxis (`claude-code-sovereign`)
  therefore spends the Praxis budget, not the stress one. Those drivers stay at one request at a time behind the guard.
- **Experience drivers** (Open WebUI, Dify, kagent, Blender, Claude Code) ride the experience clients' own shared
  budgets on purpose: they are the real user paths.

## Reading the report

`make d3 stresstest-collect` (or the AAP Template) reads the rows of the Job's pods and prints, in this order:

1. **The header**: run id, profile, state of the Job, rows, and a verdict, `CLEAN` or `ATTENTION` (any failure, tripped guard, saturated signal, failing counter or chaos row), which is informational.
2. **The per-driver table**: n, ok, err, 429, 5xx, p50, p95, p99 and whether the guard tripped.
3. **BUDGET GUARD**: which driver stopped and why.
4. **FAILURES**: each failing row with its driver, id and detail (the first ones, then a count).
5. **SATURATION**: one row per signal of the `saturation` sampler (vLLM queue and KV cache, gateway p95, Postgres
   backends): `ok` or `SATURATED`.
6. **LIMITADOR COUNTERS**: which Limitador counters moved during the run and under which identity. The isolation proof
   is the pair of rows for `system:serviceaccount:zuno-ai-run:ai-gateway-stress` (it moves) and
   `...:ai-gateway` (it does not move because of this run; it moves with every other caller's traffic, and the row says
   so). A limit with no counter is reported as "no counter", not zero.
7. **CHAOS**: for each disruption, `recovered` or `DID NOT RECOVER`, with the effect on the load.
8. **TREND**: the previous run of the same profile, read from `evaluations/day2-reports/stress/` (the file of each run
   is saved there): p95 and error rate before and after, `REGRESSED` when p95 is above 1.5 times the previous run's or the error rate is 5 points higher.

`-e stress_evidence=true` (AAP: the extra variable) also writes `docs/roadmap/evidence/stress-<run id>.md` for a person
to review and commit. Every run id is stamped on the request ids (`st-<run>-<driver>-<n>`), so a row can be found in
Tempo. The Job's TTL is one day: collect before it expires.

## Chaos

`evaluations/stress/chaos.yaml` is a closed list, checked by `platform/testing/stress_chaos.py validate`. Two kinds
only: delete **one** pod of a named application, or deny the addresses of **one** external provider to the ai-gateway
pods for a bounded time with an AdminNetworkPolicy that is deleted at the end whatever happens. The `aggressive`
profile lists `pod-ai-gateway`, `pod-mcp-gateway`, `pod-praxis`, `provider-cut-mistral` (two minutes, `zuno-code`
must fall back), `pod-a2a-gateway` and `pod-open-webui`; the first starts 5 minutes into the run, then one every 150
seconds after the previous one ends. GPU model pods and nodes are never disrupted by the stresstest: the node failover
drill stays [ADR-0536](../adr/0536-live-node-failover-drill-for-qwen-model-fallback.md). A selector marked
`labels_checked: false` was written from the chart and not yet seen on a live pod; when it matches nothing the row
fails and says so, it never guesses another one.

## Cost, and what not to do

- A campaign spends real model budget and real GPU time. `smoke` is capped at 1,500 tokens; `aggressive` at 100,000.
- **Never run `aggressive`, or any campaign that spends shared budgets, during an announced demo or a freeze window**
  ([freeze protocol](../demo/freeze-protocol.md)): it deletes pods and cuts a provider on purpose.
- **Never run `make d2 check agents` right after a stresstest**: see
  [agents release integration](agents-release-integration.md#rolling-a-promotion).
- **The drain of 2026-11-19** is why the identities exist. The run of 00:21 to 00:49 UTC, sharing the ai-gateway's MaaS
  ServiceAccount, used its budget of 1,000,000 tokens an hour per route: Open WebUI, Dify, kagent, OpenClaw and the
  acceptance gate got HTTP 429 until about 01:22 UTC. Read the isolation rows of the first campaign after a roll before
  trusting the separation.
- **The Keycloak brute-force lock.** The realm temporarily locks an account after 30 failures (60 s steps, 15 minutes
  at most, never permanent). A wrong persona password in a load pool of eight personas locks them quickly and every
  later row then fails to sign in: check the password variable first, then wait.
- Tell the cluster session before a live campaign, and keep the Job's name: it is the only handle for collecting.

## Known limits

- **Limitador does not count the `-load` limits yet** (reported by the cluster session on 2026-11-19; not yet written
  in the repository's evidence): the Kuadrant EnvoyFilter of the `maas-default-gateway` has been stale since
  2026-11-05, so the MaaS side of the isolation proof reads "no counter" for the stress ServiceAccount. The fix is
  pending the owner's go. The `<model>-load` subscriptions were renamed from `<model>-stress` because the wasm shim
  never creates a counter for the last token-limit action of a route, ordered by limit name.
- The drivers of `multi-gateway` and `agents-alt-gateway` stay pending until their clients exist (Phase 58, WP-297 to
  WP-303); their state rows say so.
- OpenClaw and Lightspeed are not replayed from a Job (OpenClaw's path is the operator's egress proxy inside each
  persona's pod; Lightspeed needs an OpenShift token). The world model has no driver.
- The experience and workstation drivers need openings of the egress firewall and the NetworkPolicies (WP-308); until
  they exist the row carries the connection error, which is the honest answer.
- Until the Mistral Codestral key is renewed, the C1 code path falls back to a local model; the report counts it as a
  known state ([key rotation](saas-provider-key-rotation.md)).
- The profile values are first values, tuned after the first runs.
