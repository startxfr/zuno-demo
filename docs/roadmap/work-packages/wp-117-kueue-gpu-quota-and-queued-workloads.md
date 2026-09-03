# WP-117: Kueue GPU quota and the first queued workloads

- **State:** Done — live-verified 2026-09-03 on demo222, on the **second** attempt. The first was
  applied and reverted within the hour; the second closed the recreation loop first, then
  re-enrolled. All three evaluation Jobs are queued, admitted and completed, both owning
  Applications sit `Synced/Healthy`, and the ClusterQueue is deliberately undersized so it
  serialises multi-GiB image pulls
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

## Live findings (2026-09-03 local / 2026-09-02 22:5x-23:4x UTC, first execution attempt)

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

**Cluster impact of the attempt: real but bounded.** Three evaluation Jobs ran a handful of extra
times over roughly ten minutes. Measured before and after on every node: the busiest master went
68.0% -> 71.5% of its filesystem (28.3 GiB still free) and a second went 68.3% -> 68.9%; the rest
were flat, and DiskPressure stayed `False` on all six throughout. So the loop did cost disk -
about 3.5 GiB on the node that mattered - and would have kept costing it indefinitely had it not
been stopped. The reason it was not worse is that the garak digest was already cached on the
nodes involved; a cold cache would have paid 4.22 GiB per iteration, on nodes with roughly 30 GiB
of headroom.

## Live findings (2026-09-03, second attempt — the one that worked)

1. **There is no per-workload opt-out on this operator build.** `Kueue.spec.config.
   workloadManagement.labelPolicy` looks like the control (`None` = "suspended on creation and a
   label added via a mutating webhook", `QueueName` = "without the label Kueue ignores the
   workload"). It is not. Proven in a throwaway namespace rather than argued from documentation:
   an empty namespace was labelled, a bare busybox Job was created and came back stamped with an
   Admitted Workload; `labelPolicy: QueueName` was then set explicitly and the identical Job was
   **still stamped**. `mjob.kb.io` enrols every Job created in a labelled namespace regardless.
   **Do not retry this setting.** It is pinned anyway (commit `28295875`) because `oc explain`
   says an unset value lets the operator pick a default "subject to change over time".

2. **Labelling a namespace does three things, not one.** Within seconds of labelling an empty
   namespace: the label is mirrored to a plain **`kueue-managed`** key that no chart declares;
   a **LocalQueue named `default` is auto-created**, owned by `platform.opendatahub.io/part-of:
   kueue`; and Jobs created afterwards are stamped. The LocalQueue's owner is the DSC's Kueue
   component **whose `managementState` is `Unmanaged`** — so Unmanaged does not mean inert here.

3. **The rendered controller config actively misleads.** `kueue-manager-config` reports
   `manageJobsWithoutQueueName: false` — the QueueName semantic — while the webhook stamps
   anyway. Controller config and webhook behaviour are separate mechanisms; reading the former
   tells you nothing about the latter. This is the single sharpest trap in this WP.

4. **The recreation loop is real and `RespectIgnoreDifferences=true` is the load-bearing half.**
   `ignoreDifferences` alone suppresses only the OutOfSync display while `Replace` still fires —
   the loop keeps running behind a green Application, which is worse than the loud version. Five
   pointers were needed: `queue-name` on the Job's own metadata, `spec.suspend`, and the three
   `kueue.x-k8s.io` pod-template labels. `spec.suspend` is not optional once the quota is
   undersized, because suspended is then a Job's normal resting state.

5. **A second, independent loop was hiding behind the first — and it was self-inflicted.** With
   the Kueue drift ignored, `garak-smoke` and `ragas-eval` went stable immediately while
   `garak-security` kept recreating every ~90s. The cause was not Kueue at all: WP-113's own
   commit `117c48e3` had inserted a `volumes:` block directly above the container's `resources:`
   block and silently reparented it, so the rendered manifest carried a `resources` key **inside
   a volume entry**. The API server drops it, the manifest can never match the live object, and
   `Replace=true` turns that into a permanent recreation loop that re-ran the scan and re-pulled
   a 4.22 GiB image on every reconcile. Fixed in `02a7f810`.
   Two consequences: the container had been running with **no requests or limits at all**, so the
   500m/1Gi figure this WP used for sizing was never in effect; and this very likely explains a
   peer session's measurement that `zuno-ai-run`'s image-pull rate did **not** fall after the
   first Kueue revert — a second loop was running the whole time, and Kueue was never its only
   source. The lesson generalises: the indentation is legal YAML and reads as if it belongs to
   the container, so review will not catch it. A permanently `OutOfSync` Application with
   `Replace=true` is the symptom to watch for.

6. **The istio sidecar does NOT count toward admitted usage** — correcting this WP's earlier
   assertion, which was made without proof. Kueue builds the Workload from the Job's pod
   template while injection happens later at pod creation, so `garak` admits as exactly
   `500m/1Gi` in a mesh-injected namespace. Read live off `status.admission.podSetAssignments`.

7. **The enrolled set was larger than this WP's inventory.** Four `zuno-day2-stresstest-*` Jobs
   were queued alongside the six `Replace=true` ones. They carry no `Replace` annotation so they
   cannot loop, but they do consume quota — which is why the quota is sized against them too.

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
3. ~~Whether the mesh sidecar's requests count toward the admitted Workload's usage~~ —
   **RESOLVED: it does not** (Live finding 6). Admitted usage is the app container alone.
   Real node usage therefore exceeds admitted usage by the sidecar's requests, which is a
   deliberate accepted gap: the quota exists to bound image pulls, not to model node capacity.
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
- **2026-09-03 - Done (second attempt).** Commits: `28295875` (pin `labelPolicy`, which the gate
  then proved does not help - kept because the default is documented as unstable), `ac8cc889`
  (`ignoreDifferences` + `RespectIgnoreDifferences=true` on **both** owning Applications),
  `79ffa9bf` (re-enrol `zuno-ai-run` only), `02a7f810` (the orphaned `resources` block - a second
  loop that had nothing to do with Kueue), `91587315` (undersize the quota to 750m/1536Mi).
  Live: all four Applications `Synced/Healthy`, `zuno-trustyai-config-d1` stable for over ten
  minutes with all three Jobs queued, every evaluation Job `succeeded=1` and none suspended,
  ClusterQueue `Active` reporting "Can admit new workloads" with both resourceGroups, and
  `DiskPressure` `False` on all six nodes throughout.
  Two deliberate departures from the brief. `zuno-ai-build` is **not** labelled: with enrolment
  proven to be namespace-wide and unconditional, labelling a namespace that has no `Replace=true`
  Jobs and nothing to serialise buys nothing and only widens the blast radius, so its LocalQueue
  stays dormant. And the `queueName` values flag no longer decides whether the eval Jobs are
  queued - the namespace label does that alone - it now only makes the rendered manifest declare
  what the webhook adds anyway, so git states the truth.
  Coordination: `gitops/apps/models/application-d1.yaml` belongs to another work stream and was
  edited here because its three prefetch Jobs are enrolled by the same namespace label and would
  otherwise have entered the loop with multi-GiB images; its owning session was told before the
  commit landed.
  **Applying `gitops/apps/*` manifests is an Ansible job, not a git one** - a push does not update
  a live Application object. The two Applications here were brought forward with a targeted
  `oc patch` of `ignoreDifferences`/`syncOptions` only; a plain `oc apply -f` of the file would
  have wiped the Ansible-injected helm values (`zuno-models-d1` carries the vLLM image digest and
  the S3 model config that way).
