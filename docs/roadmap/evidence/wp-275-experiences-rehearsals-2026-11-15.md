# WP-275: what was tested (2026-11-15)

Rehearsal of the experience demos through `make demo`, in both versions, on 2026-11-15 between 00:59 and 01:37 (the times of the reports).

Session `zuno-demo-reorg` ran these rehearsals on demo333 with the owner's named go for each, given in the demo333 session, from the checkout `phase56-integ-b`. "PASS (nothing to run)" means the step's Ansible file has nothing to run: the row is played by the presenter. The seconds are the engine's own timing of each unit; the total is the time between the start of the log and the report.

## Result

12 of 12 rehearsals are in this file; every one ends with `RESULT: PASS`.

| Demo | 5-minute | 15-minute |
|---|---|---|
| `dify` | PASS, 11 units, 67 s | PASS, 20 units, 65 s |
| `open-webui` | PASS, 11 units, 103 s | PASS, 19 units, 54 s |
| `kagent` | PASS, 11 units, 144 s | PASS, 21 units, 61 s |
| `lightspeed` | PASS, 11 units, 119 s | PASS, 19 units, 82 s |
| `openclaw` | PASS, 11 units, 80 s | PASS, 20 units, 79 s |
| `unifai-agents` | PASS, 11 units, 73 s | PASS, 21 units, 59 s |

## Conditions of the run

- The 12 rehearsals ran between 00:59 and 01:39 (CET) on demo333, one after the other, with no 429 and no skipped step.
- The host was loaded: several sessions worked on it at the same time, and the load tripled some timings. Read the
  seconds as an upper bound, not as a measure of the presenter's time.
- An accidental rehearsal of the `five-experiences` workshop overlapped the `openclaw` and `unifai-agents` rehearsals
  between 01:30 and 01:35. It had no effect on their results.
- No unit of these six demos is a changing unit: every action is a read or has nothing to run. No go was needed beyond
  the owner's go to run the rehearsals.

## Dify

### 5-minute version

11 units, 67 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 14.0 |
| check | PASS | 27.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS | 4.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 3:45 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

20 units, 65 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 13.0 |
| check | PASS | 23.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS | 5.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 3:45 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 1.0 |
| 6:00 | PASS (nothing to run) | 1.0 |
| 7:30 | PASS (nothing to run) | 0.0 |
| 8:45 | PASS | 1.0 |
| 10:00 | PASS (nothing to run) | 0.0 |
| 11:00 | PASS (nothing to run) | 0.0 |
| 12:00 | PASS (nothing to run) | 0.0 |
| 13:00 | PASS (nothing to run) | 0.0 |
| 14:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- Both sign-ins in the consultant-02 profile: Keycloak, then Dify's own form (Vault `zuno/dify/admin`), typed off screen.
- Running each Studio application once before the audience arrives: the probes never run the applications.
- Every UI row: the prompts and the answers. Do not open the MCP server card under **Integrations** (Dify 1.17.0 answers 500).

## Open WebUI

### 5-minute version

11 units, 103 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 8.0 |
| check | PASS | 19.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS | 11.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 0:45 | PASS (nothing to run) | 1.0 |
| 1:45 | PASS (nothing to run) | 1.0 |
| 3:00 | PASS (nothing to run) | 1.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 1.0 |
| uninstall | PASS (nothing to run) | 1.0 |

### 15-minute version

19 units, 54 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 10.0 |
| check | PASS | 14.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 4.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:45 | PASS (nothing to run) | 0.0 |
| 3:00 | PASS (nothing to run) | 1.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 0.0 |
| 6:00 | PASS (nothing to run) | 0.0 |
| 7:30 | PASS (nothing to run) | 0.0 |
| 9:30 | PASS (nothing to run) | 1.0 |
| 10:30 | PASS (nothing to run) | 0.0 |
| 11:30 | PASS (nothing to run) | 0.0 |
| 13:00 | PASS | 2.0 |
| 14:00 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The two browser profiles (sale-01, and consultant-02 in the 15-minute version), **Continue with Keycloak** in each, and a new chat.
- Every UI row: the prompts, the tool switch and the answers.
- Grafana as ai-ops-01 in the 15-minute version.

## kagent

### 5-minute version

11 units, 144 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 102.0 |
| check | PASS | 15.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 4.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 0:45 | PASS (nothing to run) | 1.0 |
| 2:30 | PASS (nothing to run) | 1.0 |
| 3:30 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

