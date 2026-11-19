# ADR-0624: Drive the Day 3 stresstest from scenario drivers and named profiles

- **Status:** Accepted
- **Target:** v0.17
- **Date:** 2026-11-19
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0058](0058-aggregate-existing-test-content-into-a-bulk-interaction-stresstest.md) (the informational
  stresstest), [ADR-0555](0555-parallel-and-quota-exhaustive-day3-stresstest.md) (parallel per-agent Jobs and quota
  proofs)
- **Related:** [ADR-0057](0057-introduce-day-2-agent-availability-test-and-stresstest-operations.md),
  [ADR-0536](0536-live-node-failover-drill-for-qwen-model-fallback.md), [ADR-0605](0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md),
  [ADR-0616](0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)

## Context

The stresstest run of 2026-11-19 00:21-00:49 UTC (`make d3 stresstest all`, devel 935cbffe) passed 134 of 142 agent
checks and 32 of 36 rows of the dashboard coverage pack (evaluations/dashboard_coverage.py). It showed that the
stresstest exercises the UnifAI agents and the two governed gateways, but not the rest of the platform, and that it can
hurt the users it shares budgets with.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | Every call is sequential: one Job per agent, `day2_bulk.py` loops one session at a time. No load, chaos or soak test exists. | platform/testing/day2_bulk.py, ansible/roles/day3/tasks/stresstest_job*.yml |
| F2 | The run drained the MaaS budget of the ai-gateway ServiceAccount (1,000,000 tokens per hour per model route, one Limitador counter shared by every ai-gateway caller); Open WebUI, Dify, kagent, OpenClaw and `make d2 check agents` got HTTP 429 until about 01:22 UTC. | Limitador counters of gpt-oss-20b-kserve-route read 2026-11-19 00:49 UTC |
| F3 | The ai-gateway quota class `stresstest` (2,000 tokens per 5 minutes per user, fail-closed) proves a cap; it cannot carry load and does not isolate the MaaS budget. | policies/quotas/quota-policy.yaml |
| F4 | Of the 39 demo ids in ansible/demos, about 15 have a golden-path probe; the others have read-only steps or nothing replayable. The probes use `oc exec` and port-forwards, so they cannot run in a Job; their `judge_*` functions are pure. | ansible/demos/<id>/demo.yml `probes:`, evaluations/golden_path_probe.py |
| F5 | The AAP execution environment has no `oc` and no httpx; the coverage pack prints "cannot reach the cluster" there. | ansible/roles/day3/tasks/stresstest_coverage.yml |
| F6 | Load cannot be judged: no GPU utilisation under MIG, no Limitador per-limit counters, no Authorino metrics, counters that read zero after a restart. | Dashboard audit of 2026-11-19 |

## Decision

**The Day 3 stresstest becomes a campaign of scenario drivers, combined by named profiles, run as in-cluster Jobs under
its own identity and MaaS budget, and stays informational.**

1. **One driver per demo scenario.** A driver replays the scenario's real calls (the golden-path moment, its API calls,
   its read-only state checks) over in-cluster HTTP with Keycloak tokens, without `oc`, and returns rows in the
   `Day2Result` shape (platform/testing/day2_report.py). Drivers live in evaluations/stress/driver_*.py and reuse the
   probes' `judge_*` functions. Workstation clients (Blender, Claude Code) are replayed by their network path. A driver
   for a scenario that is not deployed (world model) ships disabled; the multi-gateway and agents-alt-gateway drivers
   stay pending until their clients exist (WP-297 to WP-303). WP-308, WP-310.
2. **Four families of stress.** `functional` (every driver once), `load` (concurrency, iterations or duration, ramp,
   rate cap), `chaos` (disruptions beside a load run), `soak` (a low steady rate for hours). WP-305, WP-309, WP-311,
   WP-312.
3. **Named profiles with overrides.** `smoke`, `standard`, `aggressive` and `soak` (evaluations/stress/profile_<name>.yaml) set
   families, drivers, iterations, concurrency, duration, rate, persona pool and chaos actions. Make variables
   `PROFILE`, `ITERATIONS`, `CONCURRENCY`, `DURATION`, `FAMILIES` and `DRIVERS` override them and travel as AAP extra
   variables. The existing per-agent Jobs become the family `agents`. WP-305, WP-307.
