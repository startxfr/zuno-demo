# WP-280: what was tested (2026-11-15)

Rehearsal of the six workshops through `make demo rehearse <workshop>` on 2026-11-15 between 10:58 and 11:49 (the times of the reports).

Session `zuno-demo-reorg-demo333` ran them on demo333 with the owner's named go where a unit changes the cluster, from the checkout `phase56-integ-c` at commit fbdd31c7. A workshop rehearsal runs, for every scenario block, the units of that scenario's files in the agenda's order (`status:<id>`, `check:<id>`, `install:<id>`, `start:<id>`, then `stop` and `uninstall`). "PASS (nothing to run)" means a file has nothing to run: the row is played by the presenter. The seconds are the engine's own timing of each unit.

## Result

6 of 6 workshops end with `RESULT: PASS`, counting the replay of `agentic-ai` (its first report is the finding in the conditions below).

| Workshop | Result | Units | Seconds | Skipped | Failed |
|---|---|---|---|---|---|
| `three-experiences` | PASS | 45 | 206 | 0 | 0 |
| `five-experiences` | PASS | 94 | 269 | 2 | 0 |
| `sovereign-governed-ai` | PASS | 77 | 225 | 0 | 0 |
| `agentic-ai` | PASS | 96 | 348 | 0 | 0 |
| `rhoai-end-to-end` | PASS | 105 | 262 | 0 | 0 |
| `trusted-platform-ops` | PASS | 94 | 725 | 0 | 0 |

## Conditions of the run

- **Who and how.** Session `zuno-demo-reorg-demo333`, checkout `phase56-integ-c` at commit fbdd31c7, from 10:55:15 to 11:40:54 CET. They came after the incident of 2026-11-15 closed (03:30), with the fixed Argo CD status check.
- **Not evidence.** An earlier `five-experiences` run of 01:30 to 01:35 was started by mistake (probes only) and is not used here.
- **`sovereign-governed-ai`** ran with the owner's named go: its changing unit `start:quotas` spent token budget again (one short answer through sale-01's OpenClaw assistant, and one through consultant-02's). It is not undone.
- **`trusted-platform-ops`** ran with the owner's named go and took 725 s: it launched one read-only AAP job and ran the whole golden path of `service-mesh-kiali`.
- **`five-experiences`:** `install:blender-3d` and `uninstall:blender-3d` are SKIPPED: they write or remove the add-on on the workstation that runs the rehearsal, and are not rehearsed.
- **`agentic-ai`: finding.** The first run (112439) FAILED on `start:unifai-live-rag` and `stop:unifai-live-rag`, in 0.0 s, before touching the cluster: consultant-01's library was unchanged, as demo333 checked. Those two files included their helper through `demo_dir`, which is the workshop's directory when the unit runs inside a workshop. Commit b2dd53c1 fixes it, with a catalogue test. The replay at checkout b2dd53c1 (report `agentic-ai-w-2026-11-15-114921`, 11:42:46 to 11:51:21, 352 s) is PASS, with the owner's named go for the workshop: `start:unifai-live-rag` 31 s (it deleted the three named files, uploaded the two demo files and waited for DONE) and `stop:unifai-live-rag` 3 s. After the run, consultant-01's Personal library lists nothing, as demo333 checked. The 112439 report stays here as the finding; the table below is the replay.
- **Reviewed from the reports only.** `zuno-demo-reorg-demo333` read the reports, not the on-screen presenter output.
- The host was loaded when several sessions worked on it: read the seconds as an upper bound.

## One backend, three experiences

