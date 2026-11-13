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
| P1 | AppProject applied (`oc apply -k ansible/roles/argocd/kustomize/appproject`, only the 4 additions in the diff), then `make d0 install machines` (rc 0): infra pool 3/3 updated, `zuno-infra-a/b/c` Ready in 1a/1b/1c with the taint and only DaemonSets on them, Spot sets at 0 with their autoscalers; GPU sets untouched (`zuno-gpu-a` 2/2, `zuno-gpu-c` still in 1b) | 3 new nodes | Done 2026-11-13 ~17:35Z |
| P2 | Moved, one at a time, each followed by a check: image registry (c49307d3), router (c8540cab, console 200 throughout), platform monitoring (d485ec4a + cbb91a60), UWM (81ea151e), GitOps (74b9c627 + 9afa3826), Quay (5e528e55; registry outage 18:54:50-18:58Z). Golden path 13/13 PASS and `check_recovery.py` all ok after the phase. Incidents below | rolling moves | Done 2026-11-13 19:05Z |
| P3 | ai-gateway and mcp-gateway at 2 replicas, spread over zones (bb1d86d7; ai-gateway already counts quotas in Redis on demo333); MaaS gateway (Istio deployment through `maas-gateway-config`) and Authorino at 2 (1d458f75; MaaS answered 401 throughout); maas-api stays at 1 (its owner, the MaaS `Config` CR, has no replicas field), Limitador at 1 (in-memory counters), a2a-gateway at 1 (in-memory tasks); right-sizing pushed (6804be49): PGO rolled the 3 instances, Patroni 3/3 TL 54 with s7tr as leader, Quay rolled without losing health. The golden path then read the ai-gateway log from one pod only: fixed to read every replica (74da3555). Golden path 13/13, `check_recovery.py` all ok | brief rolls | Done 2026-11-13 19:30Z |
| P4 | `zuno-worker-a/b/c` replaced one at a time by 200 GB machines (surge to 2, mark the old Machine `delete-machine`, scale to 1: MAPI drains it); Keycloak `zuno-0` deleted twice when it was the only pod left (PDB, ADR-0101), discovery back to 200 within a minute. Both `unifai-worker-a` nodes drained and retired, MachineSet deleted (13.4 vCPU / 27 GiB of requests moved, 0.2 vCPU zone-a-pinned). A fresh node pulled the NeMo Guardrails image from registry.redhat.io in ~9 min, so the first golden path failed on guardrails; 13/13 PASS once it started. `check_recovery.py` all ok | drains | Done 2026-11-13 20:50Z |
| P5 | Pods deleted in three waves (non-GPU pods off the GPU node; first of each pair and stateless pods off the masters; second of each pair and single stateful pods: Vault, MongoDB, the Redis instances, a2a-gateway, Limitador). Vault now auto-unseals (AWS KMS) and came back unsealed. Two pods were missed because the wave files had no final newline (`while read` skips the last line) and were deleted by hand; `unifai-rag-celery` landed back on the GPU node with "failed to prepare subPath" and was recreated. End state: masters run only control-plane pods pinned to them, DaemonSets and one RHOAI pod that tolerates the master taint (`data-science-prometheus-cluster-proxy`); GPU nodes run only the 5 model pods and DaemonSets. Golden path 13/13, `check_recovery.py` all ok | pod moves | Done 2026-11-13 21:15Z |
| P6 | Masters to m5a.2xlarge through the ControlPlaneMachineSet, only if the 7-day peak per master is at or below 22 GiB **and** 5.5 vCPU; window of at least 2 h | control-plane roll | Not started |
| P7 | `check_recovery.py`: infra pool and unschedulable masters; final cost table | none | Not started |

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
largest platform images into Quay (ADR-0612 family d, IDMS) would shorten every future node replacement.

## P6 gate: CPU as well as memory (measured 2026-11-13 17:40Z)

With every workload off it, master ip-10-18-28-96 still used ~7.2 vCPU: kube-apiserver 3.7, kube-controller-manager
(the elected leader) 2.1, openshift-apiserver 0.8, etcd 0.6. An m5a.2xlarge has 8 vCPU (~7.5 allocatable). P6 therefore
also needs the 7-day CPU peak per master at or below 5.5 vCPU; otherwise the masters stay m5a.4xlarge.

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
