# chaos

Day 2 component `chaos` (`make d2 install|check|uninstall chaos`, `ansible/roles/chaos`): chaos engineering of the
cluster infrastructure and of the Zuno platform with krkn and Tekton. Referenced by
`gitops/apps/chaos/application-d1.yaml` only (no operator: OpenShift Pipelines is the Day 1 component
`openshift-pipelines`). Everything lives in `zuno-chaos`, created by `gitops/charts/namespaces` (not Kueue-managed).

| Part | Source | Objects |
|---|---|---|
| `cerberus` | startx `chaos-cerberus` (alias `cerberus`) | Deployment and Service `cerberus:8080` (answers `True`/`False`), its read-only ClusterRole, a NetworkPolicy |
| `pipeline` | startx `chaos-pipeline` (alias `pipeline`) | Tasks `cerberus-check`, `krkn-run`, `krkn-hub-scenario`; Pipelines `chaos-infra`, `chaos-application`; ConfigMap `chaos-pipeline-scenarios`; ServiceAccount `chaos-pipeline` and its chaos ClusterRole; the privileged SCC for krkn's helper pods in `zuno-chaos` |
| `zuno` | `templates/` | Tasks `zuno-provider-cut`, `zuno-steady-state`; Pipeline `zuno-chaos-provider-cut`; ClusterRole `zuno-chaos-provider-cut` (AdminNetworkPolicies) for `chaos-pipeline`; Roles `zuno-chaos-runner` and `zuno-chaos-signal-reader` for the AAP credentials |

With a wrapper chart and aliases, the startx values nest one level: `cerberus.cerberus.*`, `pipeline.pipeline.*`, and the
namespace is `<alias>.project.project.name` (the `project` subcharts stay off).

Nothing runs at install: the chart renders no PipelineRun. A run is created by `ansible/roles/chaos/tasks/run.yml`
(`make d3 chaos infra|platform`, or the AAP workflows `zuno-day3-chaos-infra-workflow` and
`zuno-day3-chaos-platform-workflow`).

## Scenarios

- `pipeline.pipeline.infra.scenarios`: the tiers of `platform/chaos/targets.yaml` (`pods`: 10, 11, 12; `hog`: 20, 21;
  `latency`: 22). The node-level ones target the nodes labelled `zuno.io/chaos-target=true` (`pipeline.nodeSelector`), a
  label put on ONE node by hand with the owner's go; on demo333 the infra node ip-10-18-82-70, so they tolerate
  `node-role.kubernetes.io/infra:NoSchedule`. `30-node-reboot-worker` stays disabled (AWS credentials, after 2026-11-24).
- `pipeline.pipeline.application.scenarios`: the startx generic ones are off; one scenario per pod target of the
  catalogue, between the `BEGIN generated` / `END generated` markers, written by
  `python3 platform/chaos/targets.py render-values --write`. Edit the catalogue, never the block:
  `platform/chaos/tests/test_chart.py` fails when they differ.
- The provider cut is not a krkn scenario: `zuno-chaos-provider-cut` runs the Zuno task, whose host and subject
  allow-list (`zuno.providerCut`) must equal the catalogue's (same test).

## Dependencies: 21.3.392 is not published yet

The chart needs `chaos-cerberus` and `chaos-pipeline` **21.3.392** (the `scenarios`, `recovery-time`, `node-selector` and
`workload-namespace` parameters). On 2026-11-21 the stable index serves 21.3.391 at most, so this chart has **no
`Chart.lock`** and `helm dependency build` fails on it. Until then:

- render it offline from a local helm-repository checkout:
  `helm package <helm-repository>/charts/chaos-pipeline <helm-repository>/charts/chaos-cerberus --version 21.3.392 -d gitops/charts/chaos/charts/`
  (the `charts/` directory is gitignored, as for every chart here);
- **vendor the tgz + Chart.lock once 21.3.392 is on the stable index**: `helm dependency update gitops/charts/chaos`, then
  commit `Chart.lock` (the CI `helm` job runs `helm dependency build` on every chart with dependencies, and fails on this
  one until then).
