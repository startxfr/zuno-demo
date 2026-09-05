# WP-136: Build deterministic `make demo-*` webinar orchestration

- **State:** Done (2026-09-05 - repo-side mechanism complete, both live rehearsals done, webinar-owner sign-off recorded below. `make demo-check` runs a read-only, report-everything-then-decide-once preflight reusing existing building blocks (agent/platform availability, Keycloak reachability, presenter-persona auth + the three webinar projects via a new `evaluations/demo_presenter_probe.py`, local model `/v1/models` readiness, external-provider config eligibility, the WP-105 failover drill's read-only preconditions, and Wesh TrainJob evidence); `make demo-reset` reuses `day3_scenario_failover_node_restore.yml` wholesale via `import_playbook` (already safely idempotent on its own); `make demo-step-1..5` print each presenter step's objective/UI/prompt/expected routing without ever submitting a chat message, and step 5 explicitly delegates the actual failover launch to the existing `make d3 scenario-failover-node` rather than reimplementing it.

  **Rehearsal 1/2 (2026-09-05, live, from `make demo-reset` + `make demo-check` 30/30 PASS)** - see the "Rehearsal log" section below for the full field-by-field record. Result: every step's model/provider/classification routing was correct with zero unplanned CLI repair, but **total duration was ~24m55s against the original 20-minute ceiling** (+~25%), so this WP's own completion criterion ("two consecutive rehearsals complete in <=20 minutes") is not yet met. Root causes were identified and fixed in the presenter contract itself (not code bugs): step 4's "open the OpenShift AI Dashboard" pointer was too vague and cost ~2 minutes of on-stage navigation confusion (`demo_step_4.yml` now prints an exact click-path); step 5's Restore phase budgeted an optimistic 2-minute cold start against a real, WP-105-documented ~4-minute one. The suggested time budget below and `demo_step_4.yml`/`demo_step_5.yml`'s own printed budgets (3->5 min, 6->8 min) were raised accordingly - a **revised ceiling of ~25 minutes**, not the original 20, is what rehearsal 2 should be measured against; the alternative (leave the 20-minute bar as-is and treat this as still-failing) is a call for whoever signs off the webinar, not one made unilaterally here.

  **Rehearsal 2/2 (2026-09-05 evening, live, from a full wipe + `make demo-reset`)** - closed this WP. Run from a genuinely pristine state (all conversations/checkpoints/projects wiped first via a one-off TRUNCATE helper against the `agent-conversations`/`agent-checkpoints` databases - deliberately not kept in the repo - then projects recreated by `make demo-reset`, `make demo-check` green). Total ~21 minutes (steps 1-4 in ~8 min - the step-4 click-path fix paid off - and step 5 in ~13 min from workflow launch to Comage visibly back on Wesh; AAP workflow job #716 successful, zero unplanned CLI repair). Two residual findings recorded, neither blocking per the sign-off below: (a) the drill workflow alone runs ~16.5 min end-to-end (#709: 1039s, #716: 992s), ~4 min of which is a pre-cordon in-cluster baseline probe - launching the workflow at the START of step 4 (during the RHOAI evidence screens) would absorb that dead time and bring the total under 20; (b) this run's nominal pre-drill Comage query (acceptance criterion 11's "visibly uses Wesh before the failover") was skipped - it was live-proven in rehearsal 1 and by the workflow's own baseline probe, but the presenter runbook should keep it explicit.

  **Sign-off (2026-09-05, webinar owner):** the 20-minute ceiling is validated as met in substance - rehearsal 2's ~21 minutes over a strict 20 is not grounds to fail the scenario ("c'est pas à cause d'1mn qu'on ne va pas valider le scénario"). Both rehearsals complete, WP closed `Done`; ADR-0550 moves to `Implemented`.)
- **ADRs:** ADR-0550
- **Depends on:** WP-137, WP-135; reuses WP-105, ADR-0526, ADR-0416, ADR-0417
- **Estimated effort:** 0.5–1 day
- **Difficulty:** Low to Medium

## Goal

Turn existing platform capabilities into a repeatable twenty-minute presenter workflow without replacing the web interfaces with CLI commands.

The Makefile acts as a prompter, preflight checker and recovery assistant.

## Commands

Implement (originally flat `demo-*` targets; regrouped 2026-09-06 as the
`make demo <verb>` verb group, same dispatch mechanism as `make day0-3`
but with no component argument and no AAP routing):

```text
make demo check
make demo reset
make demo step-1
make demo step-2
make demo step-3
make demo step-4
make demo step-5
```

Optionally add:

```text
make demo all-check
```

as an alias to `demo check`; do not create multiple competing entry points if one is sufficient.

## `make demo check`

Validate without mutating the intended demo state:

### Zuno application

- Arkos frontend/BFF/runtime ready;
- Tekos frontend/BFF/runtime ready;
- Comage frontend/BFF/runtime ready;
- Keycloak/OIDC reachable;
- demo presenter persona can authenticate.

### Projects

Ensure known demo projects exist or print the exact UI creation action if the webinar intentionally creates them live:

```text
webinar-public       C1
webinar-confidential C2
webinar-restricted   C3
```

Project creation already exists in the frontend/BFF; do not add a second project mechanism.

**Amendment (2026-09-05):** after the first live `make demo check` run confirmed all three projects were missing, the user asked for automatic creation instead of a mandatory manual UI step before every rehearsal. `make demo reset` now creates any missing one via that same existing `POST /v1/projects` endpoint (`evaluations/demo_presenter_probe.py --ensure-projects`, run inside the same in-cluster Job `make demo check` already used to detect them) - still not a second mechanism. A cross-persona gap was found while implementing this: the probe authenticates as `sale-01` (Comage, `/sales` group), and `POST /v1/projects` only auto-grants the creating subject - so each created project also grants `admin` to both the `consultant` and `sales` business-role groups, since `consultant-01` (the persona `evaluations/arkos`/`evaluations/tekos` use) is in a disjoint Keycloak group with no overlap otherwise. `make demo check` stays strictly read-only and only detects/reports; its guidance message now points at `make demo reset` first, with live frontend creation kept as an option if the presenter wants the audience to see it happen. A project that exists with the wrong classification is still only reported, never auto-corrected.

### Models/providers

Verify:

- local `gpt-oss-20b` ready;
- `qwen3.5-9b` ready;
- `qwen3.5-9b-wesh` ready;
- OVHcloud `gpt-oss-120b` smoke path healthy;
- Codestral smoke path healthy.

### Failover topology

Reuse WP-105 preconditions:

- Qwen base and Wesh workloads running;
- they are on different GPU nodes as required by the hard anti-affinity;
- target node currently schedulable;
- semantic cache cannot hide the proof;
- AAP workflow exists and presenter has launch/approval rights;
- GPU MIG `ResourceQuota` (`zuno-ai-run-gpu-cap`) has headroom, or the restore step has been re-verified not to need WP-131's manual ReplicaSet-scaling workaround (saturation observed 2026-09-05, after WP-105's last live drill proof).

### Training evidence

Verify the successful Wesh training/evaluation/registry run and serving artifact remain available to show.

## `make demo reset`

Return the environment to a safe deterministic initial state.

At minimum:

- ensure no WP-105 target node is left cordoned;
- ensure both Qwen serving workloads are Ready;
- ensure Wesh is again preferred/healthy for the Comage baseline;
- remove/close any temporary demo conversation state only if doing so is safe and documented;
- never delete shared training/model-registry evidence;
- print a final READY/NOT READY summary.

Prefer calling/reusing WP-105 restore logic instead of copying its cordon/uncordon implementation.

The command must be idempotent.

## Presenter step contract

Each `make demo step-N` prints:

1. objective/message to say;
2. web UI to open;
3. exact object/project/task to select;
4. exact short prompt to use;
5. expected classification/model/provider;
6. what to point at in the routing details panel;
7. expected maximum time budget;
8. recovery command if the expected state is not observed.

Do not automatically submit chat messages on behalf of the presenter: the audience should see the real UI interaction.

## Step 1 — Arkos C1 external reasoning (4 min)

Prompt guidance should produce a deterministic, short DAT-related request rather than a full multi-page generation.

Expected:

```text
project: webinar-public OR no project
classification: C1
model: gpt-oss-120b
provider: OVHcloud
execution: external
fallback: no
```

The helper prints the Arkos URL/path and the expected routing-panel values.

## Step 2 — Arkos C2 local reasoning (4 min)

Use the same or nearly identical request inside `webinar-confidential`.

Expected:

```text
classification: C2
model: gpt-oss-20b
execution: local
```

Then instruct the presenter to open:

1. OpenShift AI Dashboard model-serving view;
2. OpenShift Console workload/pod view;
3. the GPU-backed local serving object.

The helper may print `oc` diagnostic commands for emergency verification, but they are not the primary demo path.

## Step 3 — Tekos Codestral specialization (3 min)

Use a short C1 coding prompt known to trigger the existing `write-code` path.

Expected:

```text
agent: tekos
task: write-code
model: codestral-latest
provider: mistral-codestral
```

The prompt must be validated during rehearsal so the request reliably reaches the coding branch.

## Step 4 — Wesh training/model ownership (3 min)

Print the exact OpenShift AI / registry artifacts from the known successful Wesh run to open.

Presenter flow:

1. show completed training/evaluation evidence;
2. show the registered merged model artifact;
3. show the served `qwen3.5-9b-wesh` model;
4. open Comage and send a short normal request;
5. show Wesh as selected provider/model.

No new training run is launched.

## Step 5 — AAP model failover (6 min)

Do **not** create a new failover workflow.

Reuse:

`zuno-day3-scenario-failover-node-workflow`

Presenter flow:

1. open AAP Controller UI;
2. launch the existing workflow;
3. show baseline/Inject stage;
4. while Wesh is unavailable, open/refresh Comage and show fallback to `qwen3.5-9b` in the routing panel;
5. return to AAP and click the existing human approval node;
6. let Restore complete;
7. show Comage returning to `qwen3.5-9b-wesh`.

The helper prints the expected transitions and the existing emergency restoration path.

### Timing risk

WP-105 records real cold-start and telemetry delays around the transition. The webinar must not wait on Prometheus exposition as the only visible proof.

Use the user-facing routing panel as the primary visual proof and AAP workflow state as the infrastructure proof; metrics/logs remain corroborating evidence.

The rehearsal must also confirm that the restore step reschedules Wesh cleanly given the GPU MIG quota saturation recorded in WP-131 (2026-09-05, after WP-105's last live drill proof) — if quota headroom is still zero, check whether the same manual ReplicaSet-scaling workaround is needed and, if so, fold it into the presenter runbook rather than discovering it live.

If the model is inside the short transition interval and the chat request times out, explain the transient cutover and retry once according to the rehearsed runbook rather than improvising cluster changes.

## Rehearsal requirements

Run at least two complete rehearsals from `make demo reset`.

Record for each:

| Field | Required |
|---|---|
| total demo duration | yes |
| each step duration | yes |
| actual model/provider | yes |
| project/effective classification | yes |
| Codestral trigger success | yes |
| Wesh training evidence paths | yes |
| AAP workflow job id | yes |
| failover duration | yes |
| restore duration | yes |
| manual recovery needed | yes |

A rehearsal fails if unplanned shell surgery is required.

## Suggested time budget

**Revised 2026-09-05 after rehearsal 1/2** (original budget totaled 20:00; see the "Rehearsal log" section below for the live measurement that drove this change):

```text
00:00-04:00  Arkos C1 -> OVH gpt-oss-120b
04:00-08:00  Arkos C2 -> local gpt-oss-20b + RHOAI/OCP
08:00-11:00  Tekos -> Codestral
11:00-16:00  Wesh training evidence + Comage (was 11:00-14:00; RHOAI Dashboard navigation needed a printed click-path, not just a pointer - see demo_step_4.yml)
16:00-25:00  AAP failover Wesh -> Qwen -> Wesh (was 14:00-20:00; real Restore-to-Ready cold start measured ~4 min, not 2 - see demo_step_5.yml)
```

## Rehearsal log

### Rehearsal 1/2 - 2026-09-05, live, from `make demo-reset` (30/30 `make demo-check` PASS beforehand)

| Field | Value |
|---|---|
| total demo duration | ~24m55s (chrono start to Wesh confirmed restored) vs original 20:00 budget |
| step 1 duration | 3:53 (budget 4:00) |
| step 2 duration | 1:55 core interaction (budget 4:00) |
| steps 3+4 duration | 9:52 combined (budget 6:00) - see root cause below |
| step 5 inject->approve | 5:18 (budget 4:00) |
| step 5 restore->Wesh Ready | 3:57 (budget 2:00) - real cold start, not a process error |
| actual model/provider (step 1) | `gpt-oss-120b` / `ovhcloud-gpt-oss-120b`, classification C1, execution external |
| actual model/provider (step 2) | `gpt-oss-20b` / `local-gpt-oss-maas`, project `webinar-confidential`, classification C2, execution local |
| Codestral trigger success | yes - `write-code` / `codestral-latest` / `mistral-codestral`, C1 external |
| Wesh training evidence paths | RHOAI Dashboard > Data Science Projects > `zuno-mlops` > Experiments and runs (TrainJob `lora-tekos-sclvp`); Model Registry > `zuno`; Data Science Projects > `zuno-ai-run` > Models > `qwen3.5-9b-wesh` |
| AAP workflow job id | Controller workflow job #709 (`zuno-day3-scenario-failover-node-workflow`) |
| failover duration (cordon to fallback observed) | ~5:18 |
| restore duration (uncordon to Wesh Ready) | ~3:57 |
| manual recovery needed | no - zero unplanned CLI repair; two of Comage's three live queries during the drill window landed on the fallback/pre-Ready path and returned the expected "no live Salesforce read" refusal rather than a wrong answer, which is correct task behavior, not a defect |

Root cause of the step 3+4 overrun: the original step 4 guidance ("open the OpenShift AI Dashboard") named a destination but not a path, and the presenter lost time locating Experiments/Runs, Model Registry, and the Models tab live. Fixed by printing the exact click-path in `demo_step_4.yml` (see WP note above) - not yet re-measured live.

### Rehearsal 2/2 - 2026-09-05 evening, live, from a full wipe + `make demo-reset` (30/30 `make demo-check` PASS beforehand)

| Field | Value |
|---|---|
| total demo duration | ~21m (21:06:00 UTC chrono start to Comage visibly back on Wesh ~21:27) vs 20:00 target - accepted at sign-off |
| step 1 duration | ~1:00 (conversation 21:06:37, reply 21:07:01) |
| step 2 duration | ~2:15 (conversation 21:08:07, reply 21:08:52, project `webinar-confidential`) |
| step 3 duration | ~1:45 (conversation 21:09:55) |
| step 4 duration | ~4:00 (RHOAI screens via the new printed click-path; nominal Comage query skipped - see finding (b) in the State note) |
| step 5 launch->fallback shown | workflow #716 launched 21:13:59; cordon 21:17:52; presenter fallback query 21:18:58 |
| step 5 approve->Wesh Ready | approval ~21:21:40; uncordon 21:22:21; pod Ready 21:25:58 (cold start 3:41) |
| actual model/provider (steps 1-3) | identical to rehearsal 1 (OVH `gpt-oss-120b` C1 external / local `gpt-oss-20b` C2 / `codestral-latest`) |
| Codestral trigger success | yes |
| Wesh training evidence paths | same as rehearsal 1 (click-path now printed by `demo_step_4.yml`) |
| AAP workflow job id | #716 (`zuno-day3-scenario-failover-node-workflow`), successful, elapsed 992s; inject job #717 (7:32), approval node, restore job #721 (8:44) |
| failover duration | launch->cordon 3:53 (pre-cordon in-cluster baseline probe), cordon->fallback observed ~1:06 |
| restore duration | uncordon->Wesh Ready 3:37; workflow's own probes confirmed Comage back on `local-wesh-maas` by 21:30:32 |
| manual recovery needed | no - zero unplanned CLI repair |

## Out of scope

- Dynamic Sovereign Mode.
- New AAP policy-mutation workflow.
- New Tekos Qwen->Wesh failover path.
- Reimplementation of WP-105.
- Repair of RHOAI external `ExternalModel` egress.
- Live LoRA training during the webinar.

## Completion criteria

WP-136 is done when:

- all `demo-*` commands are documented and idempotent where applicable;
- `demo-check` catches missing critical prerequisites;
- `demo-reset` recovers the known failover state safely;
- each helper gives deterministic web guidance and expected output;
- two consecutive rehearsals complete in <=20 minutes with no unplanned CLI repair.

## Operator / human follow-up (not executable by the model without explicit go-ahead)

1. Repo-side is complete: `ansible/playbooks/demo_check.yml`, `demo_reset.yml` and `demo_step_1.yml`..`demo_step_5.yml`, the new `ansible/tasks/demo_persona_probe_job.yml` + `evaluations/demo_presenter_probe.py`, and the seven flat Makefile targets are all merged. Every playbook passed `ansible-playbook --syntax-check`; `demo_persona_probe_job.yml`'s script passed `python3 -m py_compile`; `python3 platform/docs/check_docs.py` passes.
2. Two known, documented scope limits to account for while rehearsing: (a) `demo-check`'s external-provider check (OVHcloud, Codestral) is static config only (`eligible_for` in `provider-routing.yaml`) - no repo mechanism makes a live external smoke call on every `make demo check` run, so real reachability is only proven by actually rehearsing steps 1 and 3; (b) `demo-check`'s AAP precondition confirms the failover workflow template exists in Controller but does not independently re-verify the presenter's own launch/approval RBAC (that grant is wired once by `ansible/roles/aap_config/tasks/wire_launch_rbac.yml` and trusted here, not re-checked per call).
3. Operator: create the three named demo projects live through the frontend if `make demo check` reports them missing (webinar-public/C1, webinar-confidential/C2, webinar-restricted/C3 - this WP deliberately does not create them itself), then run `make demo reset` followed by `make demo check` against the real cluster, then execute at least two complete rehearsals starting from `make demo reset`, recording every field the "Rehearsal requirements" table above lists (total/per-step duration, actual model/provider, Codestral trigger success, Wesh training evidence paths, AAP workflow job id, failover/restore duration, manual recovery needed).
4. **Done 2026-09-05**: both rehearsals executed live (logs above), all "Rehearsal requirements" fields recorded, and the webinar owner explicitly signed off rehearsal 2's ~21 minutes against the 20-minute target as validating the scenario. WP-135 and WP-137 were verified during the same day's rehearsals; ADR-0550 `Status` -> `Implemented`.
