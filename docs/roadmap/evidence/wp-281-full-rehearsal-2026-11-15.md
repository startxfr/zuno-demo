# WP-281: full rehearsal of the catalogue (2026-11-15)

## What this is, and what it is not

It is the sum of the layer rehearsals of one day, 2026-11-15, run by session `zuno-demo-reorg-demo333` on demo333 through `make demo rehearse`, plus one golden path and one browser run. It is not one pass at one commit. The runs used four checkouts: `68ed5a62`, `fbdd31c7`, `b2dd53c1` and `d105538f`. Every report below is from 02:17 or later, which means it ran with the fixed `status` check (it fails on a dead Argo CD or a stale reconciliation); the runs before the incident of 01:38 stay in the layer evidence files as history. Reports before 10:30 ran before the ordered probe queue (602b9e24); `observability-trace` is the only demo where the queue order failed a check.

- No screen review: the reports were read, not the on-screen presenter output.
- A rehearsal PASS says the files and the page play. It does not say "show-ready" (see the caveats below and the status banner of each page).
- The path where a failed check names its probe has not been seen live: no check has failed since the fix.
- The OpenShift AI DataScienceCluster shows `Ready=False` because of the parked GuardrailsOrchestrator. It was left untouched.

## Per demo and version

Result, time of the report, units and seconds from the latest valid report of each version.

| Demo | 5-minute | 15-minute | Skipped units | Notes |
|---|---|---|---|---|
| `dify` | PASS 14:39, 11 units, 42 s | PASS 14:42, 20 units, 50 s | none |  |
| `kagent` | PASS 14:44, 11 units, 41 s | PASS 14:47, 21 units, 52 s | none |  |
| `lightspeed` | PASS 14:50, 11 units, 33 s | PASS 14:53, 19 units, 47 s | none |  |
| `openclaw` | PASS 14:56, 11 units, 68 s | PASS 15:00, 20 units, 73 s | none |  |
| `open-webui` | PASS 15:03, 11 units, 40 s | PASS 15:06, 19 units, 47 s | none |  |
| `unifai-agents` | PASS 15:08, 11 units, 46 s | PASS 15:12, 21 units, 58 s | none |  |
| `a2a-delegation-approval` | PASS 02:17, 12 units, 53 s | PASS 08:41, 21 units, 72 s | none |  |
| `ai-gateway-routing` | PASS 02:21, 11 units, 96 s | PASS 02:24, 20 units, 44 s | none |  |
| `ai-gateway-sovereignty` | PASS 10:38, 11 units, 54 s | PASS 10:41, 19 units, 57 s | none |  |
| `identity-personas` | PASS 02:33, 12 units, 46 s | PASS 08:32, 21 units, 117 s | none |  |
| `mcp-tools-by-group` | PASS 08:35, 12 units, 32 s | PASS 08:38, 22 units, 46 s | none |  |
| `quotas` | PASS 08:44, 10 units, 37 s | PASS 08:47, 19 units, 47 s | none | `start` spends token budget. |
| `guardrails` | PASS 15:15, 11 units, 46 s | PASS 15:18, 20 units, 56 s | none |  |
| `evaluation-trustyai-evalhub` | PASS 08:53, 12 units, 124 s | PASS 08:59, 22 units, 140 s | none |  |
| `external-models` | PASS 09:02, 11 units, 38 s | PASS 09:05, 20 units, 50 s | none |  |
| `genai-playground` | PASS 09:08, 11 units, 42 s | PASS 09:11, 20 units, 53 s | none |  |
| `lora-pipeline-mlflow-kueue` | PASS 09:14, 12 units, 30 s | PASS 09:17, 21 units, 48 s | none |  |
| `maas-portal-api-keys` | PASS 09:19, 11 units, 30 s | PASS 09:22, 18 units, 40 s | none |  |
| `model-catalog-registry` | PASS 09:25, 11 units, 30 s | PASS 09:28, 19 units, 47 s | none | Catalog reads only: no ModelRegistry. |
| `model-serving-llmd-mig` | PASS 09:30, 11 units, 38 s | PASS 09:33, 20 units, 52 s | none |  |
| `aap-audited-operations` | PASS 10:15, 11 units, 386 s | PASS 10:23, 21 units, 389 s | none | `start` launches one read-only AAP job. |
| `gitops-day0-3` | PASS 09:38, 11 units, 127 s | PASS 09:43, 22 units, 151 s | none |  |
| `image-signing-admission` | PASS 09:45, 11 units, 38 s | PASS 09:48, 21 units, 55 s | none |  |
| `observability-trace` | PASS 10:32, 11 units, 117 s | PASS 10:35, 20 units, 64 s | none | First reports (095138, 095428) FAILED on `check`: probes flushed in queue order. Fixed by 602b9e24 and fbdd31c7; replays PASS. |
| `okf-signed-agent-release` | PASS 09:57, 11 units, 33 s | PASS 10:00, 20 units, 80 s | none |  |
| `service-mesh-kiali` | PASS 15:29, 11 units, 111 s | PASS 10:27, 20 units, 115 s | none | `start` runs the whole golden path (read-only); the 5-minute version ran later, with the owner's go. |
| `vault-pki` | PASS 10:03, 11 units, 35 s | PASS 10:06, 21 units, 53 s | none |  |
| `unifai-live-rag` | PASS 15:21, 11 units, 73 s | PASS 15:25, 21 units, 117 s | `9:30` | Changing unit with the owner's go; the optional 9:30 row of the 15-minute version is SKIPPED (mutating) by design. |
| `blender-3d` | PASS 10:44, 13 units, 42 s | PASS 10:47, 23 units, 51 s | `install`, `uninstall` |  |
| `world-model` | PASS 10:50, 12 units, 22 s | PASS 10:52, 21 units, 32 s | `install` | PASS is not show-ready: demo off, no GPU node. |

