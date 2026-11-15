# WP-277: what was tested (2026-11-15)

Rehearsal of the Red Hat OpenShift AI demos through `make demo`, in both versions, on 2026-11-15 between 08:53 and 09:33 (the times of the reports).

Session `zuno-demo-reorg-demo333` ran these rehearsals on demo333 with the owner's named go for each, given in the demo333 session, from the checkout `phase56-integ-c, fixed at commit 68ed5a62`. "PASS (nothing to run)" means the step's Ansible file has nothing to run: the row is played by the presenter. The seconds are the engine's own timing of each unit; the total is the time between the start of the log and the report.

## Result

14 of 14 rehearsals are in this file; every one ends with `RESULT: PASS`.

| Demo | 5-minute | 15-minute |
|---|---|---|
| `evaluation-trustyai-evalhub` | PASS, 12 units, 124 s | PASS, 22 units, 140 s |
| `external-models` | PASS, 11 units, 38 s | PASS, 20 units, 50 s |
| `genai-playground` | PASS, 11 units, 42 s | PASS, 20 units, 53 s |
| `lora-pipeline-mlflow-kueue` | PASS, 12 units, 30 s | PASS, 21 units, 48 s |
| `maas-portal-api-keys` | PASS, 11 units, 30 s | PASS, 18 units, 40 s |
| `model-catalog-registry` | PASS, 11 units, 30 s | PASS, 19 units, 47 s |
| `model-serving-llmd-mig` | PASS, 11 units, 38 s | PASS, 20 units, 52 s |

## Conditions of the run

- **Who and how.** Session `zuno-demo-reorg-demo333` ran all 14 rehearsals from the checkout `phase56-integ-c`, fixed
  at commit 68ed5a62, in one batch from 08:49:26 to 09:35:56 CET. Every run set `DEMO_CONFIRM=<id>`, and a check of the
  fragile Deployments ran before each one. All runs came after the incident of 2026-11-15 closed (03:30), with the fixed
  Argo CD status check: `status` fails on a dead Argo CD or a stale reconciliation.
- **A rehearsal PASS is not "show-ready".** `model-catalog-registry`: demo333 has no ModelRegistry instance. The rehearsal
  exercised the catalog reads only; the registry part can only be told, as the page says.
- **`start` is "nothing to run" by design** for `evaluation-trustyai-evalhub` and `model-catalog-registry`.
  `maas-portal-api-keys`: `start` created no key; the live key at row 1:00 is the demo's proof.
- **`lora-pipeline-mlflow-kueue`: no changing unit is declared.** Both reports say "Changing units: none (every action is
  a read or has nothing to run)", because `demo.yml` has `mutations: {}`. The page names one changing unit outside
  `make demo`: the optional run of the day before, `make d3 run mlops` (owner's go only, never during a freeze; it scales
  up the billed burst GPU node). The rehearsal did not run it.
- **Reviewed from the reports only.** `zuno-demo-reorg-demo333` read the reports, not the on-screen presenter output.
- The host was loaded when several sessions worked on it: read the seconds as an upper bound.

## Evaluation with TrustyAI and EvalHub

### 5-minute version

12 units, 124 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 62.0 |
| check | PASS | 33.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:30 | PASS (nothing to run) | 1.0 |
| 2:30 | PASS (nothing to run) | 1.0 |
| 3:30 | PASS (nothing to run) | 0.0 |
| 4:30 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

22 units, 140 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 23.0 |
| check | PASS | 69.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:30 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 3:30 | PASS (nothing to run) | 1.0 |
| 4:30 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 0.0 |
| 6:15 | PASS (nothing to run) | 0.0 |
| 7:15 | PASS | 16.0 |
| 8:15 | PASS | 8.0 |
| 9:15 | PASS | 0.0 |
| 10:00 | PASS | 1.0 |
| 11:15 | PASS (nothing to run) | 0.0 |
| 12:00 | PASS (nothing to run) | 0.0 |
| 13:00 | PASS | 2.0 |
| 14:00 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The Grafana panels, the Evaluations page of the dashboard, the scenario files in an editor and every UI row.
- No evaluation is started on stage: no EvalHub run, no LMEvalJob, no re-run of the Garak, RAGAS or gate Jobs.

## External models

### 5-minute version

11 units, 38 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 12.0 |
| check | PASS | 13.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS | 2.0 |
| 1:00 | PASS | 1.0 |
| 2:00 | PASS | 1.0 |
| 3:00 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 1.0 |

### 15-minute version

20 units, 50 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 10.0 |
| check | PASS | 13.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS | 1.0 |
| 1:00 | PASS | 1.0 |
| 2:00 | PASS | 1.0 |
| 3:00 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS | 2.0 |
| 6:15 | PASS | 1.0 |
| 7:30 | PASS | 2.0 |
| 9:00 | PASS (nothing to run) | 1.0 |
| 10:30 | PASS | 1.0 |
| 11:30 | PASS (nothing to run) | 0.0 |
| 12:30 | PASS (nothing to run) | 0.0 |
| 13:45 | PASS (nothing to run) | 0.0 |
| 14:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 1.0 |

What remains manual on stage:

- The paas-ops-01 terminal (not `kube:admin`), the editor on `provider-routing.yaml`, the Grafana tab and the evidence tabs.
- The token question of row 7:30: a `200` needs a member's token; the file resolves `$MAAS` itself.

## GenAI playground

### 5-minute version

11 units, 42 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 14.0 |
| check | PASS | 16.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:45 | PASS (nothing to run) | 0.0 |
| 3:00 | PASS (nothing to run) | 1.0 |
| 4:15 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

