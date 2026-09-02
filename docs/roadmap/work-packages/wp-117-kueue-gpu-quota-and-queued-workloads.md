# WP-117: Kueue GPU quota and the first queued workloads

- **State:** Not started — quota built and live-proven, but **both opt-ins were reverted on
  2026-09-03** after the live run exposed a design defect (see Live findings). The
  ResourceFlavors/ClusterQueue/LocalQueues remain applied and are inert without the namespace
  label; steps 2-3 need a design decision before they can be re-attempted
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

## Live findings (2026-09-03, first execution attempt)

Steps 1 and 4 succeeded and are still live. Steps 2 and 3 were applied, observed, and reverted
within about fifteen minutes (`b4629b56`, `b5730c53`, reverted by `2f36accd`). Two findings, the
second serious enough that it should be read before anyone re-attempts this WP.

1. **A Kueue-managed Job and `argocd.argoproj.io/sync-options: Replace=true` form a recreation
   loop.** On admission Kueue injects
   `kueue.x-k8s.io/{cluster-queue-name,local-queue-name,podset}` into the Job's
   **`spec.template.metadata.labels`**. ArgoCD reads that as drift from the rendered manifest,
   `selfHeal` syncs, `Replace=true` deletes and recreates the Job, Kueue admits it and injects
   again. Observed live: `garak-security`'s Workload was recreated eight or more times in five
   minutes (`ccd32`→`05310`→`9a251`→`0d682`→`1ed9a`→`6fbfd`→`8ca31`→`f7ff7`→`d2e71`) and
   `zuno-trustyai-config-d1` never reached `Synced`. **Every iteration re-runs the Job**, so the
   loop costs an image pull and a full workload execution per turn.
   The Replace annotation is not removable on a whim - a Job's `spec.template` is immutable, which
   is why all three carry it. So this is a genuine incompatibility, not a misconfiguration.

2. **`kueue.openshift.io/managed` is not the per-workload opt-in this WP assumed.** The operand's
   config really does say `manageJobsWithoutQueueName: false`, and its
   `managedJobsNamespaceSelector` really does match that label - both read live from
   `kueue-manager-config`. What neither says is that the operator **auto-stamps
   `kueue.x-k8s.io/queue-name: default` onto every Job created in a labelled namespace**, taking
   the value from the DSC's `defaultLocalQueueName`. Labelling the namespace therefore enrolled
   *everything* in `zuno-ai-run` and `zuno-ai-build`, not the three Jobs this WP intended.
   Proof: `qwen35-9b-mmlu-cache-prefetch` (owned by `zuno-models-d1`, no queue-name anywhere in
   its chart) came back carrying the label, and all three `*-mmlu-cache-prefetch` Jobs had
   Workload objects. Those Jobs also carry `Replace=true` and pull multi-GB LMEval images, so
   finding 1 was about to apply to them - the same churn mechanism as the DiskPressure cascade
   being tracked in [[diskpressure-master-cascades-into-mesh]].

   Two peer sessions had been told, on the strength of the `manageJobsWithoutQueueName` reading,
   that their Jobs could not be affected. That assurance was wrong and was corrected to both.
   State the trap this way round: **the flag is genuinely `false`, and that is still not
   sufficient** - the auto-stamping webhook is a second, separate mechanism the flag says
   nothing about.

3. **Reverting the chart does not un-enroll a namespace, for two compounding reasons.**
   First, the labels are not owned by ArgoCD - they appear in no `managedFields` entry on either
   Namespace, so removing them from the chart leaves both Applications `Synced/Healthy` while the
   labels sit there indefinitely. Second, the operator **mirrors `kueue.openshift.io/managed`
   into a plain `kueue-managed` label** that no chart in this repo declares, so clearing only the
   documented key leaves the namespace enrolled. Both must go together:
   `oc label ns zuno-ai-run zuno-ai-build kueue-managed- kueue.openshift.io/managed-`.
   And because the webhook stamps at Job *creation*, an already-stamped Job keeps its label until
   it is recreated - for a `Replace=true` family that is the next sync, for anything else
   possibly never.

4. **Job duration decides whether this defect is visible at all.** A peer's three prefetch Jobs
   were enrolled by the same label, admitted at the same moment, and never looped: they completed
   in ~36 seconds, and a Complete Job stops being mutated, so ArgoCD saw no drift to heal. The
   three evaluation Jobs here carry 1800-3600s deadlines and stayed mutable throughout. Same
   configuration, opposite outcome - so a fast Job masks this entirely and a slow one exposes it.
   Do not read "our other queued Jobs were fine" as evidence the design is safe.

**What this means for the design.** "Opt-in per workload" is not available at the namespace
level on this operator: the unit of opt-in is the namespace, and everything in it comes along.
So step 3's values flag is not the safety property it was written to be. A re-attempt needs one
of: `ignoreDifferences` on `/spec/template/metadata/labels` for every `Replace=true` Job in a
managed namespace (fragile - it must cover charts this WP does not own); dropping `Replace=true`
where Kueue manages the Job and accepting manual recreation; or a dedicated namespace for queued
evaluation work so the namespace-wide enrolment matches the intent. That is a real design
decision and is deliberately left open rather than patched live.

**Cluster impact of the attempt: transient and bounded.** Three evaluation Jobs ran a handful of
extra times over roughly ten minutes. Node filesystems were unchanged afterwards (masters
60-68%, DiskPressure `False` on all six nodes), because the garak digest was already cached on
the nodes involved.

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
- **2026-09-03 - partially applied, then reverted.** What stands: the `gpu-mig` ResourceFlavor
  and the second `resourceGroup` (ClusterQueue `Active`, "Can admit new workloads", both groups
  present), LocalQueue `default` in both namespaces, and step 4's `trainingJobs: true` on
  `OdhDashboardConfig` (the CRD's own flag names, read live: `trainingJobs` enables, while
  `disableKueue`/`disableDistributedWorkloads` are separate and both left unset). All of that is
  inert without the namespace label, so it is safe to leave applied.
  What was reverted: the namespace labels and the queue-name flag, per the Live findings above.
  Admission itself was proven to work before the revert - all three evaluation Jobs reached
  `Admitted=True` within seconds of the sync - so the quota half of this WP is sound. It is the
  enrolment model, not the quota, that needs redesign.
