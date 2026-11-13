# WP-260: Roll out the infra, general and GPU node pools on demo333

- **State:** Operator pending
- **ADRs:** [ADR-0614](../../adr/0614-split-the-cluster-into-infra-general-worker-and-gpu-node-pools.md)
- **Depends on:** none
- **Estimated files touched:** ~15 (machines, cert-manager, openshift-ai, namespaces, quay-registry, postgresql charts;
  machines and argocd roles; recovery check; docs)

> Opened 2026-11-13 with the owner's go on the plan. Every cluster phase below needs its own go, is announced to the
> other sessions, and runs only when no other session holds a window.

## Why

See ADR-0614: a saturated schedulable master took etcd and every operator down, and a 75 GB worker disk filled by an
e2e namespace evicted platform pods.

## Already live before this WP (2026-11-13, emergency, owner's go)

- `zuno-worker-a/b/c` (m5a.4xlarge, 150 GB live, one per zone) created; `mastersSchedulable: false`; about 20 pods
  moved off master ip-10-18-28-96 (97% → ~65% CPU, etcd slow applies 668 → 12 per 10 min). Commits 01f8267c,
  1db71b86.

## Phases

| Phase | Content | Cluster effect | State |
|---|---|---|---|
| P0 | Charts and roles: infra and Spot pools (141fa03d), per-component infra switches and AppProject (4b972941), CPU right-sizing of PostgreSQL and Quay (prepared, pushed in P3), ADR-0614 and this WP | none (switches off) | Done except the gateway replica change |
| P1 | `make d0 install argocd` (AppProject), then `make d0 install machines`: infra pool + `zuno-infra-a/b/c`, Spot sets at 0 | 3 new nodes | Not started |
| P2 | Flip, one at a time with a check after each: `infraPlacement.registry`, `infraNodes.router`, `infraNodes.enabled` (monitoring), `infraPlacement.userWorkloadMonitoring`, `infraPlacement.gitops`, `infraNodes` on zuno-registry (Quay pods restart: short registry outage, no release copy during it) | rolling moves | Not started |
| P3 | Push the right-sizing; 2 replicas + zone spread for mcp-gateway, ai-gateway (with `quotaLedger.store: redis`) and MaaS (Limitador stays at 1 unless it gets a Redis backend: its counters are in memory); a2a-gateway stays at 1 (see below) | brief rolls | Not started |
| P4 | Roll `zuno-worker-a/b/c` to 200 GB one at a time; drain and retire both `unifai-worker-a` nodes; delete the set and its chart entry | drains | Not started |
| P5 | Delete the non-control-plane pods left on the masters and the non-GPU pods on the GPU nodes (no change to the GPU nodes) | pod moves | Not started |
| P6 | Masters to m5a.2xlarge through the ControlPlaneMachineSet, only if the 7-day peak per master is at or below 22 GiB; window of at least 2 h | control-plane roll | Not started |
| P7 | `check_recovery.py`: infra pool and unschedulable masters; final cost table | none | Not started |

## Rules

- The two running GPU nodes (`zuno-gpu-a`) are never scaled down, replaced or drained without the owner's double
  approval.
- After each phase: golden path 13/13, `python3 platform/recovery/check_recovery.py` all ok, no new operator restart
  for 30 min, etcd slow applies under 20 per 10 min.

## Gateway statelessness (code read, 2026-11-13)

| Gateway | Verdict | Why |
|---|---|---|
| mcp-gateway | Safe at 2 | `/mcp` is POST-only with no session id; each backend call opens its own MCP session; registries load identically at start. `/admin/reload-policy` acts on one pod: call it per pod or restart. |
| ai-gateway | Safe with a change | Token budgets are in memory by default (`quotaLedger.store: memory`): two pods would double every budget. Set `quotaLedger.store: redis` (REDIS_ADDR is wired). Per-key ceilings, stream counts and `/admin/optimizer/*` overrides stay per pod. |
| a2a-gateway | Not safe | Tasks (`InMemoryTaskStore`) and pending delegation approvals (`PendingStore`) live in the process: a reject reaching the other pod fails with "Task … does not exist". Needs a shared task store and approvals in Redis, or `sessionAffinity: ClientIP` as a stopgap; stays at 1 replica until then. |

## Right-sizing evidence (Prometheus, 7-day p95 CPU, 2026-11-13)

| Workload | Request | p95 | New request |
|---|---|---|---|
| PostgreSQL instance (×3) | 2 | 237m | 500m |
| Quay app | 2 | 68m | 150m |
| Clair | 2 | 1m | 100m |
| Quay Redis | 500m | 1m | 100m |
| Clair DB | 500m | 4m | 100m |

Follow-ups, not in this WP's first pass: KServe router-schedulers (4 × 1 core, changing them re-rolls the
LLMInferenceServices and their MIG-bound model pods), Lightspeed rhokp, OGX, MLflow, EvalHub (vendor CRs, fields to
check).

## Acceptance

- Infra nodes run only the Red Hat infra-eligible set and DaemonSets; masters only the control plane; GPU nodes only
  model pods and DaemonSets.
- AZ drill (separate go): cordon the workers and infra node of zone c, delete their pods, golden path PASS, zone-c-pinned
  pods Pending by design, then uncordon.
