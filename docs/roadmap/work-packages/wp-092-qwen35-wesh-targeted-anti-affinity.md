# WP-092: Targeted anti-affinity between qwen3.5-9b and its wesh fine-tune

- **State:** Done (live-verified 2026-08-29)
- **ADRs:** ADR-0414 (amended 2026-08-29: model set refresh, MIG re-profiling investigated and
  rejected, this anti-affinity change recorded)
- **Depends on:** WP-086 (introduced the `spreadAcrossGpuNodes` soft anti-affinity mechanism this
  WP extends), WP-087/ADR-0526 (the `qwen35-9b-wesh` model this WP targets)
- **Related:** WP-083 (the two permanent MIG nodes, `zuno-gpu-a`/`zuno-gpu-c`, both `all-balanced`,
  unchanged by this WP)

## Goal

`qwen35-9b-kserve` and `qwen35-9b-wesh-kserve` (the unmodified Qwen3.5-9B base and its French
urban-register LoRA fine-tune, served side by side per ADR-0526 decision 4 so the variant can be
compared against its own base) have always landed on separate nodes in practice, but never by
design: `gitops/charts/models/values.yaml`'s own PLACEMENT comment documents that this is an
accident of MIG slice availability — each model happens to take the last free slice of its size.
Nothing expresses the intent that they *should* be separated, so a future capacity or scheduling
change could silently put both on the same node with no signal that anything changed.

A related, larger request (repartition `zuno-gpu-a`/`zuno-gpu-c` to `2x mig-2g.48gb`, matching a
misremembered `zuno-gpu-burst-a` config) was investigated as part of this WP and rejected — see
`## Investigated and rejected: MIG re-profiling` below and ADR-0414's 2026-08-29 amendment. No
machineset change is in scope; this WP is anti-affinity only.

## What changed

### Targeted soft anti-affinity

`gitops/charts/models/templates/llminferenceservice-qwen35.yaml` and
`llminferenceservice-wesh.yaml` each gain a second
`preferredDuringSchedulingIgnoredDuringExecution` term (weight 100, same list as WP-086's
existing generic `kserve.io/component: workload` term) naming the *other* model's pod directly via
`app.kubernetes.io/name` — a label the `LLMInferenceService` controller sets from the resource
name, confirmed live before writing this:

| Template | New term's selector | Renders to |
|---|---|---|
| `llminferenceservice-qwen35.yaml` | `app.kubernetes.io/name: .Values.weshModel.inferenceServiceName` | `qwen35-9b-wesh` |
| `llminferenceservice-wesh.yaml` | `app.kubernetes.io/name: .Values.qwen35Model.inferenceServiceName` | `qwen35-9b` |

Both are gated by the existing `spreadAcrossGpuNodes` toggle, no new values flag. Referenced via
`.Values.weshModel.inferenceServiceName` / `.Values.qwen35Model.inferenceServiceName`, not a
hardcoded string, so a future rename of either `inferenceServiceName` stays consistent.

**Kept soft, not `required`.** ADR-0351 decision 1 and WP-086 both chose packing onto a surviving
node over leaving a pod `Pending` when only one node is available; WP-086 also recorded a live
finding that `preferredDuringSchedulingIgnoredDuringExecution` is evaluated once, at scheduling
time, against pods already placed — it does not re-evaluate as other pods move, so this term
narrows the odds of co-location without guaranteeing separation on every rollout. This is a known,
accepted property of the mechanism, not a gap specific to this change.

Comments updated in both templates and in `values.yaml`'s PLACEMENT block to stop describing the
separation as purely a slice-availability accident.

## Investigated and rejected: MIG re-profiling

The original request also asked to repartition `zuno-gpu-a` and `zuno-gpu-c` to `2x mig-2g.48gb`
(dropping the `1g.24gb` slices), believing this matched `zuno-gpu-burst-a`'s existing profile.
Checked live and in `gitops/charts/machines/values.yaml`:

- `zuno-gpu-a` and `zuno-gpu-c` already carry the **identical** MIG profile today
  (`all-balanced` = 2x `mig-1g.24gb` + 1x `mig-2g.48gb`), since WP-083. No alignment work needed.
- `zuno-gpu-burst-a` has **no MIG at all** (`nvidia.com/mig.config: all-disabled`, whole 96GB GPU)
  — not `2x mig-2g.48gb`. This is deliberate: it is the only way the ClusterAutoscaler can predict
  its capacity and scale it from zero, since `nvidia.com/mig-*` capacity for a not-yet-created node
  cannot be inferred by the autoscaler in this repo's current setup.