21 units, 61 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 17.0 |
| check | PASS | 13.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 4.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 3:30 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 1.0 |
| 6:00 | PASS (nothing to run) | 0.0 |
| 7:30 | PASS | 2.0 |
| 8:45 | PASS | 2.0 |
| 9:45 | PASS | 1.0 |
| 11:00 | PASS (nothing to run) | 0.0 |
| 12:00 | PASS (nothing to run) | 0.0 |
| 13:00 | PASS (nothing to run) | 1.0 |
| 13:45 | PASS (nothing to run) | 0.0 |
| 14:30 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The ai-ops-01 browser profile and its Keycloak sign-in; **Skip wizard** on the first screen of a new browser.
- Every UI row: the questions to `zuno-sre` and the answers.
- `make d2 check kagent` by hand: it proves the controller discovered the governed tools.

## OpenShift Lightspeed

### 5-minute version

11 units, 119 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 43.0 |
| check | PASS | 22.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 3.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 0.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

19 units, 82 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 13.0 |
| check | PASS | 22.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 2.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 0.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 0.0 |
| 6:30 | PASS (nothing to run) | 0.0 |
| 8:00 | PASS | 1.0 |
| 9:15 | PASS | 2.0 |
| 10:45 | PASS | 2.0 |
| 12:00 | PASS (nothing to run) | 0.0 |
| 13:15 | PASS (nothing to run) | 0.0 |
| 14:30 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The console sign-in as consultant-02 with the **openshift** provider (and sale-01 in the 15-minute version, whose first sign-in creates its group).
- The question in the Lightspeed chat: it is not automated, and it spends the shared 200,000 tokens per hour.
- The known "safety inspection" warning: ask again in other words.

## OpenClaw

### 5-minute version

11 units, 80 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 15.0 |
| check | PASS | 38.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 13.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 3:30 | PASS (nothing to run) | 1.0 |
| 4:15 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

20 units, 79 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 12.0 |
| check | PASS | 32.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS | 12.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 3:30 | PASS (nothing to run) | 1.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 0.0 |
| 6:15 | PASS (nothing to run) | 0.0 |
| 7:00 | PASS (nothing to run) | 0.0 |
| 8:30 | PASS (nothing to run) | 0.0 |
| 9:45 | PASS (nothing to run) | 0.0 |
| 10:45 | PASS | 1.0 |
| 12:00 | PASS (nothing to run) | 0.0 |
| 13:30 | PASS (nothing to run) | 0.0 |
| 14:30 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The two browser profiles, the Keycloak sign-in at each front door, and the Control UI password typed off screen (read with `oc extract secret/openclaw-ui -n <namespace> --keys=password --to=-`), then **Connect**.
- Every UI row: the questions to each assistant.
- Grafana as ai-ops-01 in the 15-minute version.

## UnifAI agents

### 5-minute version

11 units, 73 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 25.0 |
| check | PASS | 29.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 5.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:45 | PASS (nothing to run) | 0.0 |
| 3:00 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

21 units, 59 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 13.0 |
| check | PASS | 13.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 5.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:45 | PASS (nothing to run) | 0.0 |
| 3:00 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 0.0 |
| 6:00 | PASS (nothing to run) | 0.0 |
| 7:00 | PASS (nothing to run) | 0.0 |
| 8:00 | PASS | 1.0 |
| 9:00 | PASS | 1.0 |
| 10:00 | PASS (nothing to run) | 0.0 |
| 11:00 | PASS | 1.0 |
| 12:00 | PASS (nothing to run) | 0.0 |
| 13:00 | PASS (nothing to run) | 1.0 |
| 14:00 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 1.0 |
| uninstall | PASS (nothing to run) | 1.0 |

What remains manual on stage:

- The two browser profiles (consultant-02 and ai-ops-01), the Keycloak sign-ins and each person's own session in the team workspace `agent-tekos`.
- The cluster-tools contrast at 3:00: it has no probe and stays a rehearsal point; ask the cluster question as ai-ops-01 the same day.
- Every UI row; Grafana and the terminal in the 15-minute version.

## Cosmetic notes

Two display flaws were seen in the engine's output earlier and are being fixed by the coder. Neither changes a result:
- the "You should see" line prints `-` when a row has no checkpoint;
- the "Next" line is cut in the middle of a backticked command.
