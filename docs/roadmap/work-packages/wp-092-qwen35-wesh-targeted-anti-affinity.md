# WP-092: Targeted anti-affinity between qwen3.5-9b and its wesh fine-tune

- **State:** Repo work in review
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

## Verification checklist

| # | Check | Expected |
|---|---|---|
| 1 | `helm template gitops/charts/models` (or equivalent render) | Both new terms render with the correct cross-referenced model name, no syntax error |
| 2 | `python3 platform/docs/check_docs.py` | Passes — ADR-0414/WP-092 pairing and index consistent |
| 3 | `oc get pods -n zuno-ai-run -o wide` after rollout | `qwen35-9b-kserve` and `qwen35-9b-wesh-kserve` on 2 different nodes |
| 4 | `oc get pods -n zuno-ai-run -o wide` | `embeddings`, `gpt-oss-20b-kserve`, `qwen36-27b-instruct-kserve` unaffected by the rollout |
| 5 | **Decisive check (WP-086 Check #9 style):** cordon the node holding one of the pair, delete its pod | Reschedules onto the survivor in well under a minute, never `Pending` — proves the term stayed soft |
| 6 | Uncordon, delete the pod again | Returns to its preferred (separated) node — proves the preference still steers when it has a choice |

Check 5 is the one that actually proves the property that matters — 1 through 4 pass even if the
new term were silently a no-op or, worse, wrongly `required`.

## Status updates

- 2026-08-29: templates, `values.yaml` comments, and ADR-0414 amendment written. Not yet pushed /
  live-verified — see checklist above.
