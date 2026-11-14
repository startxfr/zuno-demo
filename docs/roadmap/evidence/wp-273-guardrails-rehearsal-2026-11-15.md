# WP-273: what was tested (2026-11-15)

Rehearsal of the `guardrails` demo through `make demo`, in both versions, on 2026-11-15 between 00:27 and 00:30 (the
times of the reports).

Session `zuno-demo-reorg` ran these rehearsals on demo333 with the owner's named go for each, given in the demo333
session. The commands ran from the integration worktree `phase56-integ` at commit `f4869114`. "PASS (nothing to run)"
means the step's Ansible file has nothing to run: the row is played by the presenter. The seconds are the engine's
own timing of each unit.

## Result

Both rehearsals end with `RESULT: PASS`. No action of this demo changes the cluster.

## 5-minute version

11 units, 53 seconds in all. `status` read the Applications, the NeMo phase and the dashboards in 16 s; `check` ran
the golden-path probe `guardrails` and the browser check `dify` in 21 s.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 16.0 |
| check | PASS | 21.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 4.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 0.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 1.0 |
| uninstall | PASS (nothing to run) | 0.0 |

## 15-minute version

20 units, 59 seconds in all. `status` passed 11 of 11 reads and `check` passed 5 of 5, including the golden-path probe
`guardrails` and the browser check `dify`. Rows 7:30, 8:30 and 9:30 ran their `oc get` reads.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 15.0 |
| check | PASS | 19.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 4.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 1.0 |
| 2:00 | PASS (nothing to run) | 0.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 1.0 |
| 6:15 | PASS (nothing to run) | 0.0 |
| 7:30 | PASS | 1.0 |
| 8:30 | PASS | 1.0 |
| 9:30 | PASS | 1.0 |
| 10:45 | PASS (nothing to run) | 0.0 |
| 12:00 | PASS (nothing to run) | 0.0 |
| 13:00 | PASS (nothing to run) | 0.0 |
| 14:00 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

## Presenter walk-through

The coordinator played the 15-minute version by hand: `use`, `status`, `step next` three times, then `step 8`. Each
output reads in the order RESULT, then the page section, then Next, which is the right order for a presenter.

At 7:30, `oc get nemoguardrails,guardrailsorchestrator,deploy` prints only the NAME and AGE columns. The phase `Error`
of the parked orchestrator `zuno-guardrails-smoke` is therefore not visible on screen there. It shows only with
`oc get guardrailsorchestrator` alone, or in the DataScienceCluster `zuno-dsc`.

## What remains manual on stage

- Every row that says "nothing to run": the sentences to say, the Dify prompt at 0:45, the Grafana panels, the rails
  file, the explanations at 10:45 and 12:00, and the Tempo search at 13:00.
- The two browser profiles, the Dify double sign-in (Vault `zuno/dify/admin`), and the paas-ops-01 OpenShift sign-in
  when its group is missing.
- The 0% rounding of **Detection rate (window)**: use **Detections (count, window)**.

Every "Nothing to do." and "nothing to run" above was checked as deliberate: Status, Install, Stop and Uninstall change
nothing, and the rows without a read are spoken or visual proofs.

## Cosmetic notes

Two display flaws were seen in the engine's output and are being fixed by the coder. Neither changes a result:
- the "You should see" line prints `-` when a row has no checkpoint;
- the "Next" line is cut in the middle of a backticked command.
