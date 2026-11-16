# GIF afternoon of 2026-11-16: takes after the owner's order of 13:12 CET

This file continues the [sprint evidence](wp-289-gif-sprint-2026-11-16.md) for the takes of the afternoon: those of the demos
the owner's order of 13:12 CET sent to the team (see "Owner's order of 13:12 CET" in the sprint file). Takes are run by session
`zuno-demo-reorg-demo333` with the owner's go in its own session. Every fact below is read from the take directory under
`~/.cache/zuno/demo/recordings/`, or marked "as relayed". The writer (`zuno-demo-reorg-writer`) opens the marker images itself.

Privacy rule for this file: it never copies a page title, a page id, a URL of a company page or a person's name from a frame. It
says what the frame holds ("seven real Confluence onboarding pages, role titles").

## Summary

| Demo | Take directory | GIF bytes | Seconds | Moments | Published in | Reviews |
|---|---|---|---|---|---|---|
| `mcp-tools-by-group` (re-take, row 1:30 in full) | `mcp-tools-by-group-20261116-133009` | 1 996 199 | 53.0 | 7 | `a9186a2c` (replaces `c1230da7`) | recording session: N = 54, as relayed; writer: 2 of 18 images opened |

## Per demo

### `mcp-tools-by-group` re-take (browser, two personas): published, replaces `c1230da7`

Status: **published in `a9186a2c`** (`devel`, 2026-11-16 13:52 CET), replacing the GIF of `c1230da7`, on the owner's "go pour le remplacement de
mcp-tools-by-group" given in `zuno-demo-reorg`'s session at 13:46 CET, before the publication commit of 13:52 (as relayed; the writer has not seen it). Writer's check on `devel`:
`docs/assets/img/demo/mcp-tools-by-group.gif` is 1 996 199 bytes, SHA-256 `10fbb00b1d70...`, equal to the take's GIF. The page rows 1:30
and 2:45 were picked after it as `93dca48f`. The catalogue still has 17 GIF files (a replacement adds none).

