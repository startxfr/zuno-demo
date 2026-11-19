# WP-310: Evaluate the demos' state checks from the stress Job, and the drivers that remain

- **State:** Repo work in review (2026-11-19, batch 1 of 2: the state drivers and their read-only role; committed in the `wp306-coder` worktree on branch `wp312-coder`, not pushed). Batch 2, the new and the mutating drivers, is not started
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)
- **Depends on:** [WP-305](wp-305-build-the-stress-runner-core-and-profiles.md), [WP-307](wp-307-launch-the-stress-campaign-as-an-indexed-job.md)
- **Related:** WP-308, WP-309, WP-312
- **Target:** v0.17
- **Estimated files touched:** ~12 for batch 1: one extractor, one driver file, one generated rules file, the namespaces chart, the campaign launch task, the profiles, the tests

## Goal

Every demo's own state checks (custom resources Ready, workloads ready, Argo CD Applications Synced and Healthy) run from the stress Job as read-only drivers, without copying a single list out of the demos, and with the least read access that can do it.

## Batch 1: the state drivers (done offline)

1. `platform/testing/stress_state.py` extracts, from `ansible/demos/<id>/{status,check}.yml`, the lists the three shared libraries evaluate (`_lib/cr_ready.yml`, `_lib/workloads.yml`, `_lib/argo_apps.yml`): 311 assertions over 33 demos today. An entry that carries a Jinja expression cannot be evaluated by a Job and is counted as dropped (none today; the test fails if one appears, so it is written plainly).
2. `evaluations/stress/driver_state.py` registers one driver per demo, `<demo id>-state` (family `state`, 33 drivers; the demo's golden-path driver keeps the bare id). Each assertion is one row, with the id and the detail of the demos' own report, judged by a port of the Ansible logic (condition, phase, state, parents and exists modes, name prefix, ready replicas, Pod Ready) and, for Argo CD, by the demos' own `platform/demo/argo_health.py` (applications Synced and Healthy, the controller alive, reconciled recently). Every read is a GET by name over `https://kubernetes.default.svc` with the Job's own token (a LIST only for a kind a demo reads by name prefix); the resource name comes from API discovery, cached per group version.
3. **The role is generated, not written.** `python3 platform/testing/stress_state.py rbac` derives from the same lists a ClusterRole of 67 rules: `get` by `resourceNames` only, one `list` rule (ClusterServiceVersions, read by name prefix), no wildcard, no secrets, no write. It is committed as `gitops/charts/namespaces/files/stress-reader-rules.yaml` and a test fails when a demo names something it does not cover or the file drifts. The namespaces chart renders the ServiceAccount `zuno-stress-reader`, the ClusterRole and the binding when `stressReader.enabled` (default false: the render is unchanged), and a second binding to the built-in `cluster-monitoring-view` when `stressReader.monitoringView` (what the saturation sampler of WP-309 needs, on this ServiceAccount instead of `acceptance-gate`).
4. **Switches**: `zuno_stress_reader_enabled` (and `zuno_stress_reader_monitoring_view`) in `ansible/roles/namespaces/tasks/install_d1.yml` turn the chart on; the same variable makes the campaign Job run as `zuno-stress-reader` instead of `acceptance-gate`. The Job ConfigMap carries `state_assertions.json` (extracted at launch) and `argo_health.py`.
5. **Profiles**: `standard` and `aggressive` add the family `state`, one pass of each demo's checks (`family_defaults`, a new profile key between the budget and a driver's own settings). `smoke` has none: until the role exists every assertion would fail with `status=403`, which says what to enable.

## What the owner decides

The role is a cluster-wide READ of named platform objects: the 5 named ConfigMaps that `cr_ready` checks, the custom resources of ~50 API groups, the Argo CD Applications and the Deployments, StatefulSets and Pods the demos name (no Secret, no write, no list except the CSV kind). Enabling it is a roll of the namespaces chart and should be announced to zuno-demo-cluster. Check that the AppProject of the namespaces Application allows `ClusterRole` and `ClusterRoleBinding` before turning it on (`platform/gitops/check_app_projects.py` renders with the Application's values, so it sees the kinds only once the switch is on).

## Acceptance

Offline, done: `python3 evaluations/tests/test_stress_state.py` (27: the plural rule, the extraction and its modes and defaults, the coverage of every assertion by the rules, the role being get-only without wildcard or secrets, the committed file matching what the demos ask, the chart rendering the role only when switched on, the judges, the API paths by discovery, a 403 saying what to enable, the controller and staleness of Argo CD, one driver per demo, the profiles), `test_stress_runner.py` (`family_defaults`), `check_docs.py`, `helm template` of the namespaces chart unchanged by default.

Live, with the owner's go: `zuno_stress_reader_enabled: true` and `make d1 install namespaces` (announced), then `make d3 stresstest PROFILE=standard FAMILIES=state`. Every state row should match what `make demo check <id>` reports for the same demo; a row that differs is a bug of this port, not of the platform.

## Batch 2 (not started)

New drivers for the demos with no probe and no check list of their own to reuse: `maas-portal-api-keys`, `genai-playground`, `evaluation-trustyai-evalhub`, `identity-personas`, `multi-gateway` and `agents-alt-gateway` (Praxis only); and, as mutating drivers on a dedicated persona, `delegation-approval` and `unifai-live-rag` (they change a persona's state through UnifAI's approval and library APIs). A signed-image verification for `image-signing-admission` also belongs here: its state half is covered by batch 1, the proof that an unsigned image is refused needs an admission request the reader role must not make.
