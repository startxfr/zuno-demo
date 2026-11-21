# ADR-0626: Chaos engineering with krkn and Tekton pipelines

- **Status:** Proposed
- **Target:** v0.18
- **Date:** 2026-11-21
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0624](0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md) (its clause 6,
  bounded chaos, is replaced by this record once krkn has run live), [ADR-0536](0536-live-node-failover-drill-for-qwen-model-fallback.md)
  (the node failover drill, unchanged), [ADR-0418](0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md)
  (operations as AAP templates), [ADR-0620](0620-build-third-party-images-from-source-with-openshift-pipelines-and-push-them-to-quay-io.md)
  (OpenShift Pipelines on the cluster), [ADR-0616](0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
  (the demo lifecycle)

## Context

On 2026-11-21 a one-hour stress campaign ran beside the demos of the catalogue (09:35 to 10:40 UTC). Every demo of the
pass under load passed at the first try. No capacity limit was reached, but the campaign found limits of quotas and
tooling (WP-317, WP-318). The bounded disruptions of ADR-0624 clause 6 (WP-311) were not part of it: they have never
run live.

The same day the startx Helm repository released three chaos charts, 21.3.391: `chaos-cerberus`, `chaos-kraken` (krkn
5.2.15) and a new `chaos-pipeline`, which runs krkn scenarios as OpenShift Pipelines (Tekton). The platform owner asked
for two demos built on them (chaos on the cluster's infrastructure, chaos on the Zuno AI platform) and for demo333 to
prove the charts.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | The charts 21.3.391 passed an admission dry-run on demo333 on 2026-11-21 and have never run on a cluster. They are prerelease. | the startx stable index; the owner's plan of 2026-11-21 |
| F2 | `chaos-pipeline` ships 3 Tasks (`cerberus-check`, `krkn-run`, `krkn-hub-scenario`) and 2 Pipelines (`chaos-infra`, `chaos-application`). It never creates a PipelineRun. A scenario is a value (`type` and `content` in krkn's format), so Zuno can add its own. | the chart's templates and values, 21.3.391 |
| F3 | The hog, latency and time scenarios start privileged helper pods and select nodes with `node-role.kubernetes.io/worker=`, which can select a GPU node. All pods are BestEffort and carry no Kueue label. | the chart's values, 21.3.391 |
| F4 | The cerberus gate fails on any Degraded ClusterOperator or any non-Running pod of a watched namespace. On 2026-11-21, four pods were crash-looping on memory: the dashboard, feast and spark operators (before the load) and the Tempo compactor (at the peak). | the chart; the campaign evidence of 2026-11-21 |
| F5 | WP-311's disruptions (`evaluations/stress/chaos.yaml`, six entries, 22 offline tests) were never run live. | [WP-311](../roadmap/work-packages/wp-311-inflict-bounded-disruptions-beside-the-stress-load.md) |
| F6 | OpenShift Pipelines 1.24.3 is installed on demo333; PipelineRuns are excluded from Argo CD. | ADR-0620, WP-291 |
| F7 | `zuno-day3-scenario-failover-node-workflow` is an AAP workflow with an approval node. | `gitops/charts/aap-config/values.yaml` |

## Decision

**Zuno runs its chaos experiments with krkn, as Tekton pipelines in one namespace, on a closed list of targets, and a
run starts only through an AAP workflow that a person approves.**

1. **Charts consumed pinned.** The Day 2 component `chaos` (`make d2 install chaos`, `make d2 check chaos`) is a local
   wrapper chart, `gitops/charts/chaos`, with `chaos-cerberus` and `chaos-pipeline` as dependencies at an exact version
   of the startx stable index, vendored as tgz files. A fixed chart (21.3.392 or later) is taken by changing that pin.
   `chaos-kraken` is not part of the component: the pipeline replaces its Job. It is proven once, as a chart test.
2. **One namespace.** Cerberus, the Pipelines, their ServiceAccount `chaos-pipeline` and the privileged helper pods of
   the node scenarios run in `zuno-chaos`, and nowhere else. The namespace is not Kueue-managed.
3. **A closed target catalogue.** `platform/chaos/targets.yaml` names every target an application run may break: one
   pod of a named application (namespace, selector, replicas, the time it has to recover), or a cut of one external
   provider for a bounded time. It replaces `evaluations/stress/chaos.yaml` and keeps its rules: an allow-list, one pod
   at a time, a bounded recovery. etcd and the control-plane nodes are never a target, and no node is rebooted. The
   node tiers (CPU, memory, network) act on one node labelled `zuno.io/chaos-target=true`, never a GPU node.
4. **AAP approval.** A run is launched only by the AAP workflows `zuno-day3-chaos-infra-workflow` and
   `zuno-day3-chaos-platform-workflow`: pre-check (the health signal `True`, `make d3 check recovery`, no other chaos
   PipelineRun running) → approval → run (creates the PipelineRun, waits, reads the result) → post-check (each target
   back within its bound). `make d3 chaos infra|platform` routes to these workflows and asks for
   `CHAOS_CONFIRM=<infra|platform>`. One chaos run at a time.
5. **The provider cut stays a Zuno task.** The cut of one SaaS provider is a Zuno Tekton task that creates an
   AdminNetworkPolicy and always removes it at the end, with the label and the reaping of WP-311.
6. **ADR-0624 clause 6 is replaced once krkn has run live.** Until a live run proves the pipeline, clause 6 and WP-311
   stand. After it, the stress campaign launches the chaos run instead of its own disruptions (WP-317), WP-311 is marked
   superseded, and its Ansible chaos files are removed.
7. **The node failover drill stays ADR-0536.** It is a separate, approved drill on GPU nodes, not a chaos target.
8. **Worker reboot later.** The reboot scenario (tier 3) is off. It comes after 2026-11-24, with a dedicated cloud user
   allowed only `ec2:RebootInstances` and `ec2:Describe*`, its key in Vault and delivered by an ExternalSecret.
9. **Two demos.** The scenarios `chaos-infrastructure` and `chaos-platform` of the catalogue's resilience layer show
   the two pipelines, launched by their workflow and approved on stage (WP-316).

## Alternatives considered

- **Keep WP-311's Ansible disruptions.** They are a closed list too, but they run only inside a stress campaign, have no
  health gate of their own and were never run live. krkn brings node scenarios (hog, latency) and a health signal.
- **Run `chaos-kraken` as a Job.** A Job has no gate, no per-task result and no console view; the pipeline has all
  three and the same scenarios.
- **Launch the PipelineRun from `make` alone.** It would skip the approval and the audit record that AAP gives every
  run.
- **Use Litmus or Chaos Mesh.** They need their own operator and CRDs; krkn is what the startx charts package.

## Consequences

- A chaos run is recorded twice: the AAP workflow (who approved it) and the PipelineRun (what broke, and whether it
  healed in time).
- The pre-check refuses a run on an unhealthy cluster, so a crash-looping pod in a watched namespace blocks every run
  until it is fixed or explicitly ignored, and said so on the demo page.
- Each new target is a reviewed change to the catalogue, not a parameter.
- The charts are prerelease: a chart fix needs a new pin and the same render comparison as any startx chart.

## Security considerations

- The node scenarios start privileged helper pods. They are confined to `zuno-chaos`, which is the only namespace whose
  pods may be privileged for this purpose, and they are removed at the end of a run.
- The ServiceAccount `chaos-pipeline` may delete pods only in the namespaces of the catalogue, and create and delete
  the AdminNetworkPolicies that carry the chaos label.
- The approval is a separate AAP step: the person who approves is recorded.
- No cloud credential exists until the reboot tier; it will be a dedicated user with two permissions.

## Operational considerations

- `make d3 check recovery` is the steady-state reference before and after every run.
- No chaos run during a freeze. The first live validation is planned for 2026-11-22, each step on the owner's go,
  ordered from the safest to the most intrusive.
- Rollback: `make d2 uninstall chaos` removes the pipelines, cerberus and their RBAC; helper pods and network policies
  are reaped by label.

## Work packages

[WP-316](../roadmap/work-packages/wp-316-run-chaos-pipelines-and-the-two-chaos-demos.md) (the chaos component, the
target catalogue, the AAP workflows and the two demos), [WP-317](../roadmap/work-packages/wp-317-improve-the-stress-tool-after-the-2026-11-21-campaign.md)
(the stress tool, including the chaos run beside the load), [WP-318](../roadmap/work-packages/wp-318-lift-the-limits-found-by-the-2026-11-21-stress-campaign.md)
(the limits found on 2026-11-21, among them the crash-looping pods that cerberus would see).
