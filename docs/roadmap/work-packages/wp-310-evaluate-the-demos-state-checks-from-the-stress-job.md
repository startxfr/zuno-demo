# WP-310: Evaluate the demos' state checks from the stress Job, and the drivers that remain

- **State:** Repo work in review (2026-11-19, batch 1 of 2: the state drivers and their read-only role; committed in the `wp306-coder` worktree on branch `wp312-coder`, not pushed). Batch 2: three HTTP drivers and the three mutating drivers (approved by the owner 2026-11-19) done offline, none run live (below)
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

## Batch 2 (three drivers done offline, the rest decided)

Done (`evaluations/stress/driver_demos.py`, family `experiences`, throttled to one request at a time in `standard` and `aggressive`, 14 offline tests in `test_stress_drivers.py`):

- `maas-portal-api-keys`: `GET https://maas.<domain>/zuno-ai-run/gpt-oss-20b/v1/models` WITHOUT a key must answer 401/403 (the demo's 2:15 step); a 200 is an open gate and fails. It needs the zuno-ai-run egress to `maas.<domain>`, which is not in the allow-list yet (`MAAS_URL` overrides the URL). It does not create or revoke a key: that is the portal's UI.
- `identity-personas`: the stress persona's password-grant token read without signature check: `preferred_username`, `azp` (the stress client), the `zuno` realm issuer, expiry, and the number of groups (reported, not asserted: whether the stress personas carry groups is not known from the repository).
- `multi-gateway`: one short question through the Zuno ai-gateway (persona token) and through Praxis (device sign-in of `claude-code`), one row per door, so a difference between the two shows. It spends the Praxis budget like `claude-code-sovereign`.

Decided not to build, and why:

- `genai-playground` and `evaluation-trustyai-evalhub`: their steps are web-UI moves (Playground, EvalHub profile pages) plus `oc get`, which batch 1 already covers; there is no HTTP contract a Job can replay without a browser. They stay with their state drivers.
- `agents-alt-gateway`: no driver of its own beyond its state check. The kagent agent `zuno-diagnose-praxis` is live (WP-297 Done, Accepted and Ready on demo333, 2026-11-19), so its state driver no longer skips that object (`NOT_YET` in driver_state.py is empty).
- the three mutating drivers below were first held back, then approved by the owner (2026-11-19) with the conditions written there.

## Batch 2b: the three mutating drivers (`evaluations/stress/driver_mutating.py`, family `mutating`)

Owner's conditions (relayed by zuno-demo-assist, 2026-11-19): a dedicated persona, all three disabled by default, the image proof in a dedicated test namespace with its RBAC written down and behind its own switch (default off), every driver cleans up what it creates. The owner is shown the grants before anything is enabled.

**Disabled by default, twice.** Each driver is registered `mutating` (the runner skips it unless the profile sets `allow_mutating`), and only the new profile `evaluations/stress/profile_mutating.yaml` sets it; no other profile has the family `mutating` or the key. The one deliberate way to run them is `make d3 stresstest PROFILE=mutating` (or `DRIVERS=<id> ` on a profile that allows it).

**One persona, a constant.** `stress-mutate-01`, a new `evalPersonas` entry of the keycloak chart: `copyOf: consultant-01` (the persona both scenarios run as, so it holds exactly the groups they need, no `/zuno-loadtest`), joined to `/zuno-evaluation` like every evaluation persona. The drivers never read `ctx.persona` (a test fails if the source does). It is created by the eval-personas Job (create-only; deadline 1800 s since 1586ee86), so the keycloak chart must be rolled and the Job run before the first use. The copy is not narrower than consultant-01: narrowing it to the minimum set of groups needs a live look at which group each scenario really reads.

| Driver | What it changes | Cleanup | Row |
|---|---|---|---|
| `delegation-approval` | one UnifAI session as `stress-mutate-01` asking Arkos to have Tekos launch a cluster audit (a delegated write); the pending approval is **rejected, never approved** (an approval would start a real AAP job) | the session is cancelled then deleted in a `finally`; the stale and a made-up request id must both answer 409 `approval_not_pending` | `reject-and-stale` |
| `unifai-live-rag` | one small uniquely named document (`stress-rag-<run>-<i>-<hex>.md`) in the persona's Personal library, indexed until DONE | deleted by exact name in a `finally`, then listed to prove it is gone; indexing and cleanup are two rows so a leftover is never hidden by a pass | `upload-indexed`, `cleanup` |
| `image-signing-refusal` | nothing: an unsigned, tag-referenced image offered as a **dry-run** pod create to the namespace `zuno-stress-admission` | none needed (dry run stores nothing) | `unsigned-refused` |

**RBAC the image proof needs (written down first).** A pod create that the image-signing webhook must refuse needs one verb on one resource in one namespace, and nothing the read-only stress role may have:

- namespace `zuno-stress-admission`, labelled `policy.rhtas.com/include=true` (the label the PolicyController's `namespaceSelector` requires, `gitops/charts/rhtas-config/templates/policycontroller.yaml`); nothing else is deployed in it;
- `Role stress-image-proof` in that namespace: `pods` -> `create`; `RoleBinding` of it to the ServiceAccount `zuno-ai-run/zuno-stress-reader` (the identity of the campaign Job); no ClusterRole, no other verb, no other namespace;
- rendered by `gitops/charts/namespaces/templates/stress-image-proof.yaml` only when `policy.enabled` and `stressReader.enabled` and `stressImageProof.enabled`; the switch is `zuno_stress_image_proof_enabled` (default false, `ansible/roles/namespaces/tasks/install_d1.yml`), so the default render is unchanged (diff of `helm template`: 0 lines).

What the proof can and cannot say: the webhook refuses an image referenced by tag unconditionally ("must be referenced by digest", whatever the policy `mode`), so this row proves the webhook is wired to the namespace, not that a signature is verified: while the ClusterImagePolicy is in `warn` mode an unsigned image referenced BY DIGEST would be admitted with a warning, and this driver does not test that. The `unifai-live-rag` driver proves the upload-to-DONE path and the cleanup, not an answer from the document (that costs model tokens and a question the demo's page already covers).

Offline, done: `python3 evaluations/tests/test_stress_mutating.py` (19: registration and the profile gate, the persona constant, the approval flow with a scripted UnifAI (reject only, stale probes, session cancelled and deleted with or without a request), the RAG cycle (delete after a failed indexing, one name end to end), the admission judge, the dry run sent only to the dedicated namespace, the grant rendered off by default and as one verb on pods when on), the other stress suites, `helm template` of the namespaces chart unchanged by default, `check_docs.py`. Not run live: nothing here has touched UnifAI, Keycloak or the cluster.