4. **In-cluster Jobs, launched the same way from make and AAP.** An indexed Job with a deadline and a TTL runs the
   runner (platform/testing/stress_runner.py); the launch is asynchronous and `make d3 stresstest-collect` reads the
   rows. This amends ADR-0555's 40-minute synchronous wait. WP-307.
5. **A dedicated identity and budget.** A quota class `loadtest`, a pool of stress personas, and a dedicated MaaS
   ServiceAccount with its own MaaSSubscription per model route (`<model>-load`; first named `<model>-stress`, renamed
   2026-11-19). The ai-gateway chooses its MaaS credential by quota
   class, so stresstest traffic never touches the ai-gateway ServiceAccount's counter (F2). Praxis is a second MaaS
   consumer with its own ServiceAccount and subscriptions: Praxis drivers sign in as stress personas and their MaaS
   traffic uses the dedicated identity as well. A runner budget guard stops
   a driver after a streak of 429 or 5xx answers. Calls carry `X-Zuno-Traffic: stresstest`, recorded as a span
   attribute. WP-306.
6. **Bounded chaos.** The `aggressive` profile may delete one pod at a time of the ai-gateway, mcp-gateway, a2a-gateway,
   Praxis and the experience UIs, and cut one external provider with an AdminNetworkPolicy Deny removed at the end.
   GPU model pods and nodes are never disrupted by the stresstest; the node failover drill stays ADR-0536. WP-311.
7. **Informational, as ADR-0058 states.** The campaign never feeds a deployment or release gate. Each campaign writes a
   report (per-driver count, errors, 429s, p50/p95/p99, coverage per dashboard family) and an evidence file. WP-312.
8. **On demand only.** No schedule. Every live campaign needs the owner's go and a notice to the cluster session.
9. **Observability prerequisites first.** Authorino scraped on `/server-metrics`, vLLM metric renames in the dashboards,
   a Limitador counter reader, zero-initialised counters, GPU utilisation under MIG. WP-313.

## Alternatives considered

- **A separate load tool (k6, Locust).** It would not reuse the scenario judges, the personas or the report, and it
  would drift from the demos.
- **Run the drivers in the AAP execution environment.** It has no `oc` and no httpx (F5); AAP only launches the Job.
- **Keep sharing the ai-gateway's MaaS identity with a smaller budget.** F2 shows any shared budget turns a stresstest
  into an outage for the users.

## Consequences

- A campaign stimulates every demo scenario, and the dashboards get data for every family.
- WP-306 changes the ai-gateway (credential choice by quota class), adds Kubernetes and Keycloak objects and needs a
  roll of the ai-gateway and mcp-gateway.
- Until the Mistral Codestral key is renewed (expired 2026-11-19), drivers of the C1 code path fall back to a local
  model; the report counts that as a known state, not a regression.
- The `aggressive` profile disturbs users on purpose; it runs only on the owner's go and never during an announced demo.

## Security considerations

The stress personas and the dedicated MaaS identity have their own credentials, kept in Vault and read by the Job from a
Secret, never on a command line. The traffic tag is a span attribute, not an authorization input. The chaos actions are
limited to the list in clause 6.

## Notes

- 2026-11-19, live finding (WP-306): the `<model>-load` limits are not counted by Limitador. The Kuadrant operator
  cannot write the EnvoyFilter `openshift-ingress/kuadrant-maas-default-gateway` any more: the desired wasm config is
  3.9 MB, over the 3 MiB API request limit ("Request entity too large"), so the data plane has served the config of
  2026-11-05 since then, while the TokenRateLimitPolicies report Enforced. Every MaaS subscription added after that
  date is not enforced. Clause 5's isolation holds (stress traffic never spends the ai-gateway ServiceAccount's
  counter, proven the same day); the stress budget is capped by the ai-gateway quota ledger until the filter fits.