| Item | Value |
|---|---|
| Take | `mcp-tools-by-group-20261116-133009`: `sale-01` (`pass`, 8 markers in 22.7 s) and `consultant-02` (`pass`, 9 markers in 29.7 s); first attempt; rescout clean; cut at `devel` `f25167c7` (assist's full row 1:30, `4dc34b1e`) |
| Owner's go | The owner's go for the take, given in `zuno-demo-reorg-demo333`'s session (as relayed) |
| Created and cleaned | 4 chats created (2 per persona) and deleted by id; owned 1 before and 1 after for each persona; `private_addresses` count 0 for both |
| GIF | 1 996 199 bytes, SHA-256 `10fbb00b1d70...`, 53.0 s, 960x656, 7 moments (11/11/4/3/10/11/3 s), blob `50626c6dd1ff...` |

**What the images show** (writer opened `consultant-02` `q2-done` and `sale-01` `q2-done`; the other 16 not opened):
`consultant-02`: the answer to "Find our onboarding pages in Confluence." is a table with the columns page id, title, space and
URL, and **seven real Confluence onboarding pages**, all with role titles (in French), followed by a sentence saying the pages cover
onboarding for project managers, developers, QA testers and cluster operators. The URLs are links on the company's Atlassian
host, with space keys and numeric page ids. No person's name and no email on this image. The first line of the answer sits half
under the chat header (the cosmetic flag of the recording session). `sale-01`: a red cross on "View Result from
`zuno-mcp_drive.document.search`", then an answer saying it has no access to the Confluence space or to the credentials, and asking for
the exact name, the location or a link. The wording differs from the published GIF; the meaning is the same.

**Review.** The recording session: N = 54 (18 marker images and 36 sampled frames), as relayed; its reviewer read every
title on the screen of `consultant-02` and found no person's name and no email. The answer of `consultant-02` has 1613
characters (as relayed). The writer opened 2 images and sampled no frames.

**Point for the owner's review of the GIF.** The table is real company content, which the owner allowed (order of 13:12 CET).
It also shows the Atlassian host and page ids in the URLs; these are not secrets, but the repository is public.

**Pages.** The "You should see" cells of rows 1:30 and 2:45 now state what this take shows (`93dca48f`).

**What stays on the server.** The chats were deleted. The Confluence search of `consultant-02` and the failed Drive call of `sale-01`
stay in the platform's tool-call records (ADR-0618 clause 12).

## Scout: aap-audited-operations (as relayed)

Facts relayed by the coordinator; the writer saw no scout files.

- Scout at `d69bdb89`, with the owner's go in demo333's session. The go included the creation of the AAP user `consultant-03`.
- The Keycloak sign-in to AAP works on demo333.
- `consultant-03` sees 20 `zuno-day0-check` runs, 14 launched by `zuno-mcp`. A reader does see jobs it did not launch.
- The scout then failed on the read-only guard: AAP's page sends `POST /api/gateway/v1/session/`. Five requests were refused and
  nothing was written. Decision of the coordinator: that exact POST is let through and counted.
- Open: the AAP user `consultant-03` stays on the cluster if AAP created it. Demo333 is to confirm.
- Page: the "not rehearsed" notes on rows 0:00 and 2:00 are replaced by these facts, dated 2026-11-16.

## Re-take: model-serving-llmd-mig, NODE column (as relayed)

- Take `model-serving-llmd-mig-20261116-152658`, cut at `devel` `830c999d`. The recording session reports: gate 29 lines; each model has 1 under exactly one MIG column; the NODE column is filled; the quota is as before.
- GIF 46.1 s, about 1.0 MB. The recording session's review: N = 10 (2 marker images and 8 frames). The writer saw none of them.
- The frames show node names. The owner accepted that for this demo only, as relayed. **No node name is copied here.**
- Sent to the owner as a replacement of the published `21bca7e2`.

## Re-scout: aap-audited-operations (as relayed)

- `aap-audited-operations-20261116-153130-scout` at `devel` `3d48acfe`: 14 of 14 steps pass.
- The session-refresh POST was counted 5 times (2 bytes each). Refused requests: none. Private addresses: 0. No new AAP user effect.
- `zuno-day3-test` is not in the templates this reader sees. The status word is "Success". The instance group is below the window.
- Page: row 0:45 no longer states the counts 17 and 8 or names `zuno-day3-test` as the last template. The assist is to check the true list.

## Incident of 15:07 CET: Playwright version (as relayed)

- A merge of `origin/main` into `devel` (`e5626745`, not by the zuno-demo sessions) brought Dependabot's `08533cac`: Playwright 1.48.0 to 1.55.1 in `evaluations/browser/package.json`. Every script runs the v1.48.0 image, so every fresh browser run failed at launch.
- Found within minutes by the coder, the assist and demo333. Fixed by the coordinator in `3d48acfe`: the pin goes back to 1.48.0. The zuno-demo session checked the 164 open alerts: none on Playwright or npm, so it was not a security update.
- Open for the owner: `main` still carries 1.55.1. Either an ignore rule, or one planned move of the package and the image together.

## Disclosure by demo333

`make demo check` typed without an id defaulted to `guardrails` and ran its golden-path probe twice. Two `consultant-02` prompts were spent. Nothing else changed.

## On `devel`, not yet scouted

`observability-trace`, `genai-playground` (scout first) and the notes hook.

### Published: model-serving-llmd-mig replaced (2026-11-16, 16:04 CET)

`5dda6298` replaces `docs/assets/img/demo/model-serving-llmd-mig.gif` with the take above (937 892 to 1 022 964 bytes). The writer checked the
file in the commit against the take's GIF: 1 022 964 bytes, SHA-256 `eadf8c53c353...`, equal. The owner's go ("ok, go pour le
remplacement de model-serving-llmd-mig par la reprise") was at 16:04:41 CET, before the commit at 16:04:51, as read by the coordinator
from its log. The alt text now says the recording shows the server each model runs on. The writer read the take's `transcript.txt`:
the four models, each with 1 under one MIG column, and the NODE column filled (node names not copied). The catalogue still has 17 GIF files.
Page: the "(untested command)" mark on row 1:00 is lifted, because the take ran that command.

## Open items for the owner

- `main` still carries Playwright 1.55.1 while `devel` is pinned to 1.48.0 (see the incident above).
- The AAP user `consultant-03`: demo333 is to confirm whether AAP created it.
- Node names are visible in the published `model-serving-llmd-mig` GIF, accepted by the owner for this demo only.

## Scouts of the remaining demos (as relayed)

Scouts at `a6f7635b` and `5477cf1a`, with the owner's go in demo333's session. Nothing was written on the cluster. The writer saw no scout files.

| Demo | Result |
|---|---|
| `quotas` | The Grafana part is fine. The GitHub part failed because the page never scrolled. Fixed in `ae3d5cef`; rescout pending. |
| `lora-pipeline-mlflow-kueue` | The menu was dumped. Three findings on selectors and addresses. Fix pending. |
| `unifai-agents` | `ai-ops-01`: the take path is fine. `consultant-02`: failed at `enter` (click timeout), and the page lands on an earlier broken session (404, "Workflow Unavailable"). |
| `observability-trace` | The chat take path is fine. The trace stopped at the **Authorize Access** page for the service account `tempo-tempo` of `zuno-monitoring` (scopes `user:info` and `user:check-access`, as `ai-ops-01`). The owner's decision is pending in demo333. Same kind as the Grafana "Authorize" click declared earlier. |
| `genai-playground` | The subscription shown is `gpt-oss-20b-agents`; the page says `gpt-oss-20b-ocp-ai-ops` (rows 0:00 and the checklist). To check with the assist before any edit. The MCP server `zuno-mcp-gateway` is listed but not connected in a fresh browser. Coordinator's decision: no token in the recorder; the GIF covers rows 0:00 and 0:45 and the MCP settings as found; rows 1:45 and 3:00 stay words. |
| `dify`, `guardrails` | Not scouted. They wait for the owner's answer on how the Dify admin password is read from Vault. |

The WP-290 brief now says the same under `genai-playground`.

### genai-playground: subscription and MCP row (as relayed by the assist)

Scout at `a6f7635b`, 2026-11-16 at 16:11. In **Settings**, **Model** the portal shows `ai-ops-01` the subscription `gpt-oss-20b-agents`; the page named `gpt-oss-20b-ocp-ai-ops`. The model matches. Not seen: whether the dropdown offers `gpt-oss-20b-ocp-ai-ops`. The take never chooses a subscription and no caption names one. The MCP row shows `zuno-mcp-gateway` with "0 active" in a fresh browser; the GIF caption says "listed, no token in this browser".

Page: row 0:00 and the checklist now say the subscription shown may differ (option A of the assist). Possible platform finding, **not verified**: if `gpt-oss-20b-agents` is the agents' subscription and is offered to a person, a person draws on the agents' budget. The assist has not read the `MaaSSubscription` objects. Whether it goes on the deferred list is the coordinator's call.
