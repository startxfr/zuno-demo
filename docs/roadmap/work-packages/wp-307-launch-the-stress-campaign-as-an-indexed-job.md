# WP-307: Launch the stress campaign as an Indexed Job

- **State:** Repo work in review (2026-11-19, committed locally, not pushed); the proof through `make` and through AAP from a worktree without `ansible/confidential.yml` is the reviewer's, with the owner's go
- **ADRs:** ADR-0624 (to be written by the reviewer: it extends ADR-0058 and ADR-0555)
- **Depends on:** [WP-305](wp-305-build-the-stress-runner-core-and-profiles.md)
- **Related:** WP-306, WP-308, WP-312
- **Target:** v0.17
- **Estimated files touched:** ~12: ansible/roles/day3/tasks/stresstest*.yml, ansible/playbooks/day3_stresstest_collect.yml, Makefile, the AAP template registries

## Goal

`make d3 stresstest PROFILE=<name>` and the AAP template `zuno-day3-stresstest` run a profile-driven campaign in the cluster, asynchronously when asked, and the rows can be read later.

## Steps

1. `stresstest.yml` dispatches: without `stress_profile` the run is the existing per-agent stresstest, untouched; with it, `stresstest_campaign.yml`.
2. `stresstest_campaign_plan.yml` (no cluster call, tested offline by `evaluations/tests/test_stress_campaign_plan.py`) validates the knobs, reads the profile and resolves the families, drivers, shards, overrides, deadline and run id (`<profile>-<UTC timestamp>`).
3. `stresstest_campaign_launch.yml`:
   - the CA ConfigMap `zuno-stress-ca` and the Secret `zuno-stress-credentials`, from the zuno-stresstest client only (no fallback to zuno-evaluations: only that client may pick a quota class, and the stresstest class is the small budget);
   - the ConfigMap `zuno-stress-scripts`, rebuilt on every launch from `stress_runner.py`, `day2_report.py`, the golden-path judges, `requirements.txt` and every `driver_*.py` and `profile_*.yaml` found in `evaluations/stress/` (a new driver needs no list to edit; the 1 MiB limit is checked);
   - one Indexed Job `zuno-stress-<run id>` (completions = parallelism = shards) on the same `python:3.12-slim` digest and `pip install` as the agent Jobs, with `activeDeadlineSeconds` and `ttlSecondsAfterFinished` (one day), the `acceptance-gate` label the gateways' NetworkPolicies admit, and the knobs as `STRESS_*` environment variables.
4. The existing per-agent Jobs become the family `agents`: they run when the profile or `FAMILIES` names it, started after the campaign Job so both run at once, and their report no longer fails the run when a profile is given (informational, ADR-0058). Without `PROFILE` the failing behaviour is unchanged.
5. Async: with `wait: false` (the soak profile, or `-e stress_wait=false`) the launch prints the run id and returns. `make d3 stresstest-collect [RUN=<id>]` (the newest run when omitted; `ansible/playbooks/day3_stresstest_collect.yml`, AAP template `zuno-day3-stresstest-collect` on the cluster-reader credential) waits if the Job still runs, reads the log of every shard, merges the per-driver summaries into one table and prints the report (every row up to 300, else the failures and the summaries).
6. Make variables `PROFILE`, `ITERATIONS`, `CONCURRENCY`, `DURATION`, `SHARDS`, `FAMILIES`, `DRIVERS`, validated in the recipe and sent to AAP as the extra vars `stress_profile`, `stress_iterations`, `stress_concurrency`, `stress_duration`, `stress_shards`, `stress_families`, `stress_drivers`. With `PROFILE` set the bulk and cleanup prompts are skipped (bulk 0, cleanup on).

## Acceptance

- `python3 evaluations/tests/test_stress_campaign_plan.py` and `python3 evaluations/tests/test_stress_runner.py` pass; `python3 platform/docs/check_docs.py` passes.
- Without `PROFILE`, `make d3 stresstest` behaves as before (same Jobs, same report, same exit code).
- Live, with the owner's go: `make d3 stresstest PROFILE=smoke` and the same through AAP from a worktree without `ansible/confidential.yml` (the `zuno-aap-installer` credential creates the ConfigMap, the Secret and the Job: confirm it can; a local `kube:admin` hides a 403). `make d3 stresstest PROFILE=soak` returns at once, and `make d3 stresstest-collect` reads it later.
- The AAP template `zuno-day3-stresstest-collect` is registered by the aap-config chart: it is a roll of that chart, announced to zuno-demo-cluster. The cluster-reader credential must be able to read the Job and the pod logs; if it cannot, give the template the installer credential and gate it.
