# WP-311: Inflict bounded disruptions beside the stress load

- **State:** Repo work in review (2026-11-19, committed in the `wp306-coder` worktree on branch `wp311-coder`, based on origin/devel 78b1bafc, not pushed); every live step is the owner's go
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)
- **Depends on:** [WP-305](wp-305-build-the-stress-runner-core-and-profiles.md), [WP-307](wp-307-launch-the-stress-campaign-as-an-indexed-job.md), [WP-312](wp-312-report-the-campaigns-and-read-the-limitador-counters.md)
- **Related:** WP-308, WP-309; [WP-316](wp-316-run-chaos-pipelines-and-the-two-chaos-demos.md) and [ADR-0626](../../adr/0626-chaos-engineering-with-krkn-and-tekton-pipelines.md) (2026-11-21: krkn pipelines are to replace these disruptions; this brief is marked superseded only after a live krkn run)
- **Target:** v0.17
- **Estimated files touched:** ~16: the catalogue, the validator, two Ansible task files, the plan/launch/collect wiring, the runner timeline, the report, the aggressive profile, the Makefile, an optional aap-config grant, the tests

## Goal

The `aggressive` profile does not only push load: it also deletes one platform pod at a time and cuts one external provider for two minutes while the load runs, then says what the load saw and how long the platform took to run clean again. Nothing is inflicted unless the operator types the profile name a second time.

## RBAC the disruptions need (written first, as asked)

| Disruption | Kubernetes right | Who has it today | What this package does |
|---|---|---|---|
| `pod-delete` (list pods, delete one, read the workload) | `pods` list/delete, `deployments` and `statefulsets` get, in the target namespace | `aap-installer` already holds pod delete cluster-wide ([clusterrole-installer.yaml](../../../gitops/charts/aap-config/templates/clusterrole-installer.yaml)); a workstation login holds all | nothing to add |
| `provider-cut` (create and delete one AdminNetworkPolicy) | `adminnetworkpolicies` get/list/create/delete, cluster-scoped, group `policy.networking.k8s.io` | **not** `aap-installer`; a workstation `kube:admin` login does | optional ClusterRole + ClusterRoleBinding `zuno-stress-chaos` in the aap-config chart behind `chaosRbac.enabled`, **default false** (render unchanged, proven by a diff of `helm template`) |

What the owner decides: whether the AAP installer credential may create AdminNetworkPolicies. Kubernetes RBAC cannot limit a CREATE to one object name, and an AdminNetworkPolicy outranks every NetworkPolicy of the cluster, so the grant is wider than what the task uses. The mitigations are in the code, not in RBAC: the policy is built only by `platform/testing/stress_chaos.py` (a Deny of egress to the /32 addresses of one allow-listed provider, subject limited to the ai-gateway pods, priority 90), lives at most 300 seconds, is deleted by an `always` block, is labelled `zuno.io/stress-chaos=true`, and any left-over is removed at the start and at the end of every chaos stage. Without the grant the same run works from a workstation (`make d3 stresstest` with the operator's own login) and the AAP run reports the provider cut as a failing row that names the missing right, it does not skip silently.

## Steps

1. **The closed catalogue** `evaluations/stress/chaos.yaml`, checked by `stress_chaos.py validate` and a unit test: two kinds (`pod-delete`, `provider-cut`), targets from an allow-list of application names per namespace (never a model pod, a node, a namespace or a scale), providers from a host list, `duration` at most 300 s, `recover_within` at most 600 s. Six entries: ai-gateway, mcp-gateway, a2a-gateway, praxis, open-webui pods and the Mistral cut. `labels_checked: false` would mark a selector written from the chart and not yet seen on a live pod (all five were seen live 2026-11-19); a selector that matches nothing fails the row and says so.
2. **The plan**: the profile lists `chaos:` ids with `chaos_start` (300 s) and `chaos_spacing` (150 s); each starts the spacing after the previous one's end. Only `aggressive` lists any. `CHAOS_CONFIRM=<profile>` (typed twice on purpose, refused without `PROFILE`) confirms; `-e stress_chaos=false` switches them off; without confirmation the plan prints what was *not* inflicted.
3. **The disruptors** (`stresstest_chaos.yml`, `stresstest_chaos_one.yml`): wait until launch + `at`; pod-delete finds the pods by selector, deletes one, waits until the victim is gone and the workload is whole within `recover_within`; provider-cut resolves the host, applies the policy, holds, deletes it whatever happens and checks it is gone. Each makes one row, layer `chaos`, `window=<start>-<end>` in the detail.
4. **The load's view**: the runner keeps a 10-second timeline (iterations, failures) per driver, merged over the shards. The report correlates each window with it: failures before, during and the minute after, and the time to run clean again; a disruption that did not recover makes the verdict `ATTENTION`.

## Acceptance

Offline, done: `python3 evaluations/tests/test_stress_chaos.py` (22: catalogue validity and refusals, plan spacing, the policy's shape, injectable DNS, shard timeline merge, the effects over a timeline, the report section, Makefile/plan/chart wiring) and the other stress suites; `helm template` of aap-config identical by default; `check_docs.py`.

Not run (the safety classifier refused any `make d3` call): the Makefile's `CHAOS_CONFIRM` guards were read, not executed. Run `make d3 stresstest CHAOS_CONFIRM=aggressive` (expects "need PROFILE") and `PROFILE=aggressive CHAOS_CONFIRM='A B'` (expects the typed-name error) before the first live use.

Live, with the owner's go (and the grant above for AAP): `make d3 stresstest PROFILE=aggressive CHAOS_CONFIRM=aggressive`, then `make d3 stresstest-collect`. The report shows a `CHAOS` section, one line per disruption, `recovered` or `DID NOT RECOVER`, with the failure counts around it.

## Open points

- Selectors and the `v1alpha1` AdminNetworkPolicy API were confirmed live by zuno-demo-assist on 2026-11-19.
- Every live disruption is a real outage of one replica; run it outside a demo window and after the agents rollout of zuno-demo-cluster.