45 units, 206 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status:unifai-agents | PASS | 75.0 |
| status:open-webui | PASS | 11.0 |
| status:openclaw | PASS | 15.0 |
| status | PASS (nothing to run) | 0.0 |
| check:unifai-agents | PASS | 1.0 |
| check:open-webui | PASS | 0.0 |
| check:openclaw | PASS | 6.0 |
| check | PASS | 41.0 |
| install:unifai-agents | PASS (nothing to run) | 0.0 |
| install:open-webui | PASS (nothing to run) | 0.0 |
| install:openclaw | PASS (nothing to run) | 0.0 |
| install | PASS (nothing to run) | 0.0 |
| start:unifai-agents | PASS | 1.0 |
| start:open-webui | PASS | 1.0 |
| start:openclaw | PASS | 4.0 |
| start | PASS | 13.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:02/0:00 | PASS (nothing to run) | 0.0 |
| 0:02/0:45 | PASS (nothing to run) | 0.0 |
| 0:02/1:45 | PASS (nothing to run) | 0.0 |
| 0:02/3:00 | PASS (nothing to run) | 1.0 |
| 0:02/4:15 | PASS (nothing to run) | 0.0 |
| 0:07/0:00 | PASS (nothing to run) | 0.0 |
| 0:07/0:45 | PASS (nothing to run) | 0.0 |
| 0:07/1:45 | PASS (nothing to run) | 0.0 |
| 0:07/3:00 | PASS (nothing to run) | 0.0 |
| 0:07/4:15 | PASS (nothing to run) | 1.0 |
| 0:12/0:00 | PASS (nothing to run) | 0.0 |
| 0:12/0:45 | PASS (nothing to run) | 0.0 |
| 0:12/2:30 | PASS (nothing to run) | 0.0 |
| 0:12/3:30 | PASS (nothing to run) | 0.0 |
| 0:12/4:15 | PASS (nothing to run) | 1.0 |
| 0:17/0:00 | PASS (nothing to run) | 1.0 |
| 0:17/2:00 | PASS (nothing to run) | 0.0 |
| 0:17/4:00 | PASS (nothing to run) | 0.0 |
| 0:17/6:00 | PASS (nothing to run) | 0.0 |
| 0:25 | PASS (nothing to run) | 0.0 |
| stop:openclaw | PASS (nothing to run) | 0.0 |
| stop:open-webui | PASS (nothing to run) | 1.0 |
| stop:unifai-agents | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall:openclaw | PASS (nothing to run) | 0.0 |
| uninstall:open-webui | PASS (nothing to run) | 0.0 |
| uninstall:unifai-agents | PASS (nothing to run) | 1.0 |
| uninstall | PASS (nothing to run) | 1.0 |

## One governed backend, many experiences

94 units, 269 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status:unifai-agents | PASS | 15.0 |
| status:open-webui | PASS | 10.0 |
| status:openclaw | PASS | 15.0 |
| status:dify | PASS | 10.0 |
| status:kagent | PASS | 13.0 |
| status:lightspeed | PASS | 8.0 |
| status:blender-3d | PASS | 14.0 |
| status | PASS (nothing to run) | 0.0 |
| check:unifai-agents | PASS | 1.0 |
| check:open-webui | PASS | 1.0 |
| check:openclaw | PASS | 6.0 |
| check:dify | PASS | 3.0 |
| check:kagent | PASS | 3.0 |
| check:lightspeed | PASS | 7.0 |
| check:blender-3d | PASS | 0.0 |
| check | PASS | 62.0 |
| install:unifai-agents | PASS (nothing to run) | 0.0 |
| install:open-webui | PASS (nothing to run) | 0.0 |
| install:openclaw | PASS (nothing to run) | 0.0 |
| install:dify | PASS (nothing to run) | 0.0 |
| install:kagent | PASS (nothing to run) | 1.0 |
| install:lightspeed | PASS (nothing to run) | 0.0 |
| install:blender-3d | SKIPPED | 0.0 |
| install | PASS (nothing to run) | 0.0 |
| start:unifai-agents | PASS | 1.0 |
| start:open-webui | PASS | 1.0 |
| start:openclaw | PASS | 3.0 |
| start:dify | PASS | 0.0 |
| start:kagent | PASS | 0.0 |
| start:lightspeed | PASS | 2.0 |
| start:blender-3d | PASS (nothing to run) | 0.0 |
| start | PASS | 16.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 0:03/0:00 | PASS (nothing to run) | 1.0 |
| 0:03/0:45 | PASS (nothing to run) | 0.0 |
| 0:03/1:45 | PASS (nothing to run) | 0.0 |
| 0:03/3:00 | PASS (nothing to run) | 0.0 |
| 0:03/4:15 | PASS (nothing to run) | 0.0 |
| 0:08/0:00 | PASS (nothing to run) | 0.0 |
| 0:08/0:45 | PASS (nothing to run) | 0.0 |
| 0:08/1:45 | PASS (nothing to run) | 1.0 |
| 0:08/3:00 | PASS (nothing to run) | 1.0 |
| 0:08/4:15 | PASS (nothing to run) | 0.0 |
| 0:13/0:00 | PASS (nothing to run) | 0.0 |
| 0:13/0:45 | PASS (nothing to run) | 0.0 |
| 0:13/2:30 | PASS (nothing to run) | 0.0 |
| 0:13/3:30 | PASS (nothing to run) | 0.0 |
| 0:13/4:15 | PASS (nothing to run) | 0.0 |
| 0:18/0:00 | PASS (nothing to run) | 1.0 |
| 0:18/0:45 | PASS (nothing to run) | 1.0 |
| 0:18/2:30 | PASS (nothing to run) | 0.0 |
| 0:18/3:45 | PASS (nothing to run) | 0.0 |
| 0:18/4:15 | PASS (nothing to run) | 0.0 |
| 0:23/0:00 | PASS (nothing to run) | 0.0 |
| 0:23/0:45 | PASS (nothing to run) | 0.0 |
| 0:23/2:30 | PASS (nothing to run) | 0.0 |
| 0:23/3:30 | PASS (nothing to run) | 1.0 |
| 0:23/4:15 | PASS (nothing to run) | 1.0 |
| 0:28/0:00 | PASS (nothing to run) | 0.0 |
| 0:28/0:45 | PASS (nothing to run) | 0.0 |
| 0:28/2:00 | PASS (nothing to run) | 0.0 |
| 0:28/3:15 | PASS (nothing to run) | 0.0 |
| 0:28/4:15 | PASS (nothing to run) | 0.0 |
| 0:33/0:00 | PASS (nothing to run) | 0.0 |
| 0:33/0:20 | PASS (nothing to run) | 1.0 |
| 0:33/0:40 | PASS (nothing to run) | 1.0 |
| 0:33/1:10 | PASS (nothing to run) | 0.0 |
| 0:33/1:30 | PASS (nothing to run) | 0.0 |
| 0:33/2:00 | PASS (nothing to run) | 0.0 |
| 0:33/2:40 | PASS (nothing to run) | 0.0 |
| 0:38/0:00 | PASS (nothing to run) | 0.0 |
| 0:38/2:00 | PASS (nothing to run) | 0.0 |
| 0:38/4:00 | PASS (nothing to run) | 0.0 |
| 0:38/6:00 | PASS (nothing to run) | 0.0 |
| 0:38/8:00 | PASS (nothing to run) | 0.0 |
| 0:38/10:00 | PASS (nothing to run) | 0.0 |
| 0:38/12:00 | PASS (nothing to run) | 1.0 |
| 0:50 | PASS (nothing to run) | 1.0 |
| stop:blender-3d | PASS (nothing to run) | 0.0 |
| stop:lightspeed | PASS (nothing to run) | 0.0 |
| stop:kagent | PASS (nothing to run) | 0.0 |
| stop:dify | PASS (nothing to run) | 0.0 |
| stop:openclaw | PASS (nothing to run) | 0.0 |
| stop:open-webui | PASS (nothing to run) | 0.0 |
| stop:unifai-agents | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall:blender-3d | SKIPPED | 0.0 |
| uninstall:lightspeed | PASS (nothing to run) | 0.0 |
| uninstall:kagent | PASS (nothing to run) | 0.0 |
| uninstall:dify | PASS (nothing to run) | 0.0 |
| uninstall:openclaw | PASS (nothing to run) | 0.0 |
| uninstall:open-webui | PASS (nothing to run) | 1.0 |
| uninstall:unifai-agents | PASS (nothing to run) | 1.0 |
| uninstall | PASS (nothing to run) | 0.0 |

