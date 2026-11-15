# WP-274: what was tested (2026-11-15)

Rehearsal of the `unifai-live-rag` demo through `make demo`, in both versions, on 2026-11-15 between 00:30 and 00:34
(the times of the reports).

Session `zuno-demo-reorg` ran these rehearsals on demo333 with the owner's named go for each, given in the demo333
session. The commands ran from the integration worktree `phase56-integ` at commit `f4869114`. "PASS (nothing to run)"
means the step's Ansible file has nothing to run: the row is played by the presenter. The seconds are the engine's
own timing of each unit.

Unlike `guardrails`, this demo changes shared state: `start` and `stop` act on consultant-01's Personal documents.

These rehearsals ran before the incident of 2026-11-15 (01:38) with the earlier `status`, which read the stored Application statuses and did not fail on a dead Argo CD or a stale reconciliation. Their `status` units show that the Applications were Healthy at the last reconciliation. The check was fixed later the same night.

## Result

Both rehearsals end with `RESULT: PASS`. In the 15-minute version, one unit is `SKIPPED (mutating)`: the optional
row 9:30, as the brief expects.

## 5-minute version

11 units, 91 seconds in all. `start` took 35 s: it deleted the 3 named files, uploaded the 2 demo files, waited until
both were **Done** and warmed the model.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 16.0 |
| check | PASS | 26.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 35.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:30 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 0.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS | 3.0 |
| uninstall | PASS (nothing to run) | 1.0 |

## 15-minute version

20 units, 105 seconds in all, 1 skipped. Rows 10:00 and 11:00 ran their `oc get` reads and row 12:45 ran once without
`-w`. Row 9:30 (the optional Confluence resync, a change of the cluster) was skipped and never run, as designed.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 16.0 |
| check | PASS | 27.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 34.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 0:30 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 0.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 0.0 |
| 6:15 | PASS (nothing to run) | 0.0 |
| 7:30 | PASS (nothing to run) | 0.0 |
| 8:30 | PASS (nothing to run) | 0.0 |
| 9:30 | SKIPPED (mutating) | 0.0 |
| 10:00 | PASS | 1.0 |
| 11:00 | PASS | 1.0 |
| 11:45 | PASS (nothing to run) | 0.0 |
| 12:45 | PASS | 0.0 |
| 14:00 | PASS (nothing to run) | 0.0 |
| stop | PASS | 2.0 |
| uninstall | PASS (nothing to run) | 0.0 |

## State after the rehearsal

After the 15-minute run, consultant-01's Personal library is empty: the list printed nothing. The three files of
2026-11-05 are gone, as the owner's go said. `stop` deletes the three named files, which include the two demo files,
so the library holds none of them. `make demo start` creates the two demo files again.

## What remains manual on stage

- The two browser profiles (consultant-01 and, in the 15-minute version, sale-01), and the Keycloak sign-ins.
- Every UI row: the library view at 0:00 and 0:30, the questions at 2:00 and 3:15, the team and isolation contrast, and
  the Confluence question.
- The optional Confluence resync (rows 9:30 and 12:45): prepared and run by hand, outside a freeze. The step never runs
  it.
- Grafana as ai-ops-01 and the paas-ops-01 terminal in the 15-minute version.

Every "Nothing to do." and "nothing to run" above was checked as deliberate: Install and Uninstall change nothing, and
the rows without a read are spoken or visual proofs.

## Cosmetic notes

Two display flaws were seen in the engine's output and are being fixed by the coder. Neither changes a result:
- the "You should see" line prints `-` when a row has no checkpoint;
- the "Next" line is cut in the middle of a backticked command.
