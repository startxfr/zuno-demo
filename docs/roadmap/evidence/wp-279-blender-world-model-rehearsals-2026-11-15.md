# WP-279: what was tested (2026-11-15)

Rehearsal of the Blender 3D and world model demos through `make demo`, in both versions, on 2026-11-15 between 10:44 and 10:52 (the times of the reports).

Session `zuno-demo-reorg-demo333` ran these rehearsals on demo333 with the owner's named go for each, given in the demo333 session, from the checkout `phase56-integ-c`, at commit fbdd31c7 for this layer. "PASS (nothing to run)" means the step's Ansible file has nothing to run: the row is played by the presenter. The seconds are the engine's own timing of each unit; the total is the time between the start of the log and the report.

## Result

4 of 4 rehearsals are in this file; every one ends with `RESULT: PASS`.

| Demo | 5-minute | 15-minute |
|---|---|---|
| `blender-3d` | PASS, 13 units, 42 s, 2 skipped | PASS, 23 units, 51 s, 2 skipped |
| `world-model` | PASS, 12 units, 22 s, 1 skipped | PASS, 21 units, 32 s, 1 skipped |

## Conditions of the run

- **Who and how.** Session `zuno-demo-reorg-demo333` ran this layer from the checkout `phase56-integ-c` at commit fbdd31c7,
  from 10:43:52 to 10:54:57 CET: 4 of 4 reports PASS. Every run set `DEMO_CONFIRM=<id>`. They came after the incident of
  2026-11-15 closed (03:30), with the fixed Argo CD status check.
- **`blender-3d`: `install` and `uninstall` are SKIPPED** ("not rehearsed"). They write or remove the add-on in the Blender
  folders of the workstation that runs the rehearsal. This is the owner's decision of 2026-11-15. `check` is the golden-path
  probe `blender`; the check unit's log prints the row `blender-3d     check        PASS   golden-path    golden-path/blender`.
- **`world-model`: `install` is SKIPPED** ("not rehearsed: it refuses while the demo is switched off, and the owner creates
  the GPU node by hand"). `uninstall` is PASS, and it removed nothing: its detail prints the owner's three actions, by hand,
  after the session.

### What the `world-model` PASS means

It does **not** mean the demo is show-ready.

- `zuno_world_model_enabled` is `false` (`ansible/clusters/demo333.yml` at fbdd31c7). There is no GPU node (no g7e
  capacity since 2026-11-10), and the Application is not installed.
- `check` passed on two rows, quoted from the check unit's log:
  `world-model    check        PASS   custom-resource grafanadashboard/zuno-monitoring/world-model` and
  `world-model    check        PASS   golden-path    golden-path/world-model`. The log row says `PASS` and does not
  print the word `roadmap`. The probe code explains the second row: `probe_world_model` returns a `roadmap` result
  (`required=False`, "not installed (zuno_world_model_enabled is false): shown as roadmap, not live") unless the demo is
  positively found installed, and a non-required result never fails the check. So the row passed because the
  GrafanaDashboard exists and the probe reports the demo as roadmap, not because a world was created.
- The rehearsal therefore proves that the files and the page play (status, check, read-only steps, stop, uninstall). It
  does not prove the demo. The page keeps "not show-ready". A real rehearsal needs the GPU node and the owner's double
  approval.
- **No screen review.** `zuno-demo-reorg-demo333` read the reports, not the on-screen presenter output.
- The host was loaded when several sessions worked on it: read the seconds as an upper bound.

## Blender 3D

### 5-minute version

13 units, 42 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 17.0 |
| check | PASS | 15.0 |
| install | SKIPPED | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:20 | PASS (nothing to run) | 1.0 |
| 0:40 | PASS (nothing to run) | 0.0 |
| 1:10 | PASS (nothing to run) | 0.0 |
| 1:30 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 0.0 |
| 2:40 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 1.0 |
| uninstall | SKIPPED | 0.0 |

### 15-minute version

23 units, 51 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 15.0 |
| check | PASS | 12.0 |
| install | SKIPPED | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:20 | PASS (nothing to run) | 0.0 |
| 0:40 | PASS (nothing to run) | 0.0 |
| 1:10 | PASS (nothing to run) | 1.0 |
| 1:30 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 0.0 |
| 2:40 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 0.0 |
| 6:15 | PASS (nothing to run) | 1.0 |
| 7:00 | PASS (nothing to run) | 0.0 |
| 8:00 | PASS | 2.0 |
| 9:00 | PASS | 1.0 |
| 10:30 | PASS | 1.0 |
| 11:30 | PASS | 1.0 |
| 12:30 | PASS (nothing to run) | 0.0 |
| 13:30 | PASS (nothing to run) | 0.0 |
| 14:30 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 1.0 |
| uninstall | SKIPPED | 0.0 |

What remains manual on stage:

- Blender on the presenter's workstation, the add-on installed by `install` (not rehearsed here), the sentence typed and every UI row.
- The persona sign-ins and the browser views.

## World model

### 5-minute version

12 units, 22 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 4.0 |
| check | PASS | 5.0 |
| install | SKIPPED | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 0:30 | PASS (nothing to run) | 0.0 |
| 1:15 | PASS (nothing to run) | 0.0 |
| 2:15 | PASS (nothing to run) | 0.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:00 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS | 2.0 |

### 15-minute version

21 units, 32 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 4.0 |
| check | PASS | 7.0 |
| install | SKIPPED | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:30 | PASS (nothing to run) | 0.0 |
| 1:15 | PASS (nothing to run) | 1.0 |
| 2:15 | PASS (nothing to run) | 0.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:00 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 0.0 |
| 6:15 | PASS (nothing to run) | 0.0 |
| 7:00 | PASS (nothing to run) | 0.0 |
| 8:30 | PASS (nothing to run) | 0.0 |
| 9:30 | PASS (nothing to run) | 0.0 |
| 11:30 | PASS | 2.0 |
| 12:30 | PASS (nothing to run) | 0.0 |
| 14:00 | PASS (nothing to run) | 0.0 |
| 14:30 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS | 2.0 |

What remains manual on stage:

- The owner's three actions: create the GPU node by hand, enable the flag and install the demo, then (after the session) uninstall.
- Every row: nothing is played live while the demo is off.

