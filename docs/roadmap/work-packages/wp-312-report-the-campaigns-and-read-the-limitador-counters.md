# WP-312: Report the campaigns and read the Limitador counters

- **State:** Repo work in review (2026-11-19, committed in the `wp306-coder` worktree on branch `wp312-coder`, stacked on WP-308 and WP-309, not pushed); the live reading of the counters is the reviewer's, with the owner's go
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)
- **Depends on:** [WP-307](wp-307-launch-the-stress-campaign-as-an-indexed-job.md), [WP-309](wp-309-push-the-platform-with-concurrent-load-and-read-its-saturation.md)
- **Related:** WP-306, WP-313
- **Target:** v0.17
- **Estimated files touched:** ~9: the report, the counters sampler, the collect task, the Job file set, the profiles, the tests

## Goal

A campaign ends with one report a person can read and compare: what ran, what failed and why, where the platform saturated, which Limitador counters moved under which identity, how this run differs from the previous one, and whether the dashboards filled. The report can be kept as evidence.

## Steps

1. **The report** (`platform/testing/stress_report.py`, stdlib only so it also runs in the AAP execution environment). It reads the rows a campaign printed and builds: the per-driver table merged over the shards (n, ok, err, error rate, 429, 5xx, p50/p95/p99, the guard that stopped a driver), the first failing rows, the budget-guard stops, the saturation rows of the sampler, the counter rows, and a verdict `CLEAN` or `ATTENTION` (a failing row, a guard, a saturated signal, a collection error). Informational: the exit code is always 0.
2. **The trend**: `--trend-dir` reads the newest earlier report of the same profile, compares the p95 and the error rate of each driver present in both (flagged `REGRESSED` above x1.5 on the p95 or +5 points of errors) and saves this run as `stress-<run id>.json`. The default directory is `evaluations/day2-reports/stress/` of the checkout: kept on a workstation, lost with an AAP job's checkout (the report still prints its own trend when the directory holds one).
3. **The evidence file**: `-e stress_evidence=true` (local runs) also writes `docs/roadmap/evidence/stress-<run id>.md`, for a person to review and commit; the tool never commits it. Under AAP the same markdown is available from `--format markdown`.
4. **The Limitador counters** (`evaluations/stress/driver_counters.py`, a sampler of family `counters`, WP-313 step 4). It reuses the reader of `platform/testing/quota_counters_probe.py` (WP-177: `GET /counters/<url-encoded namespace>`), discovers the namespaces from the `limitador_namespace` labels of Limitador's own `/metrics`, reads every namespace at the start, every minute and at the end, then reports which counters moved per identity and an `isolation` row: the stress ServiceAccount's tokens against the shared ai-gateway ServiceAccount's (which also carries every other caller's traffic). No counter at all is a failing row that names the wasm shim (it creates none for the last token limit of a route, ordered by limit name). URL: `LIMITADOR_URL`, default `http://limitador-limitador.kuadrant-system.svc:8080`; no NetworkPolicy of this repository blocks it, and when an installation does the row says to run the same read through a port-forward.
5. **The coverage as the last stage**: when the profile sets `job.coverage` (standard, aggressive, soak; `-e stress_coverage=true|false` overrides) the collect runs `evaluations/dashboard_coverage.py --check-only` over the campaign window (the Job's age plus ten minutes) after the report. It needs `oc` and httpx where it runs: a workstation does; the AAP execution environment prints one "cannot reach the cluster" row. It never fails the run.
6. `stresstest_campaign_collect.yml` calls the report instead of the plain table; the row-by-row render (every row up to 300, else the failures and the summaries) stays below it. The Job ConfigMap carries `quota_counters_probe.py`.

## Acceptance

Offline, done: `python3 evaluations/tests/test_stress_report.py` (25: the merge over shards, the sections, the cap on failures, the trend baseline and its flags, the CLI with and without files, a read-only directory never losing the report, no httpx needed, the counters sampler and the isolation row), the Ansible report chunk run offline with a fake Job and rows, `check_docs.py`.

Live, with the owner's go: `make d3 stresstest PROFILE=standard`, then `make d3 stresstest-collect`. The report shows the table, and `LIMITADOR COUNTERS` shows `ai-gateway-stress` moving while the shared ServiceAccount's line is the other callers' traffic; the second run shows a `TREND` block against the first. If `LIMITADOR COUNTERS` says "no counter", read the limit names of the route before concluding (WP-306's `-load` rename exists for that reason).

## Open points

- The counters are read from the Job. If a NetworkPolicy of kuadrant-system refuses it, the same read from a workstation through a port-forward gives the same table by hand; a permanent reader on the control node needs the owner to decide where it runs.
- The trend compares like with like only when the profile is the same; overriding iterations or concurrency makes two runs of one profile different loads, and the report does not detect that.