| Workshop | Run | | Skipped units | Notes |
|---|---|---|---|---|
| `three-experiences` | PASS 10:58, 45 units, 206 s | | none |  |
| `five-experiences` | PASS 11:05, 94 units, 269 s | | `install:blender-3d`, `uninstall:blender-3d` |  |
| `agentic-ai` | PASS 11:49, 96 units, 348 s | | none | First report (112439) FAILED on `start:unifai-live-rag` and `stop:unifai-live-rag` (`demo_dir` inside a workshop). Fixed by b2dd53c1; replay 114921 PASS. |
| `rhoai-end-to-end` | PASS 11:12, 105 units, 262 s | | none |  |
| `sovereign-governed-ai` | PASS 11:17, 77 units, 225 s | | none | `start:quotas` spends token budget. |
| `trusted-platform-ops` | PASS 11:38, 94 units, 725 s | | none |  |

## Golden path and browser checks

- `make demo golden-path`, run first: `RESULT: PASS`, 72 s, 14 moments, 13 PASS and one ROADMAP row (`world-model`: "not installed (zuno_world_model_enabled is false): shown as roadmap, not live").
- `make demo browser`: `RESULT: PASS`, 31 s, five checks (`unifai`, `open-webui`, `kagent`, `dify`, `openclaw`), all PASS.

## Failures found and their fixes

Three bugs in the demo files, found by these rehearsals and fixed the same day.

- Probe order (`observability-trace`): the engine flushed the queued probes in queue order, so `trace` ran before `unifai-tekos`, whose run id it reads. Fixed by 602b9e24 (queue in the probe script's order). See [WP-278](wp-278-foundation-rehearsals-2026-11-15.md).
- Probe detail: a failed check did not say which probe failed. Fixed by fbdd31c7 (one check row per probe, a failed check names the probe and why).
- `demo_dir` inside a workshop (`agentic-ai`): `start:unifai-live-rag` and `stop:unifai-live-rag` found their helper in the workshop's directory. Fixed by b2dd53c1, with a catalogue test. See [WP-280](wp-280-workshops-rehearsals-2026-11-15.md).
- Earlier the same day, the incident of 01:38 and the `status` defect (a dead Argo CD was not detected): see the conditions of [WP-275](wp-275-experiences-rehearsals-2026-11-15.md).

## Caveats

- `world-model`: PASS is not show-ready. The demo is switched off, there is no GPU node, the application is not installed; `install` is SKIPPED. See [WP-279](wp-279-blender-world-model-rehearsals-2026-11-15.md).
- `model-catalog-registry`: the registry part is told, not run (no ModelRegistry instance).
- `blender-3d`: `install` and `uninstall` are SKIPPED: they write or remove the add-on on the workstation that runs the rehearsal.
- Changing units were run with the owner's named go: `quotas` and `sovereign-governed-ai` (token budget spent, not undone), `aap-audited-operations` and `trusted-platform-ops` (one read-only AAP job), `unifai-live-rag` and `agentic-ai` (consultant-01's Personal documents).

## What stays manual on stage

Each layer file lists it per demo: [WP-275](wp-275-experiences-rehearsals-2026-11-15.md), [WP-276](wp-276-governance-rehearsals-2026-11-15.md), [WP-277](wp-277-rhoai-rehearsals-2026-11-15.md), [WP-278](wp-278-foundation-rehearsals-2026-11-15.md), [WP-279](wp-279-blender-world-model-rehearsals-2026-11-15.md), [WP-280](wp-280-workshops-rehearsals-2026-11-15.md).