## Sovereign and governed AI

77 units, 225 seconds in all. Changing units: start:quotas (Spends token budget, not undone: one short answer through sale-01's OpenClaw assistant (and one through consultant-02's)). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status:identity-personas | PASS | 15.0 |
| status:mcp-tools-by-group | PASS | 15.0 |
| status:ai-gateway-sovereignty | PASS | 12.0 |
| status:ai-gateway-routing | PASS | 17.0 |
| status:guardrails | PASS | 12.0 |
| status:quotas | PASS | 18.0 |
| status | PASS (nothing to run) | 0.0 |
| check:identity-personas | PASS | 14.0 |
| check:mcp-tools-by-group | PASS | 1.0 |
| check:ai-gateway-sovereignty | PASS | 1.0 |
| check:ai-gateway-routing | PASS | 1.0 |
| check:guardrails | PASS | 4.0 |
| check:quotas | PASS | 1.0 |
| check | PASS | 33.0 |
| install:identity-personas | PASS (nothing to run) | 0.0 |
| install:mcp-tools-by-group | PASS (nothing to run) | 0.0 |
| install:ai-gateway-sovereignty | PASS (nothing to run) | 1.0 |
| install:ai-gateway-routing | PASS (nothing to run) | 1.0 |
| install:guardrails | PASS (nothing to run) | 0.0 |
| install:quotas | PASS (nothing to run) | 0.0 |
| install | PASS (nothing to run) | 0.0 |
| start:identity-personas | PASS (nothing to run) | 0.0 |
| start:mcp-tools-by-group | PASS (nothing to run) | 0.0 |
| start:ai-gateway-sovereignty | PASS (nothing to run) | 1.0 |
| start:ai-gateway-routing | PASS (nothing to run) | 0.0 |
| start:guardrails | PASS | 0.0 |
| start:quotas | PASS | 1.0 |
| start | PASS | 11.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 0:03/0:00 | PASS (nothing to run) | 1.0 |
| 0:03/0:45 | PASS (nothing to run) | 0.0 |
| 0:03/1:30 | PASS (nothing to run) | 0.0 |
| 0:03/2:30 | PASS (nothing to run) | 0.0 |
| 0:03/3:30 | PASS (nothing to run) | 0.0 |
| 0:03/4:15 | PASS (nothing to run) | 0.0 |
| 0:08/0:00 | PASS (nothing to run) | 0.0 |
| 0:08/0:45 | PASS (nothing to run) | 0.0 |
| 0:08/1:30 | PASS (nothing to run) | 1.0 |
| 0:08/2:45 | PASS (nothing to run) | 0.0 |
| 0:08/3:45 | PASS (nothing to run) | 0.0 |
| 0:08/4:30 | PASS (nothing to run) | 0.0 |
| 0:13/0:00 | PASS (nothing to run) | 0.0 |
| 0:13/1:00 | PASS | 5.0 |
| 0:13/2:30 | PASS (nothing to run) | 1.0 |
| 0:13/3:30 | PASS (nothing to run) | 1.0 |
| 0:13/4:15 | PASS (nothing to run) | 0.0 |
| 0:18/0:00 | PASS (nothing to run) | 0.0 |
| 0:18/0:45 | PASS (nothing to run) | 0.0 |
| 0:18/2:00 | PASS (nothing to run) | 0.0 |
| 0:18/3:15 | PASS (nothing to run) | 0.0 |
| 0:18/4:15 | PASS (nothing to run) | 0.0 |
| 0:23/0:00 | PASS (nothing to run) | 1.0 |
| 0:23/0:45 | PASS (nothing to run) | 1.0 |
| 0:23/2:00 | PASS (nothing to run) | 0.0 |
| 0:23/3:15 | PASS (nothing to run) | 0.0 |
| 0:23/4:15 | PASS (nothing to run) | 0.0 |
| 0:28/0:00 | PASS (nothing to run) | 0.0 |
| 0:28/1:00 | PASS (nothing to run) | 0.0 |
| 0:28/2:30 | PASS (nothing to run) | 0.0 |
| 0:28/4:00 | PASS (nothing to run) | 0.0 |
| 0:33/10:30 | PASS (nothing to run) | 1.0 |
| 0:33/12:30 | PASS (nothing to run) | 1.0 |
| 0:38 | PASS (nothing to run) | 0.0 |
| stop:quotas | PASS (nothing to run) | 0.0 |
| stop:guardrails | PASS (nothing to run) | 0.0 |
| stop:ai-gateway-routing | PASS (nothing to run) | 0.0 |
| stop:ai-gateway-sovereignty | PASS (nothing to run) | 0.0 |
| stop:mcp-tools-by-group | PASS (nothing to run) | 0.0 |
| stop:identity-personas | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 1.0 |
| uninstall:quotas | PASS (nothing to run) | 1.0 |
| uninstall:guardrails | PASS (nothing to run) | 0.0 |
| uninstall:ai-gateway-routing | PASS (nothing to run) | 0.0 |
| uninstall:ai-gateway-sovereignty | PASS (nothing to run) | 0.0 |
| uninstall:mcp-tools-by-group | PASS (nothing to run) | 0.0 |
| uninstall:identity-personas | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

