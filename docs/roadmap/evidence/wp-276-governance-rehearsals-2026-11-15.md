# WP-276: what was tested (2026-11-15)

Rehearsal of the governance demos through `make demo`, in both versions, on 2026-11-15 between 02:17 and 08:47 (the times of the reports).

Session `zuno-demo-reorg-demo333` ran these rehearsals on demo333 with the owner's named go for each, given in the demo333 session, from the checkout `phase56-integ-c, fixed at commit 68ed5a62`. "PASS (nothing to run)" means the step's Ansible file has nothing to run: the row is played by the presenter. The seconds are the engine's own timing of each unit; the total is the time between the start of the log and the report.

## Result

12 of 12 rehearsals are in this file; every one ends with `RESULT: PASS`.

| Demo | 5-minute | 15-minute |
|---|---|---|
| `a2a-delegation-approval` | PASS, 12 units, 53 s | PASS, 21 units, 72 s |
| `ai-gateway-routing` | PASS, 11 units, 96 s | PASS, 20 units, 44 s |
| `ai-gateway-sovereignty` | PASS, 11 units, 50 s | PASS, 19 units, 64 s |
| `identity-personas` | PASS, 12 units, 46 s | PASS, 21 units, 117 s |
| `mcp-tools-by-group` | PASS, 12 units, 32 s | PASS, 22 units, 46 s |
| `quotas` | PASS, 10 units, 37 s | PASS, 19 units, 47 s |

## Conditions of the run

- **Incident of 2026-11-15, 01:38.** The world-model GPU teardown deleted the Argo CD instance of demo333 and emptied
  the internal registry bucket. Argo CD was restored at 02:06. The images were rebuilt between 02:41 and 03:23, and the
  incident was closed at 03:30 (supply-chain check 12/12, golden path 13/13 at 03:25). After the restore, the golden
  path of 02:15 gave 13 PASS, and `world-model` reported `roadmap` (the demo is off).
- **Windows excluded.** A report whose log or time falls between 01:38 and 02:06 (Argo CD gone) or between 02:35 and
  03:30 (the rebuild) is not used here. The five governance reports of 01:40 to 01:52 ran while Argo CD was gone, and
  `identity-personas` 15 (02:36) and `mcp-tools-by-group` 5 (02:39) overlapped the rebuild; both were run again
  at 08:32 and 08:35. For every demo and version this file uses the latest report outside these windows.
- **A defect found by the incident.** `status` read the stored Application statuses and did not fail on a dead Argo CD or
  a stale reconciliation; five rehearsals had passed that way. It now fails on both. Every report used here is from 02:17 or later (the second batch ran from 08:30:28 to 08:49:16 CET) and ran from the checkout `phase56-integ-c` (fixed at commit 68ed5a62 for the rest of the rehearsals), which holds the fixed check (its log prints the row `argo/application-controller`, which only the fixed check prints). The experiences layer and the two pilots ran with the earlier check.
- **How the runs were made.** Every run set `DEMO_CONFIRM=<id>`, and a check of the fragile Deployments ran before each
  one. Reports `identity-personas` 15 (083235) and `mcp-tools-by-group` 5 (083517) replace the suspect runs of 02:36 and 02:39.
- **`quotas` has a changing unit, run with the owner's named go.** `start` spends token budget and is not undone: one short
  answer through sale-01's OpenClaw assistant and one through consultant-02's, in each version, so sale-01's budget was
  spent twice. The Open WebUI question as sale-01 stays by hand. The `quotas` runs are short (37 s and 47 s) because `start` is one probe.
- The host was loaded when several sessions worked on it: read the seconds as an upper bound.
- **Replay of 2026-11-15, 10:30 to 10:43.** `ai-gateway-sovereignty` 5 (103829) and 15 (104136) were run again at checkout
  fbdd31c7, with the probe queue in the script's order: both PASS. The 02:27 and 02:30 reports stay the result of this
  file. The night log shows the queue was already `unifai-tekos,sovereignty,trace`, so the night PASS did not depend on
  the queue-order bug found in WP-278.
- `guardrails` belongs to this layer and has its own file: [WP-273](wp-273-guardrails-rehearsal-2026-11-15.md).

## A2A delegation with approval

### 5-minute version

12 units, 53 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 13.0 |
| check | PASS | 27.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 1.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:30 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 3:30 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

21 units, 72 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 14.0 |
| check | PASS | 36.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 1.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:30 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 3:30 | PASS (nothing to run) | 1.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS | 1.0 |
| 6:00 | PASS | 1.0 |
| 7:00 | PASS (nothing to run) | 0.0 |
| 8:30 | PASS (nothing to run) | 0.0 |
| 9:30 | PASS (nothing to run) | 0.0 |
| 10:30 | PASS (nothing to run) | 0.0 |
| 11:45 | PASS (nothing to run) | 1.0 |
| 13:00 | PASS (nothing to run) | 0.0 |
| 14:00 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The consultant-02 sign-in, and the same-day rehearsal of the **Reject** path.
- The approval click by consultant-02 in UnifAI and the AAP job: they stay human steps; respect the AAP launch limit of 2 per 900 s.
- Every UI row, and the Tempo, Grafana and sheet tabs.

## Routing

### 5-minute version

11 units, 96 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 61.0 |
| check | PASS | 11.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 1.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

