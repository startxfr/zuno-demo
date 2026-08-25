# ADR-0344: Track blocked resources and add a Day 0 reconcile verb

- **Status:** Implemented
- **Target:** v0.1
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

When a Day 0 install wait timed out (ArgoCD Application not Synced/Healthy, `zuno-dsc` not Ready, Subscription stuck), the run died with a raw Ansible `until`-retries error: no indication of which resource was blocked, why, or how to fix it. ADR-0343 documents four real root causes that kept the DataScienceCluster at `Ready=False`, every one of which had to be found by live investigation. ADR-0343 also established the key operational fact: Application manifests are applied by Ansible, not synced from git (ADR-0311 removed the root App-of-Apps), so re-applying a component's Application manifest is itself the baseline remediation for helm-values drift.

## Decision

Add a blocked-resource tracking layer to the Day 0 flow and a `make d0 reconcile [component]` verb that applies known remediations automatically:

- **Findings accumulator**: a play-wide `blocked_findings` fact collects structured records (`component`, `resource`, `state`, `cause`, `solution`, `auto_fix`), appended only via `ansible/tasks/record_blocked_finding.yml` (never passed as an include parameter - include params would shadow the fact). Every day0 playbook ends with `ansible/tasks/report_blocked_findings.yml`: a compact RESOURCE/STATE/CAUSE/SOLUTION/AUTO-FIX summary per finding, then one final failure naming the `make d0 reconcile <component>` commands. `make d0 check` prints the same summary but keeps its never-failing contract.
- **Generic diagnosis** (`ansible/tasks/diagnose_gitops_app.yml`): on any Application wait timeout, `apply_gitops_app.yml`'s rescue records why - app missing, error conditions, failed sync operation, each non-Synced/non-Healthy entry of `status.resources[]` (capped at 10 per app), or a stuck-Progressing catch-all (e.g. the ADR-0312 Lua Subscription health check waiting on `status.installedCSV`). A blocked component no longer aborts the whole `all` run: `ansible/tasks/run_day0_component.yml` wraps each role so remaining components still run and the summary covers everything.
- **Deep openshift-ai diagnosis** (`roles/openshift_ai/tasks/diagnose.yml`): Subscription -> InstallPlan -> CSV chain, every `False` DataScienceCluster condition mapped to the ADR-0343 solutions, and direct checks of the ADR-0343 prerequisites (`maas-db-config`, `cluster-monitoring-config`, `istio-ca-root-cert`).
- **Reconcile verb**: `day0_reconcile.yml` dispatches per component. Roles without a `tasks/reconcile.yml` fall back to their idempotent install re-run - correct by construction, since install re-applies the Application manifest and re-runs the now-diagnosing waits. `roles/openshift_ai/tasks/reconcile.yml` adds targeted remediations: approve the pending InstallPlan **only when it targets the pinned `startingCSV`** (drift is recorded as manual-only, preserving the Manual-approval pin), re-copy `istio-ca-root-cert`, re-apply both Applications with an ArgoCD hard-refresh annotation (`gitops_app_refresh`), verify `maas-db-config`, re-wait for DSC Ready. Deleting CrashLoopBackOff pods is opt-in (`-e openshift_ai_reconcile_restart_pods=true`), keeping reconcile state-restoring-only by default.

## Consequences

Blocked installs now end with an actionable summary and a one-command fix path instead of a raw retries error. With `target_component=all`, dependents of a blocked component still burn their own wait retries before being recorded (no dependency graph was added - deliberate); shorten with `EXTRA_VARS='-e gitops_app_wait_retries=3'`. `diagnose_gitops_app.yml` also runs inside precheck, so it must stay strictly read-only and never-failing. Reconcile never approves a drifted InstallPlan - CSV drift always remains a manual decision.

## Acceptance criteria

- A timed-out wait produces per-resource findings and a final BLOCKED RESOURCES summary; the run exits non-zero naming `make d0 reconcile <component>`.
- `make d0 reconcile openshift-ai` restores a deleted `istio-ca-root-cert` copy and an unapproved pinned InstallPlan without manual `oc` commands.
- `make d0 check` reports the same findings and still exits 0.

## Implementation note (2026-08-25) — the reconcile verb moved to Day 1, and this ADR's acceptance criterion was never runnable

This ADR's acceptance criterion reads *"`make d0 reconcile openshift-ai` restores a deleted `istio-ca-root-cert` copy and an unapproved pinned InstallPlan without manual `oc` commands."* That command has never worked. `reconcile` was a Day 0 verb and `openshift-ai` is a Day 1 component, so the Day 0 dispatcher — which validates the component against `DAY0_COMPONENTS` — rejected it every time. Nine blocked-findings across `ansible/roles/openshift_ai/` printed it as the authoritative remedy, and `ansible/tasks/report_blocked_findings.yml` used the same `make d0 reconcile <component>` shape as its default for any finding that omitted `auto_fix`.

Nothing detected this because `auto_fix` is a plain string: it is printed for a human to type, never executed during a run and never validated. The diagnosis layer, `roles/openshift_ai/tasks/reconcile.yml` and its remediations were all correct — only the entry point was missing. The practical consequence, found live on 2026-08-25: ADR-0201's payload-processing sidecar injection had been diagnosed, automated and documented, and was still unapplied ten hours after an install that had correctly flagged it, because no documented command reached it.

`reconcile` now also exists on Day 1 (`make d1 reconcile [component]`, `ansible/playbooks/day1_reconcile.yml`), so **this ADR's criterion should be read as `make d1 reconcile openshift-ai`**. The decision itself is unchanged: same per-component dispatch, same fallback to the idempotent install re-run for roles without a `tasks/reconcile.yml`, same refusal to approve a drifted InstallPlan. `ansible/tasks/run_day0_component.yml` became the day-agnostic `ansible/tasks/run_component.yml` so both days share one implementation, and `platform/docs/check_docs.py` now validates every `auto_fix` string against the Makefile's real verb/component lists, so a hint naming a command the Makefile rejects fails CI instead of surviving indefinitely.
