# WP-278: what was tested (2026-11-15)

Rehearsal of the foundation demos through `make demo`, in both versions, on 2026-11-15 between 09:38 and 10:35 (the times of the reports).

Session `zuno-demo-reorg-demo333` ran these rehearsals on demo333 with the owner's named go for each, given in the demo333 session, from the checkout `phase56-integ-c, fixed at commit 68ed5a62`. "PASS (nothing to run)" means the step's Ansible file has nothing to run: the row is played by the presenter. The seconds are the engine's own timing of each unit; the total is the time between the start of the log and the report.

## Result

13 of 14 rehearsals are in this file; every one ends with `RESULT: PASS`.

| Demo | 5-minute | 15-minute |
|---|---|---|
| `gitops-day0-3` | PASS, 11 units, 127 s | PASS, 22 units, 151 s |
| `image-signing-admission` | PASS, 11 units, 38 s | PASS, 21 units, 55 s |
| `okf-signed-agent-release` | PASS, 11 units, 33 s | PASS, 20 units, 80 s |
| `vault-pki` | PASS, 11 units, 35 s | PASS, 21 units, 53 s |
| `service-mesh-kiali` | not rehearsed: the owner's go of 2026-11-15 covered the 15-minute version | PASS, 20 units, 115 s |
| `observability-trace` | PASS, 11 units, 117 s | PASS, 20 units, 64 s |
| `aap-audited-operations` | PASS, 11 units, 386 s | PASS, 21 units, 389 s |

## Conditions of the run

- **Who and how.** Session `zuno-demo-reorg-demo333` ran the foundation layer from the checkout `phase56-integ-c`, fixed at
  commit 68ed5a62, in one batch from 09:36:07 to 10:29:46 CET: 11 reports PASS and 2 FAIL. Every run set
  `DEMO_CONFIRM=<id>`, and a check of the fragile Deployments ran before each one. All runs came after the incident of
  2026-11-15 closed (03:30), with the fixed Argo CD status check.
- **`image-signing-admission`.** The supply-chain and signature reads are unchanged after the image rebuild of the incident.
- **`aap-audited-operations` has a changing unit, run with the owner's named go.** `start` launches one read-only AAP job
  (`zuno-day0-check`) per run and waits for it: about 6 minutes.
- **`service-mesh-kiali`: `start` runs the whole golden path.** It is read-only and not a changing unit; it was run with the
  owner's named go. Only the 15-minute version was rehearsed: the owner's go covered that version only, and the 5-minute version is not rehearsed yet. 13 of the 14 versions are rehearsed and PASS, counting the replays.
- **Finding: `observability-trace` failed on `check` in both versions (09:51 and 09:54).** The engine flushed the queued
  probes in queue order: `trace` ran before `unifai-tekos`, whose run id `trace` reads. The platform was fine: demo333 ran
  the probe by hand in both orders at 10:11. The fix is in two commits: 602b9e24 (queue the probes in the probe script's
  `PROBES` order) and fbdd31c7 (one check row per probe; a failed check names the probe and why). The two FAIL reports
  (`observability-trace-5-2026-11-15-095138` and `-15-2026-11-15-095428`) stay here as that finding, not as the result of
  the demo. The tables below show the replays at checkout fbdd31c7, run from 10:30:07 to 10:43:36: `observability-trace`
  5 (103214) and 15 (103526), both PASS; `check` ran `unifai-tekos` and then `trace`, and the log shows 2 of 2
  golden-path rows. The report keeps the unit table; the per-probe rows are in the unit's log. The path where a failed check
  names its probe has not been seen live: no check has failed since the fix.
- **Reviewed from the reports only.** `zuno-demo-reorg-demo333` read the reports, not the on-screen presenter output.
- The host was loaded when several sessions worked on it: read the seconds as an upper bound.

## GitOps and Day 0-3

### 5-minute version

11 units, 127 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 10.0 |
| check | PASS | 65.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS (nothing to run) | 1.0 |
| 0:00 | PASS | 1.0 |
| 1:00 | PASS | 2.0 |
| 2:00 | PASS | 2.0 |
| 3:00 | PASS | 37.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

