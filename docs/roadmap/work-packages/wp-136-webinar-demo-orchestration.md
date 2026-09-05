# WP-136: Build deterministic `make demo-*` webinar orchestration

- **State:** Operator pending (2026-09-05 - repo-side mechanism complete: `make demo-check` runs a read-only, report-everything-then-decide-once preflight reusing existing building blocks (agent/platform availability, Keycloak reachability, presenter-persona auth + the three webinar projects via a new `evaluations/demo_presenter_probe.py`, local model `/v1/models` readiness, external-provider config eligibility, the WP-105 failover drill's read-only preconditions, and Wesh TrainJob evidence); `make demo-reset` reuses `day3_scenario_failover_node_restore.yml` wholesale via `import_playbook` (already safely idempotent on its own); `make demo-step-1..5` print each presenter step's objective/UI/prompt/expected routing without ever submitting a chat message, and step 5 explicitly delegates the actual failover launch to the existing `make d3 scenario-failover-node` rather than reimplementing it. Two full 20-minute rehearsals and every "Rehearsal requirements" field below are unrun - they need a live cluster.)
- **ADRs:** ADR-0550
- **Depends on:** WP-137, WP-135; reuses WP-105, ADR-0526, ADR-0416, ADR-0417
- **Estimated effort:** 0.5–1 day
- **Difficulty:** Low to Medium

## Goal

Turn existing platform capabilities into a repeatable twenty-minute presenter workflow without replacing the web interfaces with CLI commands.

The Makefile acts as a prompter, preflight checker and recovery assistant.

## Commands

Implement:

```text
make demo-check
make demo-reset
make demo-step-1
make demo-step-2
make demo-step-3
make demo-step-4
make demo-step-5
```

Optionally add:

```text
make demo-all-check
```

as an alias to `demo-check`; do not create multiple competing entry points if one is sufficient.

## `make demo-check`

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

**Amendment (2026-09-05):** after the first live `make demo-check` run confirmed all three projects were missing, the user asked for automatic creation instead of a mandatory manual UI step before every rehearsal. `make demo-reset` now creates any missing one via that same existing `POST /v1/projects` endpoint (`evaluations/demo_presenter_probe.py --ensure-projects`, run inside the same in-cluster Job `make demo-check` already used to detect them) - still not a second mechanism. A cross-persona gap was found while implementing this: the probe authenticates as `sale-01` (Comage, `/sales` group), and `POST /v1/projects` only auto-grants the creating subject - so each created project also grants `admin` to both the `consultant` and `sales` business-role groups, since `consultant-01` (the persona `evaluations/arkos`/`evaluations/tekos` use) is in a disjoint Keycloak group with no overlap otherwise. `make demo-check` stays strictly read-only and only detects/reports; its guidance message now points at `make demo-reset` first, with live frontend creation kept as an option if the presenter wants the audience to see it happen. A project that exists with the wrong classification is still only reported, never auto-corrected.

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

## `make demo-reset`

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

Each `demo-step-N` prints:

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

Run at least two complete rehearsals from `make demo-reset`.

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

```text
00:00-04:00  Arkos C1 -> OVH gpt-oss-120b
04:00-08:00  Arkos C2 -> local gpt-oss-20b + RHOAI/OCP
08:00-11:00  Tekos -> Codestral
11:00-14:00  Wesh training evidence + Comage
14:00-20:00  AAP failover Wesh -> Qwen -> Wesh
```

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
2. Two known, documented scope limits to account for while rehearsing: (a) `demo-check`'s external-provider check (OVHcloud, Codestral) is static config only (`eligible_for` in `provider-routing.yaml`) - no repo mechanism makes a live external smoke call on every `make demo-check` run, so real reachability is only proven by actually rehearsing steps 1 and 3; (b) `demo-check`'s AAP precondition confirms the failover workflow template exists in Controller but does not independently re-verify the presenter's own launch/approval RBAC (that grant is wired once by `ansible/roles/aap_config/tasks/wire_launch_rbac.yml` and trusted here, not re-checked per call).
3. Operator: create the three named demo projects live through the frontend if `make demo-check` reports them missing (webinar-public/C1, webinar-confidential/C2, webinar-restricted/C3 - this WP deliberately does not create them itself), then run `make demo-reset` followed by `make demo-check` against the real cluster, then execute at least two complete rehearsals starting from `make demo-reset`, recording every field the "Rehearsal requirements" table above lists (total/per-step duration, actual model/provider, Codestral trigger success, Wesh training evidence paths, AAP workflow job id, failover/restore duration, manual recovery needed).
4. Once verified: this WP's tracker -> `Done`; contributes toward ADR-0550 `Status` -> `Implemented` once WP-135 and WP-137 are verified too (all three are prerequisites for that final ADR status flip).