## Agentic AI

96 units, 348 seconds in all. Changing units: start:unifai-live-rag (deletes travel-and-expense-policy.md, on-call-rota-handbook.md and questions.md from consultant-01's Personal documents, uploads the two demo files of docs/demo/unifai-rag-upload/ and waits until they are DONE, then runs one turn of consultant-01-my-assistant); stop:unifai-live-rag (deletes travel-and-expense-policy.md, on-call-rota-handbook.md and questions.md from consultant-01's Personal documents). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status:unifai-agents | PASS | 16.0 |
| status:mcp-tools-by-group | PASS | 15.0 |
| status:unifai-live-rag | PASS | 10.0 |
| status:a2a-delegation-approval | PASS | 14.0 |
| status:kagent | PASS | 13.0 |
| status:okf-signed-agent-release | PASS | 14.0 |
| status:ai-gateway-sovereignty | PASS | 12.0 |
| status | PASS (nothing to run) | 1.0 |
| check:unifai-agents | PASS | 1.0 |
| check:mcp-tools-by-group | PASS | 0.0 |
| check:unifai-live-rag | PASS | 13.0 |
| check:a2a-delegation-approval | PASS | 1.0 |
| check:kagent | PASS | 3.0 |
| check:okf-signed-agent-release | PASS | 6.0 |
| check:ai-gateway-sovereignty | PASS | 0.0 |
| check | PASS | 80.0 |
| install:unifai-agents | PASS (nothing to run) | 0.0 |
| install:mcp-tools-by-group | PASS (nothing to run) | 0.0 |
| install:unifai-live-rag | PASS (nothing to run) | 0.0 |
| install:a2a-delegation-approval | PASS (nothing to run) | 0.0 |
| install:kagent | PASS (nothing to run) | 0.0 |
| install:okf-signed-agent-release | PASS (nothing to run) | 1.0 |
| install:ai-gateway-sovereignty | PASS (nothing to run) | 1.0 |
| install | PASS (nothing to run) | 0.0 |
| start:unifai-agents | PASS | 0.0 |
| start:mcp-tools-by-group | PASS (nothing to run) | 0.0 |
| start:unifai-live-rag | PASS | 31.0 |
| start:a2a-delegation-approval | PASS (nothing to run) | 0.0 |
| start:kagent | PASS | 0.0 |
| start:okf-signed-agent-release | PASS (nothing to run) | 0.0 |
| start:ai-gateway-sovereignty | PASS (nothing to run) | 0.0 |
| start | PASS | 8.0 |
| 0:00 | PASS (nothing to run) | 1.0 |
| 0:03/0:00 | PASS (nothing to run) | 0.0 |
| 0:03/0:45 | PASS (nothing to run) | 0.0 |
| 0:03/1:45 | PASS (nothing to run) | 0.0 |
| 0:03/3:00 | PASS (nothing to run) | 0.0 |
| 0:03/4:15 | PASS (nothing to run) | 0.0 |
| 0:08/0:00 | PASS (nothing to run) | 0.0 |
| 0:08/0:45 | PASS (nothing to run) | 1.0 |
| 0:08/1:30 | PASS (nothing to run) | 1.0 |
| 0:08/2:45 | PASS (nothing to run) | 0.0 |
| 0:08/3:45 | PASS (nothing to run) | 0.0 |
| 0:08/4:30 | PASS (nothing to run) | 0.0 |
| 0:13/0:00 | PASS (nothing to run) | 0.0 |
| 0:13/0:30 | PASS (nothing to run) | 0.0 |
| 0:13/2:00 | PASS (nothing to run) | 0.0 |
| 0:13/3:15 | PASS (nothing to run) | 1.0 |
| 0:13/4:15 | PASS (nothing to run) | 0.0 |
| 0:18/0:00 | PASS (nothing to run) | 1.0 |
| 0:18/0:45 | PASS (nothing to run) | 0.0 |
| 0:18/1:30 | PASS (nothing to run) | 0.0 |
| 0:18/2:30 | PASS (nothing to run) | 0.0 |
| 0:18/3:30 | PASS (nothing to run) | 0.0 |
| 0:18/4:15 | PASS (nothing to run) | 0.0 |
| 0:18/5:00 | PASS | 1.0 |
| 0:18/6:00 | PASS | 1.0 |
| 0:18/7:00 | PASS (nothing to run) | 0.0 |
| 0:18/8:30 | PASS (nothing to run) | 0.0 |
| 0:18/9:30 | PASS (nothing to run) | 0.0 |
| 0:18/10:30 | PASS (nothing to run) | 0.0 |
| 0:18/11:45 | PASS (nothing to run) | 0.0 |
| 0:18/13:00 | PASS (nothing to run) | 0.0 |
| 0:18/14:00 | PASS (nothing to run) | 1.0 |
| 0:33/0:00 | PASS (nothing to run) | 1.0 |
| 0:33/0:45 | PASS (nothing to run) | 0.0 |
| 0:33/2:30 | PASS (nothing to run) | 0.0 |
| 0:33/3:30 | PASS (nothing to run) | 0.0 |
| 0:33/4:15 | PASS (nothing to run) | 0.0 |
| 0:38/0:00 | PASS (nothing to run) | 0.0 |
| 0:38/1:15 | PASS | 0.0 |
| 0:38/2:15 | PASS | 2.0 |
| 0:38/3:30 | PASS (nothing to run) | 0.0 |
| 0:38/4:15 | PASS (nothing to run) | 0.0 |
| 0:46/0:00 | PASS (nothing to run) | 0.0 |
| 0:46/1:00 | PASS | 5.0 |
| 0:46/2:30 | PASS (nothing to run) | 0.0 |
| 0:46/3:30 | PASS (nothing to run) | 0.0 |
| 0:46/4:15 | PASS (nothing to run) | 1.0 |
| 0:51 | PASS (nothing to run) | 1.0 |
| stop:ai-gateway-sovereignty | PASS (nothing to run) | 1.0 |
| stop:okf-signed-agent-release | PASS (nothing to run) | 1.0 |
| stop:kagent | PASS (nothing to run) | 0.0 |
| stop:a2a-delegation-approval | PASS (nothing to run) | 0.0 |
| stop:unifai-live-rag | PASS | 3.0 |
| stop:mcp-tools-by-group | PASS (nothing to run) | 1.0 |
| stop:unifai-agents | PASS (nothing to run) | 1.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall:ai-gateway-sovereignty | PASS (nothing to run) | 0.0 |
| uninstall:okf-signed-agent-release | PASS (nothing to run) | 0.0 |
| uninstall:kagent | PASS (nothing to run) | 0.0 |
| uninstall:a2a-delegation-approval | PASS (nothing to run) | 0.0 |
| uninstall:unifai-live-rag | PASS (nothing to run) | 0.0 |
| uninstall:mcp-tools-by-group | PASS (nothing to run) | 0.0 |
| uninstall:unifai-agents | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

