# WP-117: Kueue GPU quota and the first queued workloads

- **State:** Not started (2026-09-02)
- **ADRs:** [ADR-0538](../../adr/0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md)
  (decisions 3 and 5), [ADR-0321](../../adr/0321-delegate-kueue-lifecycle-to-the-red-hat-build-of-kueue-operator.md)
  (the installation whose GPU precondition this discharges),
  [ADR-0351](../../adr/0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md)
  (the MIG topology the quota must match)
- **Depends on:** WP-109/WP-113 (the evaluation Jobs that become the first queued consumers)
- **Related:** WP-115, WP-116

## Goal

The dashboard's Workload metrics page says "Configure the project queue", and it is right:
Kueue has been installed and reconciling since ADR-0321 and has **never admitted a single
workload**. Three gaps, all closed here:

- no zuno namespace carries `kueue.openshift.io/managed`, so the admission webhook never sees
  anything (the lone LocalQueue in `zuno-ai-build` is dormant by construction);
- the ClusterQueue covers cpu/memory only, and the `nvidia-gpu-flavor` ResourceFlavor has an
  empty spec - it selects no node. ADR-0321's own text required GPU flavor/quota "before ...
  queued model workloads are enabled"; that precondition was never discharged;
- nothing opts in, so there is nothing to show.

This WP completes the GPU quota against the real MIG topology and makes the TrustyAI evaluation
Jobs the first genuinely queued, admitted workloads.

## Steps

### Step 1 - GPU ResourceFlavor and ClusterQueue quota
New `gpu-mig` ResourceFlavor with real `nodeLabels` (`machine.startx.io/group: gpu`) and the
GPU nodes' soft taint toleration. ClusterQueue gains a **second resourceGroup** for
`nvidia.com/mig-1g.24gb` (nominal 4) and `nvidia.com/mig-2g.48gb` (nominal 2) - the live
cluster-wide totals - kept separate from the cpu/memory group because a Kueue resource may
belong to only one group. Note `nvidia.com/gpu` allocatable is **zero** on these nodes:
quotaing it would gate nothing.

Quota re-read live 2026-09-03 before authoring, and it matched: both
`machine.startx.io/group=gpu` nodes allocate `mig-1g.24gb: 2` + `mig-2g.48gb: 1`, giving the 4
and 2 above, with `nvidia.com/gpu: 0` confirmed on both.