- A `2x mig-2g.48gb` profile on `zuno-gpu-a`/`zuno-gpu-c` would drop total slice capacity from 6 to
  4, below the 5 models currently served. The only way to make up the gap — giving
  `zuno-gpu-burst-a` a permanent MIG profile too — fails on two independent grounds: it is a
  `g7e.2xlarge` (8 vCPU), the same instance type ADR-0414's own Context section already documents
  as unable to drive a 3-slice partition, and any MIG profile at all forces it off scale-from-zero
  onto a permanent, always-on node — removing the only on-demand full-GPU node this repo has for
  training (WP-087's fine-tune ran there).

Decision: no machineset change. `all-balanced` stays on both permanent nodes, capacity unchanged
at 6 slices for 5 workloads (1 spare). Recorded in ADR-0414's 2026-08-29 amendment so this path
isn't re-investigated from scratch later.

## Live finding: the rollout re-tripped WP-082's quota deadlock, on both models at once

Pushing the templates (`00b9da49`) let `zuno-models-d1` sync the two `LLMInferenceService` CRs
immediately, but both underlying Deployments then sat with `0 of 1 new replicas updated`
indefinitely — the exact failure WP-082 already recorded: `zuno-ai-run-gpu-cap` caps each MIG
profile at precisely the steady-state count (`mig-1g.24gb: 3/3`, `mig-2g.48gb: 2/2`), and
`RollingUpdate` at `replicas: 1` needs a surge pod *before* removing the old one. Both new
ReplicaSets looped on `FailedCreate: exceeded quota` (`qwen35-9b-kserve-5cd599dc74` and
`qwen35-9b-wesh-kserve-9f899c5f8`). Unblocked with WP-082's own escape hatch —
`oc scale rs qwen35-9b-kserve-54ccf6d57d --replicas=0` and the equivalent for wesh's old RS —
which freed one slice of each profile and let the new ReplicaSets create their pods. Both old
pods were healthy and serving right up to the scale-to-0, so the interruption was exactly the
time for the new pod to become `Ready` (no `Pending` window during this half — quota was the
only blocker, and clearing it let the scheduler place normally).

**This will recur on every future spec change to either template** as long as the quota stays
saturated at 5/5. Worth a WP of its own if these two models are edited often; out of scope here.

## Live finding: the decisive check exposed a real, already-accepted survivability gap

Ran Check 5 exactly as planned: cordoned `ip-10-18-15-25` (held `qwen35-9b-kserve`, 1 free
`mig-1g.24gb` slot alongside `qwen36-27b-instruct-kserve`), deleted the pod. It did **not**
reschedule within a minute the way WP-086's Check #9 did for `gpt-oss-20b` — it sat `Pending`
for the full test:

```
FailedScheduling: 0/6 nodes are available: 1 Insufficient nvidia.com/mig-1g.24gb,
1 node(s) were unschedulable, 4 node(s) didn't match Pod's node affinity/selector.
```

Root cause has nothing to do with the new anti-affinity term — the reason is capacity, not
placement preference. The would-be survivor, `ip-10-18-67-65`, already runs `embeddings`,
`gpt-oss-20b-kserve` and `qwen35-9b-wesh-kserve` at exactly 3/3 slices; the cluster's one spare
`mig-1g.24gb` slot lived on `ip-10-18-15-25` itself, the node just cordoned. WP-086's "packing
onto a survivor" property held when a node's failure left slack elsewhere; it does not hold here
because the spare slice and the cordoned node were the same place. This is precisely the risk
`gitops/charts/models/values.yaml`'s WP-087 comment already named — "the survivability property
no longer holds at five workloads across six slices" — now confirmed empirically rather than
just asserted. **The soft term itself behaved correctly**: nothing was blocked by `required`,
and once schedulable again the pod returned to exactly the same node.

Recovered: `oc adm uncordon ip-10-18-15-25` at 20:36:04, pod `Ready` at 20:39:44 (created
20:34:21) — end to end 5m23s from delete to serving, of which ~1m42s was genuinely
unschedulable and the rest was normal cold-start (S3 model pull + vLLM init, consistent with
WP-086's own cold-start timings). The pod landed back on `ip-10-18-15-25`, its pre-test node,
serving Check 6 (return-to-preferred-node) in the same action — no separate delete needed.

**Accepted, not remediated here.** WP-092's scope is the anti-affinity term, not the underlying
capacity headroom; fixing this needs either a 6th slice somewhere or accepting a single-model
outage window on whichever node happens to be lost. Recorded so it is a known trade-off the next
node-maintenance operator makes on purpose, not a surprise mid-drain.

## Verification checklist

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | `helm template gitops/charts/models` | Both new terms render with the correct cross-referenced model name, no syntax error | ✅ |
| 2 | `python3 platform/docs/check_docs.py` | Passes | ✅ |
| 3 | `oc get pods -n zuno-ai-run -o wide` after rollout | `qwen35-9b-kserve` and `qwen35-9b-wesh-kserve` on 2 different nodes | ✅ `ip-10-18-15-25` / `ip-10-18-67-65` |
| 4 | `oc get pods -n zuno-ai-run -o wide` | `embeddings`, `gpt-oss-20b-kserve`, `qwen36-27b-instruct-kserve` unaffected | ✅ untouched, ages confirm no restart |
| 5 | Decisive check: cordon + delete | Reschedules onto the survivor without `Pending` | ⚠️ term stayed soft as required, but went `Pending` ~1m42s on real capacity exhaustion — see live finding above |
| 6 | Uncordon, confirm return to preferred node | Returns to its preferred (separated) node | ✅ (same action as recovery above) |

Check 5's result is not a regression in this change — it is real information the change's own
verification step surfaced about the fleet's current headroom, exactly the kind of thing this
check exists to catch.

## Status updates

- 2026-08-29: templates, `values.yaml` comments, ADR-0414 amendment, WP-092 written (`00b9da49`),
  pushed, `zuno-models-d1` synced. Both rollouts hit and cleared the WP-082 quota deadlock.
  Steady-state placement confirmed separated. Decisive check run live — soft term confirmed
  correct, and surfaced the zero-headroom finding above. `python3 platform/docs/check_docs.py`
  passes.
