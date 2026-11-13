# WP-260: Roll out the infra, general and GPU node pools on demo333

- **State:** Done
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
| P1 | AppProject applied (`oc apply -k ansible/roles/argocd/kustomize/appproject`, only the 4 additions in the diff), then `make d0 install machines` (rc 0): infra pool 3/3 updated, `zuno-infra-a/b/c` Ready in 1a/1b/1c with the taint and only DaemonSets on them, Spot sets at 0 with their autoscalers; GPU sets untouched (`zuno-gpu-a` 2/2, `zuno-gpu-c` still in 1b) | 3 new nodes | Done 2026-11-13 ~17:35Z |
| P2 | Moved, one at a time, each followed by a check: image registry (c49307d3), router (c8540cab, console 200 throughout), platform monitoring (d485ec4a + cbb91a60), UWM (81ea151e), GitOps (74b9c627 + 9afa3826), Quay (5e528e55; registry outage 18:54:50-18:58Z). Golden path 13/13 PASS and `check_recovery.py` all ok after the phase. Incidents below | rolling moves | Done 2026-11-13 19:05Z |
| P3 | ai-gateway and mcp-gateway at 2 replicas, spread over zones (bb1d86d7; ai-gateway already counts quotas in Redis on demo333); MaaS gateway (Istio deployment through `maas-gateway-config`) and Authorino at 2 (1d458f75; MaaS answered 401 throughout); maas-api stays at 1 (its owner, the MaaS `Config` CR, has no replicas field), Limitador at 1 (in-memory counters), a2a-gateway at 1 (in-memory tasks); right-sizing pushed (6804be49): PGO rolled the 3 instances, Patroni 3/3 TL 54 with s7tr as leader, Quay rolled without losing health. The golden path then read the ai-gateway log from one pod only: fixed to read every replica (74da3555). Golden path 13/13, `check_recovery.py` all ok | brief rolls | Done 2026-11-13 19:30Z |
| P4 | `zuno-worker-a/b/c` replaced one at a time by 200 GB machines (surge to 2, mark the old Machine `delete-machine`, scale to 1: MAPI drains it); Keycloak `zuno-0` deleted twice when it was the only pod left (PDB, ADR-0101), discovery back to 200 within a minute. Both `unifai-worker-a` nodes drained and retired, MachineSet deleted (13.4 vCPU / 27 GiB of requests moved, 0.2 vCPU zone-a-pinned). A fresh node pulled the NeMo Guardrails image from registry.redhat.io in ~9 min, so the first golden path failed on guardrails; 13/13 PASS once it started. `check_recovery.py` all ok | drains | Done 2026-11-13 20:50Z |
| P5 | Pods deleted in three waves (non-GPU pods off the GPU node; first of each pair and stateless pods off the masters; second of each pair and single stateful pods: Vault, MongoDB, the Redis instances, a2a-gateway, Limitador). Vault now auto-unseals (AWS KMS) and came back unsealed. Two pods were missed because the wave files had no final newline (`while read` skips the last line) and were deleted by hand; `unifai-rag-celery` landed back on the GPU node with "failed to prepare subPath" and was recreated. End state: masters run only control-plane pods pinned to them, DaemonSets and one RHOAI pod that tolerates the master taint (`data-science-prometheus-cluster-proxy`); GPU nodes run only the 5 model pods and DaemonSets. Golden path 13/13, `check_recovery.py` all ok | pod moves | Done 2026-11-13 21:15Z |
| P6 | Measured, not done: the control-plane pods alone peak above the gate on two masters (see "P6 verdict"). The masters stay m5a.4xlarge | none | Closed, no-go 2026-11-13 |
| P7 | `check_recovery.py` gains a `layout` layer (masters unschedulable, no workload pod on a master, infra pool at 3 Ready nodes), with a test; operations.md documents the pools and the worker replacement recipe; cost table below | none | Done 2026-11-13 |

## P2 incidents and traps (2026-11-13)

- **Router served a self-signed certificate for about 70 min (17:37-18:46Z).** Two Applications render the
  cert-manager chart (d0 and d1). The `infraNodes.router` default also made d0 render IngressController/default with
  the placement alone; d0 took it over and its apply removed `defaultCertificate`, so the router fell back to the
  operator's self-signed wildcard. Fixed live (certificate restored, `argocd.argoproj.io/sync-options: Prune=false` on
  the object so d0 could never prune it) and in 5735b3dd (the placement renders only with the certificate, in d1).
  Rule: before adding a switch to a chart, list the Applications that render it.
- **Monitoring config webhook refused `prometheusOperatorAdmissionWebhook.tolerations`** (OCP 4.22), which blocked the
  openshift-ai d0 sync until its retries ran out; that component stays on the workers (cbb91a60). A server dry-run of
  the rendered ConfigMap catches this.