## RHOAI end to end

105 units, 262 seconds in all. Changing units: none (every action is a read or has nothing to run). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status:model-catalog-registry | PASS | 12.0 |
| status:model-serving-llmd-mig | PASS | 11.0 |
| status:external-models | PASS | 10.0 |
| status:maas-portal-api-keys | PASS | 9.0 |
| status:genai-playground | PASS | 14.0 |
| status:lora-pipeline-mlflow-kueue | PASS | 8.0 |
| status:evaluation-trustyai-evalhub | PASS | 5.0 |
| status | PASS (nothing to run) | 0.0 |
| check:model-catalog-registry | PASS | 7.0 |
| check:model-serving-llmd-mig | PASS | 8.0 |
| check:external-models | PASS | 13.0 |
| check:maas-portal-api-keys | PASS | 9.0 |
| check:genai-playground | PASS | 17.0 |
| check:lora-pipeline-mlflow-kueue | PASS | 9.0 |
| check:evaluation-trustyai-evalhub | PASS | 8.0 |
| check | PASS | 0.0 |
| install:model-catalog-registry | PASS (nothing to run) | 0.0 |
| install:model-serving-llmd-mig | PASS (nothing to run) | 0.0 |
| install:external-models | PASS (nothing to run) | 0.0 |
| install:maas-portal-api-keys | PASS (nothing to run) | 0.0 |
| install:genai-playground | PASS (nothing to run) | 1.0 |
| install:lora-pipeline-mlflow-kueue | PASS (nothing to run) | 0.0 |
| install:evaluation-trustyai-evalhub | PASS (nothing to run) | 0.0 |
| install | PASS (nothing to run) | 0.0 |
| start:model-catalog-registry | PASS (nothing to run) | 0.0 |
| start:model-serving-llmd-mig | PASS (nothing to run) | 0.0 |
| start:external-models | PASS (nothing to run) | 1.0 |
| start:maas-portal-api-keys | PASS (nothing to run) | 0.0 |
| start:genai-playground | PASS (nothing to run) | 0.0 |
| start:lora-pipeline-mlflow-kueue | PASS (nothing to run) | 0.0 |
| start:evaluation-trustyai-evalhub | PASS (nothing to run) | 0.0 |
| start | PASS | 0.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:03/0:00 | PASS (nothing to run) | 0.0 |
| 0:03/0:45 | PASS (nothing to run) | 0.0 |
| 0:03/2:00 | PASS (nothing to run) | 0.0 |
| 0:03/3:15 | PASS (nothing to run) | 0.0 |
| 0:03/4:15 | PASS (nothing to run) | 0.0 |
| 0:08/0:00 | PASS | 2.0 |
| 0:08/1:00 | PASS | 1.0 |
| 0:08/2:15 | PASS | 1.0 |
| 0:08/3:00 | PASS (nothing to run) | 0.0 |
| 0:08/4:15 | PASS (nothing to run) | 1.0 |
| 0:08/5:00 | PASS | 1.0 |
| 0:08/6:15 | PASS | 1.0 |
| 0:08/7:15 | PASS | 1.0 |
| 0:08/8:30 | PASS | 3.0 |
| 0:08/9:45 | PASS | 2.0 |
| 0:08/11:00 | PASS | 2.0 |
| 0:08/12:00 | PASS | 1.0 |
| 0:08/13:00 | PASS (nothing to run) | 0.0 |
| 0:08/14:15 | PASS (nothing to run) | 0.0 |
| 0:23/0:00 | PASS | 1.0 |
| 0:23/1:00 | PASS | 1.0 |
| 0:23/2:00 | PASS | 1.0 |
| 0:23/3:00 | PASS (nothing to run) | 0.0 |
| 0:23/4:15 | PASS (nothing to run) | 0.0 |
| 0:28/0:00 | PASS (nothing to run) | 0.0 |
| 0:28/1:00 | PASS (nothing to run) | 0.0 |
| 0:28/2:15 | PASS | 1.0 |
| 0:28/3:00 | PASS (nothing to run) | 1.0 |
| 0:28/4:15 | PASS (nothing to run) | 1.0 |
| 0:33/0:00 | PASS (nothing to run) | 1.0 |
| 0:33/0:45 | PASS (nothing to run) | 1.0 |
| 0:33/1:45 | PASS (nothing to run) | 0.0 |
| 0:33/3:00 | PASS (nothing to run) | 0.0 |
| 0:33/4:15 | PASS (nothing to run) | 0.0 |
| 0:38/0:00 | PASS (nothing to run) | 0.0 |
| 0:38/0:45 | PASS (nothing to run) | 0.0 |
| 0:38/1:45 | PASS | 1.0 |
| 0:38/2:45 | PASS (nothing to run) | 0.0 |
| 0:38/3:45 | PASS (nothing to run) | 1.0 |
| 0:38/4:30 | PASS (nothing to run) | 1.0 |
| 0:38/5:00 | PASS | 1.0 |
| 0:38/6:15 | PASS | 2.0 |
| 0:38/7:30 | PASS | 2.0 |
| 0:38/8:45 | PASS | 1.0 |
| 0:38/9:45 | PASS | 2.0 |
| 0:38/10:45 | PASS | 1.0 |
| 0:38/11:45 | PASS | 1.0 |
| 0:38/13:00 | PASS | 1.0 |
| 0:38/14:15 | PASS (nothing to run) | 0.0 |
| 0:53/0:00 | PASS (nothing to run) | 0.0 |
| 0:53/0:45 | PASS (nothing to run) | 0.0 |
| 0:53/1:30 | PASS (nothing to run) | 0.0 |
| 0:53/2:30 | PASS (nothing to run) | 0.0 |
| 0:53/3:30 | PASS (nothing to run) | 0.0 |
| 0:53/4:30 | PASS (nothing to run) | 0.0 |
| 0:58 | PASS (nothing to run) | 1.0 |
| stop:evaluation-trustyai-evalhub | PASS (nothing to run) | 1.0 |
| stop:lora-pipeline-mlflow-kueue | PASS (nothing to run) | 0.0 |
| stop:genai-playground | PASS (nothing to run) | 1.0 |
| stop:maas-portal-api-keys | PASS (nothing to run) | 1.0 |
| stop:external-models | PASS (nothing to run) | 0.0 |
| stop:model-serving-llmd-mig | PASS (nothing to run) | 0.0 |
| stop:model-catalog-registry | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall:evaluation-trustyai-evalhub | PASS (nothing to run) | 0.0 |
| uninstall:lora-pipeline-mlflow-kueue | PASS (nothing to run) | 0.0 |
| uninstall:genai-playground | PASS (nothing to run) | 0.0 |
| uninstall:maas-portal-api-keys | PASS (nothing to run) | 0.0 |
| uninstall:external-models | PASS (nothing to run) | 0.0 |
| uninstall:model-serving-llmd-mig | PASS (nothing to run) | 0.0 |
| uninstall:model-catalog-registry | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |

