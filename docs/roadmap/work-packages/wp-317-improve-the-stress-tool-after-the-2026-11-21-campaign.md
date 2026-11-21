# WP-317: Improve the stress tool after the 2026-11-21 campaign

- **State:** Repo work in review (2026-11-21: in progress on a separate branch, nothing merged; no live run of the changed tool yet)
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md), [ADR-0626](../../adr/0626-chaos-engineering-with-krkn-and-tekton-pipelines.md)
- **Depends on:** [WP-305](wp-305-build-the-stress-runner-core-and-profiles.md), [WP-307](wp-307-launch-the-stress-campaign-as-an-indexed-job.md), [WP-312](wp-312-report-the-campaigns-and-read-the-limitador-counters.md)
- **Related:** [WP-316](wp-316-run-chaos-pipelines-and-the-two-chaos-demos.md) (the chaos run beside the load), [WP-318](wp-318-lift-the-limits-found-by-the-2026-11-21-stress-campaign.md) (the limits outside the tool)
- **Target:** v0.18
- **Estimated files touched:** ~14: `platform/testing/stress_runner.py`, `ansible/roles/day3/tasks/stresstest_campaign_plan.yml`, `stresstest_campaign_launch.yml` and `stresstest_campaign.yml`, `evaluations/stress/driver_load.py`, `driver_models.py`, `driver_network.py`, `driver_unifai.py`, `driver_counters.py`, `evaluations/stress/profile_aggressive.yaml`, `gitops/charts/keycloak/values.yaml`, `docs/platform/stresstest.md`, the tests under `evaluations/tests/`

## Goal

The stress campaign of 2026-11-21 (09:35 to 10:40 UTC, on the owner's explicit request, beside a full demo pass) showed
what keeps the tool from loading the platform as intended. This work package changes the tool, not the platform's
limits (those are WP-318).

## What the campaign showed (2026-11-21)

- Every demo of the pass under load passed at the first try. No capacity limit was reached: no request waited for a
  GPU, the KV cache stayed near 15 %, the nodes stayed at or under 82 % CPU, and the gateways returned no 5xx.
- The drivers of one shard ran one after the other, and the `DURATION` override applied to each of them, so one long
  driver held back the rest.
- The load drivers asked for the quota class `stresstest` (2,000 tokens per 5 minutes per user) through the trusted
  header, not `loadtest`.
- The shared-budget guard could not read Limitador, so it was skipped.
- 10 workers shared 8 `stress-load-*` personas: 46 UnifAI sign-ins failed (Keycloak, shared persona).
- gpt-oss-20b gave empty or truncated answers under load; the load driver asks for `max_tokens` 64.

## The changes

| Finding | Change | Files |
|---|---|---|
| The drivers of a shard run one after the other | Profile key `parallel_families: [load]` runs those drivers together; `duration` becomes the campaign's budget; the Job deadline follows | `platform/testing/stress_runner.py`, `stresstest_campaign_plan.yml` |
| The load drivers use the `stresstest` class | `stress_quota_class` defaults to `loadtest` for the load family; the header becomes configurable | `stresstest_campaign_launch.yml`, `driver_load.py`, `driver_models.py`, `driver_network.py`, `driver_unifai.py` |
| The shared-budget guard cannot read Limitador | `LIMITADOR_URL` set in the Job; the counter match fixed after a live read of the counter names | `stresstest_campaign_launch.yml`, `driver_counters.py` |
| 8 personas for 10 users | two more personas, `stress-load-09` and `stress-load-10` | `gitops/charts/keycloak/values.yaml`, `profile_aggressive.yaml`, the runner tests (and `platform/keycloak/tests` before the push) |
| Empty or truncated answers | `max_tokens` 64 → 256 in the load driver | `driver_load.py` |
| Chaos beside the load | the campaign launches the chaos workflow's run (ADR-0626) instead of its own disruptions, once krkn has run live; `stresstest_chaos.yml` is kept until then | `stresstest_campaign.yml` |
| Stale documentation | the profile header and the stresstest page | `profile_aggressive.yaml`, `docs/platform/stresstest.md` |

## Acceptance

- The tests under `evaluations/tests/test_stress_*.py` cover the new keys; `platform/keycloak/tests` pass.
- A live campaign (owner's go) shows the load drivers running together for the campaign's budget, in the `loadtest`
  class, with the shared-budget guard reading Limitador, and no sign-in failure caused by shared personas.
