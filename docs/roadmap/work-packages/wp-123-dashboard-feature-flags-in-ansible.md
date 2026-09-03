# WP-123: Reconcile the RHOAI dashboard feature flags from Ansible

- **State:** Done (2026-09-03) — applied and live-verified end to end (`check` found the
  drift, `reconcile` fixed it, a re-run was a no-op, a delete-a-flag drill proved
  self-healing), with operator sign-off on the `zuno-ai-run` UI
- **ADRs:** [ADR-0538](../../adr/0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md)
  (decision 5 amended here; decision 3 is the surface `disableKueue` unlocks),
  [ADR-0534](../../adr/0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md)
  (Operational considerations amended here)
- **Depends on:** none — [WP-115](wp-115-trustyai-dashboard-ui-flags-and-evalhub.md) and
  [WP-117](wp-117-kueue-gpu-quota-and-queued-workloads.md) already landed the flags by hand
- **Related:** [ADR-0517](../../adr/0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md) / [WP-118](wp-118-demo333-portability-blockers.md)
  — this is a tenth blocker of exactly that class, which WP-118 could not see because a
  cluster-only mutation leaves nothing in the repo to grep for

## Goal

Make the four RHOAI dashboard feature flags survive a from-scratch install, and fix the one
that was never applied at all.

## The problem

`OdhDashboardConfig/odh-dashboard-config` (`redhat-ods-applications`) gates whole dashboard
pages. Three flags were declared authoritative in prose — `disableLMEval: false`,
`guardrails: true` (ADR-0534/WP-115), `trainingJobs: true` (ADR-0538/WP-117) — and applied by
a human running `oc patch`. Nothing in `ansible/` or `gitops/` applied them: a repo-wide grep
returned only comments, and even the patch *body* was never written down (WP-115 step 1 records
the command without its payload, so without the `spec.dashboardConfig` path). On a new cluster
the operator recreates the CR with its own defaults and those surfaces silently vanish.

A fourth flag was missing entirely, and that is what surfaced this. The dashboard showed
**"Kueue is disabled in this cluster"** in `zuno-ai-run` only, with the "Deploy model" button
disabled and the hardware-profile list filtered to empty — while the Kueue operand was
`Available` with two ready replicas, `ClusterQueue/default` active and LocalQueues in place.

## What the dashboard bundle actually does

Read out of the running `rhods-dashboard` pod on 2026-09-03, because guessing here had already
cost one wrong diagnosis:

```js
// the hook behind the banner
const isProjectKueueEnabled = ns.metadata.labels["kueue.openshift.io/managed"] === "true";
const isKueueFeatureEnabled = useIsAreaAvailable(SupportedArea.KUEUE).status;
const isKueueDisabled       = isProjectKueueEnabled && !isKueueFeatureEnabled;
```

1. **Why only `zuno-ai-run`.** The banner keys on the namespace label, nothing else.
   `zuno-ai-run` is the only namespace carrying `kueue.openshift.io/managed=true` (deliberate,
   ADR-0538 decision 3 / WP-117). `zuno-ai-build` has a dormant `LocalQueue` and no label, so it
   shows nothing — the dashboard never looks at LocalQueues.
2. **The DSC was never the problem.** The KUEUE area is
   `{featureFlags:["disableKueue"], requiredComponents:["kueue"]}`, and the requiredComponents
   test accepts **both** `"Managed"` and `"Unmanaged"` managementState, so `kueue: Unmanaged`
   passes it. The obvious suspect was the wrong one.
3. **The real cause is the flag evaluator's order of operations:**

   ```js
   const s = (flag, state) => {
     if (undefined === state[flag]) return "off";      // <-- short-circuits FIRST
     return (flag.startsWith("disable") ? !state[flag] : state[flag]) ? "on" : "off";
   };
   ```

   An **undefined** key returns `"off"` *before* the `disable*` inversion is applied, and the
   dashboard backend's own fallback is `disableKueue: true` besides. So absent ≠ false, and
   nothing but an explicit `false` in the CR turns the area on. The CRD declares no `default:`
   for any flag either — deleting a key to "let the operator decide" disables the surface.