## Trusted platform and operations

94 units, 725 seconds in all. Changing units: start:aap-audited-operations (launches one read-only AAP job, zuno-day0-check, as the AAP admin: it creates a job record and an automation-job-* pod in zuno-aap and waits for its end (about six minutes)). Steps not run: none.

| Unit | Result | Seconds |
|---|---|---|
| status:gitops-day0-3 | PASS | 9.0 |
| status:image-signing-admission | PASS | 11.0 |
| status:okf-signed-agent-release | PASS | 14.0 |
| status:vault-pki | PASS | 8.0 |
| status:service-mesh-kiali | PASS | 8.0 |
| status:observability-trace | PASS | 11.0 |
| status:aap-audited-operations | PASS | 8.0 |
| status | PASS (nothing to run) | 0.0 |
| check:gitops-day0-3 | PASS | 7.0 |
| check:image-signing-admission | PASS | 14.0 |
| check:okf-signed-agent-release | PASS | 6.0 |
| check:vault-pki | PASS | 10.0 |
| check:service-mesh-kiali | PASS | 16.0 |
| check:observability-trace | PASS | 6.0 |
| check:aap-audited-operations | PASS | 10.0 |
| check | PASS | 26.0 |
| install:gitops-day0-3 | PASS (nothing to run) | 1.0 |
| install:image-signing-admission | PASS (nothing to run) | 1.0 |
| install:okf-signed-agent-release | PASS (nothing to run) | 1.0 |
| install:vault-pki | PASS (nothing to run) | 1.0 |
| install:service-mesh-kiali | PASS (nothing to run) | 0.0 |
| install:observability-trace | PASS (nothing to run) | 0.0 |
| install:aap-audited-operations | PASS (nothing to run) | 0.0 |
| install | PASS (nothing to run) | 0.0 |
| start:gitops-day0-3 | PASS (nothing to run) | 1.0 |
| start:image-signing-admission | PASS (nothing to run) | 1.0 |
| start:okf-signed-agent-release | PASS (nothing to run) | 0.0 |
| start:vault-pki | PASS (nothing to run) | 0.0 |
| start:service-mesh-kiali | PASS | 0.0 |
| start:observability-trace | PASS (nothing to run) | 0.0 |
| start:aap-audited-operations | PASS | 350.0 |
| start | PASS | 64.0 |
| 0:00 | PASS (nothing to run) | 0.0 |
| 0:03/0:00 | PASS | 1.0 |
| 0:03/1:00 | PASS | 2.0 |
| 0:03/2:00 | PASS | 1.0 |
| 0:03/3:00 | PASS | 37.0 |
| 0:03/4:15 | PASS (nothing to run) | 0.0 |
| 0:08/0:00 | PASS | 1.0 |
| 0:08/1:15 | PASS | 1.0 |
| 0:08/2:30 | PASS | 1.0 |
| 0:08/3:15 | PASS | 1.0 |
| 0:08/4:15 | PASS (nothing to run) | 0.0 |
| 0:13/0:00 | PASS (nothing to run) | 0.0 |
| 0:13/1:15 | PASS | 1.0 |
| 0:13/2:15 | PASS | 2.0 |
| 0:13/3:30 | PASS (nothing to run) | 1.0 |
| 0:13/4:15 | PASS (nothing to run) | 1.0 |
| 0:18/0:00 | PASS | 1.0 |
| 0:18/1:00 | PASS | 2.0 |
| 0:18/2:15 | PASS | 2.0 |
| 0:18/3:15 | PASS | 1.0 |
| 0:18/4:15 | PASS (nothing to run) | 0.0 |
| 0:23/0:00 | PASS | 1.0 |
| 0:23/1:00 | PASS | 1.0 |
| 0:23/2:15 | PASS | 1.0 |
| 0:23/3:15 | PASS (nothing to run) | 0.0 |
| 0:23/4:15 | PASS (nothing to run) | 0.0 |
| 0:28/0:00 | PASS (nothing to run) | 0.0 |
| 0:28/0:45 | PASS (nothing to run) | 0.0 |
| 0:28/1:45 | PASS (nothing to run) | 0.0 |
| 0:28/3:00 | PASS (nothing to run) | 0.0 |
| 0:28/4:15 | PASS (nothing to run) | 0.0 |
| 0:28/5:00 | PASS (nothing to run) | 0.0 |
| 0:28/6:30 | PASS (nothing to run) | 0.0 |
| 0:28/8:00 | PASS (nothing to run) | 0.0 |
| 0:28/9:15 | PASS (nothing to run) | 0.0 |
| 0:28/10:15 | PASS | 1.0 |
| 0:28/11:15 | PASS | 2.0 |
| 0:28/12:15 | PASS (nothing to run) | 0.0 |
| 0:28/13:15 | PASS (nothing to run) | 0.0 |
| 0:28/14:15 | PASS (nothing to run) | 0.0 |
| 0:43/0:00 | PASS (nothing to run) | 0.0 |
| 0:43/0:45 | PASS (nothing to run) | 0.0 |
| 0:43/2:00 | PASS (nothing to run) | 1.0 |
| 0:43/3:15 | PASS (nothing to run) | 1.0 |
| 0:43/4:15 | PASS (nothing to run) | 1.0 |
| 0:48 | PASS (nothing to run) | 1.0 |
| stop:aap-audited-operations | PASS (nothing to run) | 1.0 |
| stop:observability-trace | PASS (nothing to run) | 1.0 |
| stop:service-mesh-kiali | PASS (nothing to run) | 1.0 |
| stop:vault-pki | PASS (nothing to run) | 0.0 |
| stop:okf-signed-agent-release | PASS (nothing to run) | 0.0 |
| stop:image-signing-admission | PASS (nothing to run) | 0.0 |
| stop:gitops-day0-3 | PASS (nothing to run) | 0.0 |
| stop | PASS (nothing to run) | 0.0 |
| uninstall:aap-audited-operations | PASS (nothing to run) | 0.0 |
| uninstall:observability-trace | PASS (nothing to run) | 0.0 |
| uninstall:service-mesh-kiali | PASS (nothing to run) | 0.0 |
| uninstall:vault-pki | PASS (nothing to run) | 0.0 |
| uninstall:okf-signed-agent-release | PASS (nothing to run) | 0.0 |
| uninstall:image-signing-admission | PASS (nothing to run) | 0.0 |
| uninstall:gitops-day0-3 | PASS (nothing to run) | 0.0 |
| uninstall | PASS (nothing to run) | 0.0 |
