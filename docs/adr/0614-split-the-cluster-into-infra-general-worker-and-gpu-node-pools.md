# ADR-0614: Split the cluster into infra, general-worker and GPU node pools

- **Status:** Accepted
- **Target:** v0.17
- **Date:** 2026-11-13
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md), [ADR-0573](0573-pilot-unifai-on-demo333-with-tekos-before-cutting-demo222-over.md),
  [ADR-0101](0101-provide-ha-for-shared-agent-platform-services.md), [ADR-0612](0612-serve-every-zuno-image-from-an-internal-red-hat-quay-backed-by-an-s3-bucket.md)

## Context

demo333 was installed as a compact cluster: the three control-plane nodes were schedulable workers. Worker capacity
was added later by hand (`unifai-worker-a`, two m5a.4xlarge with a 75 GB root disk, both in zone a). On 2026-11-13 the
cost of that layout showed in one day.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | A master ran 179 pods at 97% CPU; etcd logged 668 "apply request took too long" in 10 min; about 75 operators lost their leader election and crash-looped; the Patroni timeline climbed by itself (51 → 53). | etcd and operator logs, 2026-11-13 11:00-12:30Z |
| F2 | A UnifAI e2e namespace pushed `unifai-worker-a` into DiskPressure (13.7 GB free against a 12 GB eviction threshold) and the kubelet evicted aap-gateway. | node conditions and events, 2026-11-13 13:33Z |
| F3 | Load (requests / 7-day usage): Red Hat infra-eligible set 7.8 vCPU / 34 GiB (used 5.1 / 25); apps and platform plumbing 40 vCPU / 98 GiB (used 4.5 / 62); 5 GPU model pods 8.8 / 46 GiB. Memory binds; app CPU requests are about ten times their use. | `oc get pods`, `oc adm top`, Prometheus p95 |
| F4 | Most components run one replica on purpose; many carry a zone-bound EBS volume (Vault, Keycloak Redis, Open WebUI, Dify, UnifAI in zone a). PostgreSQL already runs one instance per zone. | chart values, PV node affinity |
| F5 | Both GPU nodes are in zone a; 5 of their 6 MIG slices are in use, so one node alone no longer holds every model. g7e capacity in eu-central-1 is scarce. | node allocatable, WP-229 searches |
| F6 | The vendored `cluster-machine` subchart renders infra MachineSets (label + taint) and the infra MachineConfigPool, but not Spot instances; `QuayRegistry` overrides carry no tolerations. | `gitops/charts/machines/charts/cluster-machine-21.3.277.tgz`, `oc explain quayregistries` |

## Decision

**Run three node pools: infra nodes for the Red Hat infra-eligible components, general workers on three zones for
everything else that needs no GPU, and the existing GPU nodes for GPU work only; the control-plane nodes run no
workload.**

1. **Masters run no workload.** `schedulers.config.openshift.io/cluster` `mastersSchedulable: false`, set by
   `ansible/roles/machines` once the general and infra pools have their nodes. Their size moves to m5a.2xlarge only
   after a 7-day measurement shows a peak at or below 22 GiB per master (WP-260 P6).
2. **Infra pool.** `zuno-infra-a/b/c`, m5a.2xlarge, one per zone, label and NoSchedule taint
   `node-role.kubernetes.io/infra`, infra MachineConfigPool. It runs only the Red Hat infra-eligible set: default
   router, internal registry, platform and user-workload monitoring, OpenShift GitOps, Quay. Each component has its own
   switch, off by default: `infraNodes.router` (cert-manager chart), `infraNodes.enabled` (openshift-ai chart),
   `infraPlacement.*` (machines chart), `infraNodes` on the `zuno-registry` namespace (namespaces chart).
3. **General pool.** `zuno-worker-a/b/c`, m5a.4xlarge on demand, 200 GB, one per zone, sized so that two zones carry
   the requests when one is lost. `zuno-worker-spot-a/b/c` (m5a.2xlarge Spot, 0 to 1 each under the ClusterAutoscaler)
   absorb peaks and the overflow; Spot is never counted for the one-zone-lost sizing. `unifai-worker-a` is drained and
   retired.
4. **GPU pool unchanged.** No new GPU node and no change to the running ones; only non-GPU pods are moved off them.
   The two running GPU nodes are never scaled down, replaced or drained without the owner's double approval.
5. **Zone loss.** The major stateless components run 2 replicas spread over zones: mcp-gateway, ai-gateway once its
   quota ledger is in Redis, and MaaS (Limitador only with a shared counter store). a2a-gateway keeps its tasks and
   pending approvals in memory and stays at 1 replica until they move to a shared store (WP-260). Single-replica components with a zone-bound volume are down while their
   zone is down, by decision.
6. **CPU requests follow use.** Requests are set to twice the 7-day p95 (minimum 100m) on the largest consumers;
   limits and memory stay as they are.

## Alternatives considered

- **Platform plumbing on infra too** (mesh control plane, Vault, cert-manager, RHOAI monitoring). Technically
  convenient, but outside the Red Hat infra-eligible list; rejected by the owner.
- **Full multi-zone HA for Keycloak, Redis and Vault.** Removes the zone-a single points, at the cost of more nodes and
  one failover drill per component; deferred.
- **A third GPU node in zone b.** Would keep every model through one GPU node loss (about $4/h); the owner chose no
  GPU change for now.

## Consequences

- Non-GPU capacity goes from 8 to about 6 on-demand m5a.4xlarge equivalents (about -25%), plus Spot hours when used.
- A zone loss no longer takes the control plane's CPU with it, and a full disk on one worker no longer evicts platform
  pods on the same node as the e2e namespaces.
- Every new infra-eligible component needs its own toleration; DaemonSets without one (for example `dns-default`) do
  not run on infra nodes, which Red Hat documents as expected.

## Security considerations

The zuno-platform AppProject gains `MachineConfigPool`, the image registry `Config`, `GitopsService` and the
`openshift-user-workload-monitoring` destination, each rendered by a chart (`check_app_projects.py`). Spot instances
use the same IAM profile, security group and subnets as the on-demand workers.

## Operational considerations

Rollout phases, windows and checks are in WP-260. Each cluster phase has its own go and runs only when no other
session holds a window. A node drain of a single-replica workload with a `minAvailable: 1` PDB uses the
delete-then-drain step of ADR-0101 (31-65 s outage).

## Work packages

[WP-260](../roadmap/work-packages/wp-260-roll-out-the-infra-general-and-gpu-node-pools-on-demo333.md) (rollout on demo333).