4. **Blast radius beyond the banner:** `isKueueDisabled` also feeds the "Deploy model" button's
   `isAriaDisabled`, and `kueueFilteringState` goes to `NO_PROFILES`, which filters the hardware
   profile list to `[]`. A UI-only block — GitOps and CLI submission were never affected.

## Why this is Ansible and not GitOps

The CR has no `ownerReferences` and **three** concurrent writers, read off `managedFields` live:

| manager | owns |
|---|---|
| `manager` (RHOAI operator) | `spec.dashboardConfig.disableTracking`, `notebookController`, `templateOrder` |
| `kubectl-patch` (a human) | the three hand-applied flags |
| `unknown` (the dashboard UI) | `spec.hardwareProfileOrder`, `spec.modelServing` — written at runtime |

Every Application in this repo runs `prune: true, selfHeal: true`, so ArgoCD ownership would
revert an admin's own UI actions. The usual escape hatch is worse: a blanket
`ignoreDifferences: /spec` is the false-green trap this repo has already hit three times (DSC
`/spec`, MachineSet `/spec/replicas`, Kiali's subtrees), `Replace=true` on a CR produced a
recreation loop (WP-117), and `ServerSideApply` is used exactly once, on the manual-bootstrap
root app, never on an operand. The repo's established answer for an operator-owned object is a
partial Ansible patch, and that is what this WP ships.

## What landed

- `ansible/roles/openshift_ai/tasks/set_dashboard_flags.yml` — **the** authoritative flag map
  (`disableLMEval: false`, `guardrails: true`, `trainingJobs: true`, `disableKueue: false`),
  with the reason each key is written explicitly and the reason `disableTracking` and
  `disableDistributedWorkloads` are deliberately left out.
- `ansible/roles/openshift_ai/tasks/dashboard_feature_flags.yml` — wait for the
  operator-created CR (`k8s_info` + bounded `until`, `failed_when: false`), then one
  `state: patched` / `merge_type: merge` partial patch. Modelled on
  `right_size_monitoring_stack.yml`, same contract: patch-only, never fails on its own,
  idempotent, self-healing, shared by install and reconcile.
- `ansible/roles/openshift_ai/tasks/install.yml` + `reconcile.yml` — the shared include, last,
  after the DSC is `Ready` (the dashboard component only creates its CR then).
- `ansible/roles/openshift_ai/tasks/precheck.yml` — a read-only tripwire that reports drift as
  a blocked finding (auto-fix `make d1 reconcile openshift-ai`) and prints `ABSENT` distinctly
  from `=false`. It deliberately does **not** gate `_state_is_installed`: a hidden UI surface is
  not an uninstalled component.
- `docs/adr/0538…` decision 5 amended (mechanism only; the GitOps posture is unchanged and
  reinforced), `docs/adr/0534…` Operational considerations amended, and the two
  `gitops/charts/trustyai-config` comments that told operators to patch by hand.

## Deliberate non-actions

- **`disableTracking`** stays out of the map: it is the only `dashboardConfig` key the operator
  itself owns, already at its default, and it decides whether telemetry is on.
- **`disableDistributedWorkloads`** stays unset, as WP-117 left it. It is the last key in this
  family; whether the Workload metrics page needs it under the same undefined-is-off rule is the
  one question this WP leaves open (step 6 below answers it for the record).
- **The `kueue.openshift.io/managed` label on `zuno-ai-run`** is untouched — it is the
  admission-serialisation mechanism WP-117 wanted.
- **The DSC's `mcpGuardrailsMode`** has the same "a values commit never reaches the cluster"
  symptom for a different reason (`ignoreDifferences: /spec`); same class, different work.

## Verification

1. `python3 platform/docs/check_docs.py` — green.
2. `make d1 check openshift-ai` **before** applying: the finding must name
   `disableKueue ABSENT (want false)`, exit 0, and still report openshift-ai installed.
3. `make d1 reconcile openshift-ai`: the patch task reports `changed`.
4. Re-run it: `ok`/`changed=0` (the module diffs the real object, so this is a true no-op), and
   `make d1 check openshift-ai` reports "all 4 flags as declared".
5. Nothing clobbered: diff the CR JSON before/after — only the four flag keys, `generation` and
   `resourceVersion` may move; `disableTracking`, `notebookController`, `templateOrder`,
   `templateDisablement`, `hardwareProfileOrder` and `modelServing` must be identical. Then
   `--show-managed-fields` must show the `kubectl-patch` manager gone, the operator still owning
   `disableTracking`, and the UI still owning `hardwareProfileOrder`/`modelServing`.
6. Self-healing, without waiting for a fresh cluster: delete one key
   (`--type=merge -p '{"spec":{"dashboardConfig":{"disableKueue":null}}}'`), confirm `check`
   re-reports it, `reconcile` restores it, `check` goes clean.
7. The banner: hard-refresh `/projects/zuno-ai-run?section=settings` — no "Kueue is disabled in
   this cluster", "Deploy model" enabled, hardware-profile list populated. No `rhods-dashboard`
   restart is needed; the flags are read per request (WP-115 finding 1).

## Live run, 2026-09-03

Executed in the order above, on `demo222`:

1. **`make d1 check openshift-ai` before the fix** — reported
   `dashboard feature flags drifted: disableKueue ABSENT (want false)` with auto-fix
   `make d1 reconcile openshift-ai`, exited 0, and still reported `openshift-ai is installed`:
   the tripwire does not gate the component's state, as designed. (A second, pre-existing
   `maas-api` finding was already there and is unrelated.)