**ADR-0351's taint belongs in `spec.tolerations`, not `spec.nodeTaints`.** `oc explain
resourceflavor.spec` states that only `NoSchedule` and `NoExecute` are evaluated during
admission and that `PreferNoSchedule` is *ignored* - and the GPU taint is exactly
`nvidia.com/gpu=true:PreferNoSchedule`. Declared as a `nodeTaint` it would have been silently
inert. As a toleration it is not: Kueue injects it into the admitted Workload's pods, so the
soft preference keeps working for a queued GPU consumer, and nothing needs revisiting if that
taint is ever hardened.

### Step 2 - LocalQueue and namespace opt-in
LocalQueue `default` rendered per configured namespace (`zuno-ai-build` keeps its existing one,
`zuno-ai-run` gains one - name `default` matches the DSC's `defaultLocalQueueName`, so the
dashboard auto-detects it). Namespace label `kueue.openshift.io/managed: "true"` on
`zuno-ai-run` via the namespaces chart - **and on `zuno-ai-build` too**: it has carried a
LocalQueue since ADR-0321 without ever carrying the label, so that queue could never have
admitted anything. Labelling it is free (nothing there sets a queue-name) and removes a
standing inconsistency. `zuno-mlops` deliberately gets neither: the operand integrates the
`BatchJob` framework only, and its workloads are KFP-launched Pods.

### Step 3 - opt the evaluation Jobs in
`kueue.x-k8s.io/queue-name: default` on the **Job** metadata of `garak-smoke`,
`garak-security` and `ragas-eval`, behind a values flag so it is revertible without a template
edit. Safe by construction: the operand runs `manageJobsWithoutQueueName: false`, so every
other Job in the namespace is untouched.

**The flag ships empty (unqueued), and turning it on is a deliberate operator action.** All
three Jobs carry `argocd.argoproj.io/sync-options: Replace=true,Force=true` - they must, a
Job's `spec.template` is immutable - so *any* change to their rendered metadata deletes and
recreates all three and re-pulls their images, Garak's alone being 4.22 GiB. A peer session
measured exactly that pattern on the models chart's prefetch Jobs the same day: 22 seconds
from Replace-recreation to `EvictionThresholdMet` on a control-plane node already at 85% image
-filesystem usage ([[diskpressure-master-cascades-into-mesh]], commit `6c55a5b7`). Shipping the
label on by default would have made the *push itself* the trigger, on a cluster whose etcd
nodes have the smallest disks and are schedulable. Empty-by-default separates "the code is
merged" from "the churn happens", so the second can be timed.

There is an upside worth stating: once queued, these three Jobs are serialised through a quota
instead of all landing at once. The disk-pressure incident is a churn problem, so this WP is
plausibly a small part of the remedy rather than a contributor to it.

### Step 4 - the training-jobs dashboard flag
`trainingJobs: true` on `OdhDashboardConfig` (live patch - operator-created CR, ADR-0538
decision 5). No workload moves off KFP; this only makes the page usable.

## What NOT to touch

- KFP training pods - not queueable here (BatchJob-only integration), and ADR-0526's
  burst-node/scale-from-zero placement must not be disturbed by admission gating.
- The existing `ResourceFlavor/default` - the GPU flavor is additive; mutating the cpu/memory
  flavor would re-quota every future consumer.
- Any Job without the queue-name label - opt-in is the safety property of this design.

## Verification checklist (operator step - ask before running)

1. `oc get clusterqueue default -o yaml` shows both resourceGroups and `Active`;
   `oc get resourceflavor gpu-mig -o yaml` shows the nodeLabels.
2. `oc get localqueue -A` lists `zuno-ai-run` (Active); `oc get ns zuno-ai-run --show-labels`
   carries `kueue.openshift.io/managed=true`.
3. After a `trustyai-config` sync: `oc get workloads -n zuno-ai-run` shows Admitted workloads,
   the Jobs still complete normally, and the dashboard's Workload metrics page is non-empty.
4. `make d3 check trustyai-config` still green; no unrelated Job in `zuno-ai-run` gained a
   `suspend` field.

## Risks and known unknowns

1. **A suspended Job reads as Progressing to ArgoCD.** With free quota, admission is
   sub-second; a mis-sized ClusterQueue would surface as a stuck sync - visible, not silent,
   which is the correct failure mode but worth recognizing quickly.
2. `activeDeadlineSeconds` is safe: a suspended Job has no `startTime`, and the Job controller
   resets it on unsuspend, so the 1800s/3600s budgets start at admission.
3. Whether the mesh sidecar's requests count toward the admitted Workload's usage is **open,
   and was asserted here without proof**. Kueue's webhook builds the Workload from the Job's
   pod template, while istio injection is a pod-creation webhook - so the sidecar plausibly is
   NOT counted, which would mean real usage exceeds admitted usage. Read the Workload's
   `spec.podSets[].template` at verification time and record the answer rather than assuming
   it. Either way it is not a sizing risk here: the three Jobs request 1.25 CPU / 2.5Gi in
   total against an 8 CPU / 32Gi quota, so even a 3x undercount admits comfortably.
4. Stray live ResourceFlavors `default-flavor` and `nvidia-gpu-flavor` (empty spec, not in git,
   unreferenced) should be deleted once confirmed unused - cleanup, not a blocker.
5. GPU quota interacts with ADR-0351's scale-from-zero if a GPU workload is ever queued: a
   Workload waits Suspended for quota while the autoscaler only reacts to Pending pods. No
   current consumer requests GPU through the queue, so this is documented, not exercised.

## Status updates (once live-verified)

- `State` moves to `Done` once the checklist passes, with at least one real admitted workload
  visible on the Workload metrics page.
