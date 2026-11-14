# WP-273: Pilot the guardrails demo on the lifecycle

- **State:** Operator pending
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-271](wp-271-scaffold-every-demo-directory-and-the-catalogue-check.md)
- **Related:** [WP-274](wp-274-pilot-the-unifai-live-rag-demo-on-the-lifecycle.md) (the other pilot), [WP-238](wp-238-golden-path-check-freeze-protocol-and-demo-day-runbook.md) (the `guardrails` probe)
- **Target:** v0.16
- **Estimated files touched:** ~18: `docs/demo/scenarios/governance/guardrails.md`, `ansible/demos/guardrails/*`, one evidence file

> Why: the first of the two complete demos the owner chose to prove ADR-0616 before the rollout. It covers a demo
> checked by a golden-path probe, mouse steps in its 5-minute version, terminal steps in its 15-minute version, and a
> lifecycle where almost every action has nothing to change.

## Goal

`guardrails` is played end to end through `make demo` in both versions, and its page says after each action and step
what is left to the presenter.

## Steps

1. Page: replace `## Before you start` by `## Presenter lifecycle`:
   - `### Status`: Nothing to do (the file reads the Applications `zuno-trustyai-config-d1`, `zuno-ai-gateway-d1`,
     `zuno-dify-d1`, `zuno-token-proxy-dify-d1`, the `NemoGuardrails` phase, the gateway's guardrails environment and
     the two Grafana dashboards);
   - `### Check`: what the `guardrails` probe proves, and that its detection already shows on the dashboard;
   - `### Install`: Nothing to do (shared platform, verified);
   - `### Start`: the two browser profiles and the Dify double sign-in (human), the model already woken by the file,
     the paas-ops-01 OpenShift sign-in if `status` reported its group missing;
   - `### Stop` and `### Uninstall`: Nothing to do.
2. Files: `status.yml` (`_lib/argo_apps.yml`, `cr_ready.yml`, a read of the gateway environment), `check.yml`
   (`queue_probes: [guardrails]`, `queue_browser: [dify]`, `flush_checks`), `start.yml` (one warm-up answer through
   Dify's token proxy, the way `probe_guardrails` sends its prompt, without the injection text), the others
   `nothing_to_run`. Step files: the 15-minute `oc get` rows run their reads; the rows that open Grafana, the rails file
   or Tempo say so.
3. Rehearse: `make demo use guardrails 15`, then `status`, `check`, `install`, `start`, `step next` until the last step,
   `stop`, `uninstall`; then `make demo rehearse guardrails 5` and `make demo rehearse guardrails 15`. No action
   changes the cluster, so no go is needed.
4. Write the evidence `docs/roadmap/evidence/wp-273-guardrails-rehearsal-2026-11-15.md`: both reports, the time per
   step, every "Nothing to do." checked as deliberate, what the presenter still does by hand.

## Acceptance

- Both rehearsals end with `RESULT: PASS`.
- The catalogue test passes with `guardrails` counted as moved.
- The owner reviews the evidence at the gate of 2026-11-16.