22 units, 151 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 9.0 |
| check | PASS | 6.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 1.0 |
| 0:00 | PASS | 1.0 |
| 1:00 | PASS | 1.0 |
| 2:00 | PASS | 1.0 |
| 3:00 | PASS | 36.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS | 2.0 |
| 6:00 | PASS (nothing to run) | 0.0 |
| 7:00 | PASS | 2.0 |
| 8:00 | PASS (nothing to run) | 0.0 |
| 9:00 | PASS | 53.0 |
| 10:30 | PASS | 20.0 |
| 11:45 | PASS | 0.0 |
| 12:45 | PASS (nothing to run) | 0.0 |
| 13:30 | PASS | 1.0 |
| 14:15 | PASS | 1.0 |
| 14:45 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 1.0 |

What remains manual on stage:

- The paas-ops-01 terminal, the morning's `make demo golden-path` output kept open, the optional Argo CD UI (look only) and the two documentation tabs.
- Every spoken row; the three Applications that are not Synced and Healthy are known on screen.

## Image signing and admission

### 5-minute version

11 units, 38 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 10.0 |
| check | PASS | 14.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS | 1.0 |
| 1:15 | PASS | 1.0 |
| 2:30 | PASS | 1.0 |
| 3:15 | PASS | 1.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 1.0 |

### 15-minute version

21 units, 55 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 10.0 |
| check | PASS | 14.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS | 1.0 |
| 1:15 | PASS | 1.0 |
| 2:30 | PASS | 1.0 |
| 3:15 | PASS | 1.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS | 1.0 |
| 6:00 | PASS | 1.0 |
| 7:15 | PASS | 2.0 |
| 8:15 | PASS (nothing to run) | 0.0 |
| 9:15 | PASS | 2.0 |
| 10:30 | PASS | 2.0 |
| 11:30 | PASS | 1.0 |
| 12:45 | PASS | 1.0 |
| 13:45 | PASS (nothing to run) | 0.0 |
| 14:15 | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 1.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The paas-ops-01 terminal, the WP-178 tab and `pinned-releases.yaml` at its last entry.
- Always type `clusterimagepolicies.policy.sigstore.dev` in full.

## Signed agent release (OKF)

### 5-minute version

11 units, 33 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 14.0 |
| check | PASS | 6.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 1:15 | PASS | 0.0 |
| 2:15 | PASS | 1.0 |
| 3:30 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 1.0 |

### 15-minute version

20 units, 80 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 15.0 |
| check | PASS | 6.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 1:15 | PASS | 1.0 |
| 2:15 | PASS | 1.0 |
| 3:30 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS | 1.0 |
| 6:00 | PASS | 35.0 |
| 7:30 | PASS (nothing to run) | 1.0 |
| 8:30 | PASS | 1.0 |
| 10:00 | PASS | 1.0 |
| 11:00 | PASS | 1.0 |
| 12:00 | PASS | 1.0 |
| 13:30 | PASS (nothing to run) | 0.0 |
| 14:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The paas-ops-01 terminal (with `OKF_MIRROR_TO` empty), the agent sheet and releases tabs.
- 15-minute version: `make d3 admit agents` once before the session (about 35 s), with `quay.io` reachable.

## Vault and PKI

### 5-minute version

11 units, 35 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 8.0 |
| check | PASS | 9.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS | 1.0 |
| 1:00 | PASS | 2.0 |
| 2:15 | PASS | 2.0 |
| 3:15 | PASS | 1.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

21 units, 53 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 8.0 |
| check | PASS | 9.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS | 1.0 |
| 1:00 | PASS | 2.0 |
| 2:15 | PASS | 2.0 |
| 3:15 | PASS | 1.0 |
| 4:15 | PASS (nothing to run) | 1.0 |
| 5:00 | PASS | 2.0 |
| 6:00 | PASS | 1.0 |
| 7:15 | PASS | 2.0 |
| 8:15 | PASS | 1.0 |
| 9:30 | PASS | 1.0 |
| 10:30 | PASS | 2.0 |
| 11:30 | PASS | 2.0 |
| 12:30 | PASS | 2.0 |
| 13:30 | PASS (nothing to run) | 0.0 |
| 14:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The paas-ops-01 terminal, the "What changed" table of the migration runbook.
- No `vault` command is shown: never read a value in front of an audience.