2. **`make d1 reconcile openshift-ai`** — the patch task reported `changed`.
3. **Re-run** — the same task reported `ok`; the play's `changed` count dropped from 3 to 2
   (the two remaining are the ArgoCD Application re-applies, not this patch). Idempotent.
4. **`make d1 check openshift-ai`** — "all 4 flags as declared", blocked findings down from 2
   to 1.
5. **Nothing clobbered.** A full object diff before/after, minus `managedFields`/
   `resourceVersion`/`generation`, is exactly one added line: `"disableKueue": false`.
   `hardwareProfileOrder`, `modelServing`, `notebookController`, `templateOrder`,
   `templateDisablement` and `disableTracking` are byte-identical.
6. **Self-healing drill.** `trainingJobs` was deleted with a `null` merge patch, as a stand-in
   for the operator recreating the CR on a fresh cluster. `check` reported
   `trainingJobs ABSENT (want true)`, `reconcile` restored it (`changed`), `check` went clean.

### Finding: ownership transfers on value change, not on write

The expectation that the `kubectl-patch` manager entry would disappear after the first
reconcile was wrong, and the mechanics are worth recording. A JSON merge patch only
re-attributes a field in `managedFields` when it actually **changes** the value, so after
step 2 ownership read:

| manager | dashboardConfig keys |
|---|---|
| `manager` (RHOAI operator) | `disableTracking` |
| `kubectl-patch` (the 2026-09-02 hand patch) | `disableLMEval`, `guardrails`, `trainingJobs` |
| `OpenAPI-Generator` (this automation) | `disableKueue` |

Step 6 then proved the transfer: once `trainingJobs` actually changed, it moved to
`OpenAPI-Generator` and left `kubectl-patch` holding only the two flags whose values have
never moved. This is cosmetic - the automation asserts all four on every run regardless of
who is recorded as their last writer - but it means the stale `kubectl-patch` entry is not
evidence that anything is still hand-managed. The two facts that do matter held throughout:
the operator still owns only `disableTracking`, and the dashboard UI still owns
`hardwareProfileOrder`/`modelServing`.

### The UI half, confirmed by the operator

**Human live test: OK - operator sign-off 2026-09-03.** The `zuno-ai-run` project page is
clean after a plain refresh: no "Kueue is disabled in this cluster" banner, no `rhods-dashboard`
restart needed (the flags are read per request, as WP-115 already saw for `disableLMEval`).

This half could not be self-certified, and that is worth recording for the next person: the
dashboard's own `/api/config` is unreadable from a shell - the route sits behind an
oauth-proxy that wants the browser login flow, and the backend rejects a bearer token even
in-pod (`401 - Failed to determine user identity`). The CR is the only input the frontend
evaluator reads, so the API-side evidence above is what the automation can prove; the pixels
are always a human step.
