# WP-283: Check that a pod without a node selector schedules, for the UnifAI canary

- **State:** Not started
- **ADRs:** [ADR-0614](../../adr/0614-split-the-cluster-into-infra-general-worker-and-gpu-node-pools.md) (node pools)
- **Depends on:** [WP-260](wp-260-roll-out-the-infra-general-and-gpu-node-pools-on-demo333.md) (the pools on demo333)
- **Estimated files touched:** ~7 (a check playbook and its `make` target, a small chart for the rehearsal namespace with its Role, the runbook)

> Opened 2026-11-14. The owner validated the point the same day in the UnifAI review held with unifai-compare (drift point
> 4). The owner chose to plan it rather than build it that night. Planned before the UnifAI 0.1 freeze of 2026-12-01; the
> live proof needs the owner's go. unifai-main listed the canary's assumptions the same evening, from the fork's
> `Makefile`, `config/canary` and `test/e2e` and from this week's canaries on demo333.

## Why

The UnifAI fork's canary runs on demo333. Our cluster changes can break it while the release itself is fine:

- **Pools.** Since ADR-0614, `E2E_NODE_SELECTOR` is empty by default (fork e913fb0dd). Before that, `workload=unifai`
  matched no node, and every suite timed out after 30 minutes.
- **Disk.** The canary of the weekend of 2026-11-14 hit DiskPressure on a worker.
- **Other changes.** A taint, a quota, a new egress rule or an admission label on new namespaces would also break it.

Nothing on our side checks what the canary assumes.

## What the canary assumes

| # | Assumption | State on demo333, 2026-11-14 (read-only) |
|---|---|---|
| a | Pods with no node selector and no toleration schedule on any worker. | Not checked: this WP's check. |
| b | StorageClasses `gp3-csi` (RWO) and `nfs` (RWX, `E2E_SHARED_STORAGE_CLASS`) exist and provision. | Both exist (`gp3-csi` is the default) and the `nfs-provisioner` pod runs. Provisioning is not tested. |
| c | Images come from `quay.io/zuno`: application images by `devel-<sha>` tag, the operator by signed digest. The admission must accept them in `unifai-e2e-*` and `unifai-operator-canary`. | The `policy.rhtas.com` webhook only looks at namespaces labelled `policy.rhtas.com/include=true`: `unifai-operator`, `zuno-unifai` and `zuno-wp226-cip-test`. The canary namespaces are not checked. The `zuno-unifai-via-registry` ImageDigestMirrorSet uses `AllowContactingSource`, and tag pulls go to quay.io. |
| d | Internet egress from `unifai-e2e-*` for the full suite (`E2E_FULL=1`): the embedding service, documentation sites, the signed `quay.io/zuno/okf-tekos`. | Open. There is no AdminNetworkPolicy, no BaselineAdminNetworkPolicy and no project request template. EgressFirewalls exist only in eight named `zuno-*` namespaces. |
| e | `E2E_UPGRADE=1` needs the OLM operator instance installed. `E2E_KEYCLOAK=1` installs RHBK through OLM, then removes it. | The OLM instance runs (0.1.71). `redhat-operators` is `READY`. |
| f | The tester's account has cluster rights: CRDs, the canary operator's ClusterRole and ClusterRoleBinding, create and delete on namespaces, `system:auth-delegator` for the RAG test's tokenReview. | The fork's account, outside zuno's RBAC. Not checked here. |
| g | Capacity: a full suite takes about 45 minutes (Go timeout 180 minutes), and one e2e stack is heavy (RAG workers). | Three 200 GB workers plus the Spot pool this week. Disk and CPU headroom matters. |

Namespaces: the canary operator runs in `unifai-operator-canary`. It only reconciles objects labelled
`unifai.startx.fr/operator-instance=canary`, which the OLM instance ignores. Each e2e suite creates its own
`unifai-e2e-NNNNN` (five random digits) with a full UnifaiStack, then deletes it. `make canary-delete` removes the
`unifai-e2e-*` namespaces first and the canary last, because the stacks need the canary's finalizers.

## Content

1. **`make d2 check canary-ready`.** A fixed rehearsal namespace, `zuno-canary-ready`, owned by a small chart and
   shaped like a fresh `unifai-e2e-*`: no admission label, no EgressFirewall, no quota. In it:
   - (a) a throwaway pod with no node selector and no toleration; fail when it stays `Pending` past a timeout, and print
     the scheduler's event;
   - (b) one PVC on `gp3-csi` and one on `nfs`, mounted by that pod, both `Bound`;
   - (c, d) from the pod, pull a `quay.io/zuno` image by tag and send an HTTPS request to quay.io;
   - read-only checks for (c) to (e): neither canary namespace prefix carries `policy.rhtas.com/include`, no
     AdminNetworkPolicy or BaselineAdminNetworkPolicy, `redhat-operators` `READY`;
   - (g) report free disk and allocatable CPU on the general workers, with a warning below a threshold set with the
     fork's maintainers.
   Delete everything with `propagationPolicy: Background` or a TTL, so nothing is orphaned.
2. **Permissions.** The AAP check identity (`zuno-aap/aap-day0-check`) can only read. The chart gives it a Role in
   `zuno-canary-ready` only: create and delete on pods and PVCs (ADR-0354). It never gets namespace creation. Prove the
   check through AAP, not only with kube:admin.
3. **Runbook.** In `docs/platform/operations.md`, the table above, with the command that checks each row. Point (f) stays
   the fork's.

## Acceptance

- The check passes on demo333 through AAP.
- It fails with the scheduler's reason when the rehearsal namespace gets a pod quota of zero (negative test).
- No pod, PVC or Job is left behind.
- The runbook section exists, and unifai-main confirms that it matches the canary.