20 units, 53 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 14.0 |
| check | PASS | 16.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 1.0 |
| 1:45 | PASS (nothing to run) | 1.0 |
| 3:00 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 0.0 |
| 6:00 | PASS (nothing to run) | 0.0 |
| 7:15 | PASS (nothing to run) | 0.0 |
| 8:15 | PASS (nothing to run) | 1.0 |
| 9:15 | PASS | 2.0 |
| 10:30 | PASS | 2.0 |
| 11:45 | PASS (nothing to run) | 1.0 |
| 13:00 | PASS (nothing to run) | 0.0 |
| 14:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The two browser windows (ai-ops-01 and ai-dev-01), the OpenShift sign-ins, the warm-up question and the MCP tokens (never shown on screen).
- The document upload of the 15-minute version and every playground row.

## LoRA pipeline with MLflow

### 5-minute version

12 units, 30 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 8.0 |
| check | PASS | 9.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 1.0 |
| 1:45 | PASS | 1.0 |
| 2:45 | PASS (nothing to run) | 0.0 |
| 3:45 | PASS (nothing to run) | 0.0 |
| 4:30 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 1.0 |
| uninstall | PASS (nothing to run) | 1.0 |

### 15-minute version

21 units, 48 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 8.0 |
| check | PASS | 9.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 1.0 |
| 1:45 | PASS | 1.0 |
| 2:45 | PASS (nothing to run) | 0.0 |
| 3:45 | PASS (nothing to run) | 0.0 |
| 4:30 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS | 1.0 |
| 6:15 | PASS | 2.0 |
| 7:30 | PASS | 2.0 |
| 8:45 | PASS | 1.0 |
| 9:45 | PASS | 2.0 |
| 10:45 | PASS | 1.0 |
| 11:45 | PASS | 1.0 |
| 13:00 | PASS | 1.0 |
| 14:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The ai-dev-01 browser profile, the MLflow tab, the WP-133 evidence tab and the paas-ops-01 terminal.
- A fresh run with `make d3 run mlops`, the day before, by hand and outside `make demo`: see Conditions of the run.

## MaaS portal and API keys

### 5-minute version

11 units, 30 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 9.0 |
| check | PASS | 8.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 1:00 | PASS (nothing to run) | 1.0 |
| 2:15 | PASS | 1.0 |
| 3:00 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 1.0 |

### 15-minute version

18 units, 40 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 10.0 |
| check | PASS | 8.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 1:00 | PASS (nothing to run) | 0.0 |
| 2:15 | PASS | 1.0 |
| 3:00 | PASS (nothing to run) | 1.0 |
| 4:15 | PASS (nothing to run) | 1.0 |
| 5:00 | PASS | 1.0 |
| 7:00 | PASS | 2.0 |
| 9:00 | PASS | 2.0 |
| 10:30 | PASS (nothing to run) | 0.0 |
| 12:00 | PASS (nothing to run) | 0.0 |
| 13:00 | PASS (nothing to run) | 0.0 |
| 14:30 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The ai-dev-01 sign-in, the key made live at row 1:00 (the demo's proof), its use with `curl` and its revocation in the portal.
- Rows 3:00 and 12:00 of the 15-minute version, run by hand with `$MAAS` exported.

## Model catalog and registry

### 5-minute version

11 units, 30 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 10.0 |
| check | PASS | 8.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 1.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

19 units, 47 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 11.0 |
| check | PASS | 8.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 0.0 |
| 3:15 | PASS (nothing to run) | 1.0 |
| 4:15 | PASS (nothing to run) | 1.0 |
| 5:00 | PASS | 2.0 |
| 6:15 | PASS | 3.0 |
| 7:45 | PASS | 1.0 |
| 9:00 | PASS | 2.0 |
| 10:00 | PASS (nothing to run) | 0.0 |
| 11:30 | PASS | 1.0 |
| 12:45 | PASS (nothing to run) | 0.0 |
| 14:00 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 1.0 |

What remains manual on stage:

- The ai-dev-01 browser profile, the catalog card, the WP-133 evidence and `stage_push_registry` in an editor.
- The registry steps of the 15-minute version are told, not run: demo333 has no ModelRegistry instance.

## Model serving with llm-d on MIG

### 5-minute version

11 units, 38 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 13.0 |
| check | PASS | 9.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS (nothing to run) | 1.0 |
| 0:00 | PASS | 2.0 |
| 1:00 | PASS | 2.0 |
| 2:15 | PASS | 1.0 |
| 3:00 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

20 units, 52 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 12.0 |
| check | PASS | 8.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS | 2.0 |
| 1:00 | PASS | 2.0 |
| 2:15 | PASS | 1.0 |
| 3:00 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS | 1.0 |
| 6:15 | PASS | 1.0 |
| 7:15 | PASS | 1.0 |
| 8:30 | PASS | 3.0 |
| 9:45 | PASS | 3.0 |
| 11:00 | PASS | 2.0 |
| 12:00 | PASS | 1.0 |
| 13:00 | PASS (nothing to run) | 1.0 |
| 14:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The paas-ops-01 terminal, the Grafana dashboard and rows, the optional Perses dashboards and the two evidence pages.
- Every UI row.

## Cosmetic notes

Two display flaws were seen in the engine's output earlier and are being fixed by the coder. Neither changes a result:
- the "You should see" line prints `-` when a row has no checkpoint;
- the "Next" line is cut in the middle of a backticked command.