## Service mesh and Kiali

### 5-minute version

Not rehearsed: the owner's go of 2026-11-15 covered the 15-minute version.

### 15-minute version

20 units, 115 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 9.0 |
| check | PASS | 15.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 63.0 |
| 0:00 | PASS | 1.0 |
| 1:00 | PASS | 1.0 |
| 2:15 | PASS | 1.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 0.0 |
| 6:30 | PASS (nothing to run) | 1.0 |
| 7:45 | PASS | 2.0 |
| 9:00 | PASS | 1.0 |
| 10:00 | PASS | 2.0 |
| 11:15 | PASS | 1.0 |
| 12:15 | PASS | 1.0 |
| 13:30 | PASS (nothing to run) | 0.0 |
| 14:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 1.0 |

What remains manual on stage:

- The paas-ops-01 terminal, the Kiali sign-in as ai-ops-01 (identity provider `openshift`; not tried before: do it the day before) and the Grafana dashboard.
- The graph itself: `start` only creates the traffic.

## Observability and traces

### 5-minute version

11 units, 117 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 11.0 |
| check | PASS | 93.0 |
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

20 units, 64 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 12.0 |
| check | PASS | 27.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS (nothing to run) | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 1:45 | PASS (nothing to run) | 0.0 |
| 3:00 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS (nothing to run) | 1.0 |
| 6:30 | PASS (nothing to run) | 1.0 |
| 8:00 | PASS (nothing to run) | 0.0 |
| 9:15 | PASS (nothing to run) | 0.0 |
| 10:15 | PASS | 1.0 |
| 11:15 | PASS | 2.0 |
| 12:15 | PASS (nothing to run) | 0.0 |
| 13:15 | PASS (nothing to run) | 0.0 |
| 14:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The consultant-02 and ai-ops-01 browser profiles, the warm-up question to Tekos, the Tempo and Grafana views.
- 15-minute version: the paas-ops-01 terminal and the console.

## AAP audited operations

### 5-minute version

11 units, 386 seconds in all. Changing units: start (launches one read-only AAP job, zuno-day0-check, as the AAP admin: it creates a job record and an automation-job-* pod in zuno-aap and waits for its end (about six minutes)). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 9.0 |
| check | PASS | 11.0 |
| install | PASS (nothing to run) | 1.0 |
| start | PASS | 355.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 0.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

### 15-minute version

21 units, 389 seconds in all. Changing units: start (launches one read-only AAP job, zuno-day0-check, as the AAP admin: it creates a job record and an automation-job-* pod in zuno-aap and waits for its end (about six minutes)). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status | PASS | 9.0 |
| check | PASS | 13.0 |
| install | PASS (nothing to run) | 0.0 |
| start | PASS | 339.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:45 | PASS (nothing to run) | 0.0 |
| 2:00 | PASS (nothing to run) | 0.0 |
| 3:15 | PASS (nothing to run) | 0.0 |
| 4:15 | PASS (nothing to run) | 0.0 |
| 5:00 | PASS | 1.0 |
| 6:00 | PASS | 1.0 |
| 6:45 | PASS | 1.0 |
| 8:00 | PASS (nothing to run) | 0.0 |
| 9:00 | PASS | 1.0 |
| 10:15 | PASS (nothing to run) | 0.0 |
| 11:15 | PASS (nothing to run) | 0.0 |
| 12:00 | PASS | 2.0 |
| 13:00 | PASS (nothing to run) | 0.0 |
| 14:00 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

What remains manual on stage:

- The consultant-03 and consultant-02 browser profiles and sign-ins; neither is recorded on demo333, so rehearse both.
- The paas-ops-01 terminal (15-minute version), the AAP menus and the Jobs list.