20 units, 44 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 18.0 |
| check | PASS | 3.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 1.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS | 1.0 |
| 6:30 | PASS (nothing to run) | 0.0 |
| 8:00 | PASS (nothing to run) | 0.0 |
| 9:00 | PASS (nothing to run) | 1.0 |
| 10:30 | PASS | 2.0 |
| 11:30 | PASS (nothing to run) | 0.0 |
| 12:15 | PASS (nothing to run) | 0.0 |
| 13:00 | PASS (nothing to run) | 1.0 |
| 14:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The paas-ops-01 terminal, the sale-01 and ai-ops-01 profiles, the warm-up question and every UI row.
- The block "The coding pair: C1 and C3": an owner action, printed and never run by the step.

## Sovereignty

### 5-minute version

11 units, 50 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 13.0 |
| check | PASS | 18.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 1:00 | PASS | 6.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 3:30 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

19 units, 64 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 15.0 |
| check | PASS | 24.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 1:00 | PASS | 5.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 3:30 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 1.0 |
| 6:00 | PASS | 1.0 |
| 7:30 | PASS (nothing to run) | 0.0 |
| 9:00 | PASS (nothing to run) | 0.0 |
| 10:30 | PASS (nothing to run) | 0.0 |
| 12:30 | PASS (nothing to run) | 0.0 |
| 13:45 | PASS (nothing to run) | 1.0 |
| 14:30 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The browser profiles, the questions and the Grafana and Tempo views.
- Row 1:00 runs `ONLY=sovereignty make demo golden-path` by itself, as an allowed read; the rest of the rows are spoken or visual.

## Identity and personas

### 5-minute version

12 units, 46 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 17.0 |
| check | PASS | 15.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS (nothing to run) | 1.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:30 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 3:30 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

21 units, 117 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 77.0 |
| check | PASS | 15.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:30 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 1.0 |
| 3:30 | PASS (nothing to run) | 1.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS | 1.0 |
| 6:00 | PASS | 2.0 |
| 7:15 | PASS (nothing to run) | 0.0 |
| 8:15 | PASS (nothing to run) | 1.0 |
| 9:15 | PASS (nothing to run) | 0.0 |
| 10:15 | PASS | 1.0 |
| 11:30 | PASS (nothing to run) | 0.0 |
| 12:30 | PASS | 1.0 |
| 13:45 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The first OpenShift sign-in of each persona whose group is missing (a first sign-in creates the user and the group); not sale-01, whose absent `sales` group the 5:00 row shows.
- The profiles, the Keycloak sign-ins and the new chats.

## MCP tools by group

### 5-minute version

12 units, 32 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 15.0 |
| check | PASS | 6.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:30 | PASS (nothing to run) | 0.0 |
| 2:45 | PASS (nothing to run) | 1.0 |
| 3:45 | PASS (nothing to run) | 0.0 |
| 4:30 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

22 units, 46 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 14.0 |
| check | PASS | 5.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:30 | PASS (nothing to run) | 1.0 |
| 2:45 | PASS (nothing to run) | 0.0 |
| 3:45 | PASS (nothing to run) | 0.0 |
| 4:30 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS | 5.0 |
| 6:00 | PASS (nothing to run) | 0.0 |
| 7:00 | PASS (nothing to run) | 0.0 |
| 8:00 | PASS (nothing to run) | 0.0 |
| 8:45 | PASS (nothing to run) | 1.0 |
| 10:00 | PASS (nothing to run) | 0.0 |
| 11:00 | PASS | 1.0 |
| 12:00 | PASS (nothing to run) | 0.0 |
| 13:00 | PASS (nothing to run) | 0.0 |
| 14:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 1.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The three Open WebUI profiles, the Keycloak sign-ins, new chats and the warm-up question.
- The optional rows 8:00 and 11:00 (a terminal read of the gateway log); every UI row.

## One budget per persona

### 5-minute version

10 units, 37 seconds in all. Changing units: start (Spends token budget, not undone: one short answer through sale-01's OpenClaw assistant (and one through consultant-02's)). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 17.0 |
| check | PASS | 1.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 7.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 1:00 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 4:00 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 1.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

19 units, 47 seconds in all. Changing units: start (Spends token budget, not undone: one short answer through sale-01's OpenClaw assistant (and one through consultant-02's)). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 18.0 |
| check | PASS | 2.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 8.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 1:00 | PASS (nothing to run) | 0.0 |
| 2:30 | PASS (nothing to run) | 0.0 |
| 4:00 | PASS (nothing to run) | 1.0 |
| 5:00 | PASS (nothing to run) | 0.0 |
| 6:30 | PASS | 1.0 |
| 8:00 | PASS (nothing to run) | 0.0 |
| 9:00 | PASS | 1.0 |
| 10:00 | PASS (nothing to run) | 0.0 |
| 10:45 | PASS (nothing to run) | 0.0 |
| 11:45 | PASS (nothing to run) | 0.0 |
| 13:00 | PASS (nothing to run) | 0.0 |
| 14:30 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The Open WebUI question as sale-01: the file prints it as a line and does not ask it, because no automated sign-in to Open WebUI as sale-01 exists.
- Every UI row: the budget panel, the trace, the refusal.
- The 15-minute "Optional replay": an owner action, printed and never run by the step.

## Cosmetic notes

Two display flaws were seen in the engine's output earlier and are being fixed by the coder. Neither changes a result:
- the "You should see" line prints `-` when a row has no checkpoint;
- the "Next" line is cut in the middle of a backticked command.