- **`runOnInfra` set only the tolerations** on the openshift-gitops deployments; the explicit `nodeSelector` in the
  GitopsService pins them (9afa3826). Then the legacy quota `openshift-gitops-quotas` (startx chart) blocked the new
  ReplicaSets at 40/40: 33 zero-replica ReplicaSets older than 7 days were deleted.
- `startx-cluster-infra-config` (startxfr/helm-repository, no selfHeal) also tracks `cluster-monitoring-config`; a push
  on its source would overwrite the infra placement and `enableUserWorkload`. Open for the owner.

## Follow-up from P4

New nodes pull large `registry.redhat.io` images slowly (NeMo Guardrails ~9 min on 2026-11-13). Mirroring the
largest platform images into Quay would shorten every future node replacement: done as
[WP-261](wp-261-mirror-the-large-red-hat-product-images-into-the-internal-quay.md) (ADR-0612 family e, owner's choice of 2026-11-14).

## P6 gate: CPU as well as memory (measured 2026-11-13 17:40Z)

With every workload off it, master ip-10-18-28-96 still used ~7.2 vCPU: kube-apiserver 3.7, kube-controller-manager
(the elected leader) 2.1, openshift-apiserver 0.8, etcd 0.6. An m5a.2xlarge has 8 vCPU (~7.5 allocatable). P6 therefore
also needs the 7-day CPU peak per master at or below 5.5 vCPU; otherwise the masters stay m5a.4xlarge.

## P6 verdict (Prometheus, 7 days to 2026-11-13 21:30Z, control-plane namespaces only, masters)

| Master | CPU p95 | CPU max | Memory max |
|---|---|---|---|
| ip-10-18-28-96 | 6.80 | 7.47 | 23.8 GiB |
| ip-10-18-36-37 | 6.74 | 6.88 | 23.2 GiB |
| ip-10-18-94-42 | 5.44 | 6.28 | 18.5 GiB |

The gate is 5.5 vCPU and 22 GiB. An m5a.2xlarge has 8 vCPU and about 29 GiB allocatable, and the control plane alone (kube-apiserver
about 14 GiB each, the elected kube-controller-manager about 2 cores) would leave no headroom. The week includes the 2026-11-13
operator storm, but the load measured after P5 (4.4-5.5 vCPU, 18-26 GiB per master, every pod included) also misses the memory
gate. The masters stay m5a.4xlarge; a later re-measure can reopen this.

## Cost (eu-central-1, USD per hour)

On-demand list prices (m5a.4xlarge 0.832, m5a.2xlarge 0.416) are the published Frankfurt prices, not fetched: the account has no
`pricing:GetProducts`. The Spot price is from `describe-spot-price-history` on 2026-11-13 (m5a.2xlarge 0.220-0.232). GPU:
2 x g7e.4xlarge at about 4 each (ADR-0351), unchanged throughout.

| Layout | Non-GPU instances | USD/h | USD/month (730 h) |
|---|---|---|---|
| Morning of 2026-11-13 (masters schedulable) | 3 masters + 2 unifai-worker, all m5a.4xlarge | 4.16 | ~3,040 |
| After the emergency fixes (same day) | 3 masters + 2 unifai-worker + 3 zuno-worker, m5a.4xlarge | 6.66 | ~4,860 |
| ADR-0614, as rolled out | 3 masters + 3 zuno-worker (m5a.4xlarge) + 3 infra (m5a.2xlarge) | 6.24 | ~4,555 |
| ADR-0614 plan, if P6 had passed | masters at m5a.2xlarge | 4.99 | ~3,640 |

Spot workers add about 0.23 per hour each, only while the autoscaler keeps them. Compared with the morning, the layout costs about
2.08 more per hour (+50%). That buys a control plane that no longer saturates, three zones for workers and infra, and room for
the e2e canaries. Compared with the emergency layout it saves about 0.42 per hour. The plan's -25% assumed smaller masters, which
P6 refused. EBS root volumes add about 1,050 GB of gp3 in total.

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
  pods Pending by design, then uncordon. **Not run: the owner dropped it on 2026-11-14.**

## Owner decisions after closure (2026-11-14)

- No AZ drill (see Acceptance).
- a2a-gateway and Limitador stay at one replica for good; the shared-store follow-ups are dropped. a2a-gateway's
  PodDisruptionBudget is now `maxUnavailable: 1`, so drains no longer wait for someone to delete the pod; Limitador has
  no budget. Keycloak `zuno-0` keeps `minAvailable: 1` and still needs the manual delete during a drain.
- The inoperative `restore_command` block (616890dd) is removed from the PostgreSQL chart: PGO ignored it. The
  workaround for a replica stuck on pgBackRest's "duplicates found" is in
  [operations.md](../../platform/operations.md#a-postgresql-replica-stuck-in-archive-recovery).
