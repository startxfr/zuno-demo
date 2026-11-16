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
- Page: row 0:45 no longer states the counts 17 and 8. The take shows the pager "1 - 10 of 25", so `zuno-day3-test` is on a later page.

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
- **Dify, Zuno Agent's configuration.** On the Studio frame of the `dify` take, the card **Zuno Agent** reads "Edited at 11/16/2026 18:42"; the other applications read 11/05 or 11/06. The first `dify` take of the evening (failed at the workflow step) ran at 18:42 UTC, as relayed. A take or scout probably let an autosave of the Agent's configuration through, because the Dify guard refused only a guessed list of paths. Instructions and tools look unchanged on screen; this is **not proven either way**. To do: compare the Agent's configuration with its reference.

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

Page: row 0:00 and the checklist say a subscription of `ai-ops-01` is shown and that the default is not stable (see the take below). Possible platform finding, **not verified**: if `gpt-oss-20b-agents` is the agents' subscription and is offered to a person, a person draws on the agents' budget. The assist has not read the `MaaSSubscription` objects. Whether it goes on the deferred list is the coordinator's call.

## Takes of the late afternoon (not published)

### aap-audited-operations (published)

| Item | Value |
|---|---|
| Take | `aap-audited-operations-20261116-165220`: `consultant-03`, `pass`, 7 markers, cut at `a67ae533` (as relayed) |
| Owner's go | Given in `zuno-demo-reorg-demo333`'s session (as relayed) |
| Created and cleaned | `created` empty, `cleaned` null; owned 0 before and 0 after; `private_addresses` count 0 |
| GIF | 3 232 151 bytes (read from the take), SHA-256 `d3c837e41a9d...`, 49.0 s, 960x656, 7 moments |
| Notes in `markers.json` | job 1454; `zuno-mcp` jobs visible 14; session refreshes 5, 2 bytes, no keys |

**Review.** The recording session: N = 18 (6 marker images and 12 frames), as relayed; the writer opened 2 images (`templates.png`,
`job.png`) and no frames. `templates.png`: the Automation Templates list as `consultant-03`, 10 of 25 on the first page, launch
buttons greyed, no person's name; the account name `consultant-03` is in the header. `job.png`: the Details tab of job 1454, status
Success, launched by `zuno-mcp`, inventory `zuno`, credential `zuno-cluster-reader` (a name; no value). The Details frame ends
before the instance group. Reported by the recording session, accepted: the AAP account name `admin` on the project page. The writer
did not open that image. No node name was seen on the two images the writer opened.

**Published** as `bbdec534`, on the owner's go of 18:36:28 CET (coordinator's log), before the commit at 18:36:50. The writer compared the file in the commit with the take's GIF: 3 232 151 bytes, SHA-256 `d3c837e41a9d...`, equal.

### quotas (published)

| Item | Value |
|---|---|
| Take | `quotas-20261116-172034`: `ai-ops-01`, `pass`, 6 markers in 99.4 s, cut at `e8f96b8d` (as relayed) |
| Created and cleaned | `created` empty; owned 0 before and 0 after; `private_addresses` count 0 |
| GIF | 5 016 713 bytes (read from the take), SHA-256 `76d62e17e770...`, 45.0 s, 960x656, 5 moments |

The GIF is over the 5 MB aim (5.0 MB, under the 8 MB limit).

**Review.** The recording session lists 5 opened images and 1 contact sheet of 12 frames, as relayed; its report says 6 images, so
the writer counts what it can verify: the take holds 6 marker images and no frame files. The writer opened 2 images (`panel.png`,
`evidence.png`) and no frames. `panel.png`: the Grafana panel "One group across the experiences: tokens (over range)", last 24
hours, columns client and group, token counts per group, no person's name. Group names are role and source names
(`consultant/confluence-...`, some cut by the column); the writer judges them not private, the owner is to confirm. An avatar sits at the top right.
`evidence.png`: the repository page `quotas.md` on GitHub, with the WP-190 evidence paragraph (no secret). The recording session reports
one transitional "Loading…" frame. `make demo start quotas` was **not** run: the panel held spend from earlier the same day.

**Published** as `41ebd891`, on the same go, before the commit at 18:36:51. The writer compared the file in the commit with the take's GIF: 5 016 713 bytes, SHA-256 `76d62e17e770...`, equal.

The catalogue now has 19 GIF files of 30 demos. No "(untested ...)" mark was lifted: the marks left on these two pages are on rows these takes did not run (`quotas` 13:00 and the 15-minute prompt).

## Scouts, later (as relayed)

- Tempo authorization: the click for `ai-ops-01` was made and is stored as declared (`tempo-tempo` in `zuno-monitoring`, scopes `user:info` and `user:check-access`), after the owner's decision in demo333's session.
- `genai-playground` rescout: 11 of 11 steps.
- `lora-pipeline-mlflow-kueue`: the Experiments page shows "No experiments" for the project Zuno MLOps. Page row 2:45 is at risk; to settle with the assist.
- `dify`: the sign-in lands on a new Home page and shows four apps. The Vault read of the Dify admin password was done by demo333 with the owner's agreement: 3 helper runs, each creating and deleting for a few seconds an `ansible-seeder-login-token` in `zuno-vault`. The value was never printed.
- On `devel`, unscouted: `maas-portal-api-keys`, `openclaw` (scout only), `a2a-delegation-approval`.

### dify: first scout facts (as relayed by the coder)

Scout of 2026-11-16 at 16:43 (`scout-enter.png`); the writer opened that image. After the two sign-ins Dify opens on a **Home** page ("Welcome back", the single Dify account displayed as "x", workspace "x's Workspace"), not on Studio; Studio is one click on the left menu. Four applications are listed, not three: the three examples and a fourth, **Strategic Consulting Expert** (an agent, edited 11 days ago). Its origin was not checked. Not yet seen: Studio, the Agent's chat pane, the workflow run. Page: row 0:00 and the checklist state this.

## Scouts at `8f655617` and a workstation finding (as relayed)

Owner's gos in demo333's session.

- `dify`: 9 of 9. The Agent page was still loading when read. The workflow run form was seen; nothing was started.
- `guardrails`: the paths of both takes are fine.
- `openclaw`: 6 of 6. The storage key `openclaw-device-identity-v1` was added in the browser. Earlier session titles are visible in the sidebar: none is copied here, and the take must not show them.
- `maas-portal-api-keys`: failed at `enter`. The portal lists the keys with a `POST .../api-keys/search`, and the scout guard refused it. Nothing was created.
- One more Vault read of the Dify admin password (value never printed).
- Workstation: six orphaned containers of the coordinator's own timed-out offline suites ran from 14:38 and loaded the box (load 15, then 3 after they were stopped). `timeout` kills the script, not its container. The coder is asked to add an exit trap.

### genai-playground (published)

| Item | Value |
|---|---|
| Take | `genai-playground-20261116-183758`: `ai-ops-01`, `pass`, 6 markers, cut at `8f655617` (as relayed) |
| Owner's go | Given in demo333's session (as relayed) |
| Created and cleaned | `created` empty, `cleaned` null; owned 0 before and 0 after; `private_addresses` count 0 |
| GIF | 1 046 464 bytes (read from the take), SHA-256 `df603fdf6cf0...`, 41.0 s as relayed, 6 moments |
| Model calls | One, as relayed. The answer: "La capitale de la France est Paris." |

A first attempt, `genai-playground-20261116-183648`, failed with no GIF: the project showed the empty state "Create your playground" (never pressed) although the server was Ready. It was transient; the one allowed retry passed.

**What the images show.** The recording session reports N = 17 (5 marker images and 12 frames in a contact sheet), as relayed; the writer opened 2 images (`q1-done.png`, `mcp.png`) and no frames. `q1-done.png`: the Playground with the answer above, the Settings panel on **Model**, the model `publishers/zuno-ai-run/models/gpt-oss-20b` and the subscription `gpt-oss-20b-ocp-ai-ops`; the header shows the account name `ai-ops-01`; no node name, no address. `mcp.png`: the **MCP** tab, one server `zuno-mcp-gateway`, "0 active", a lock icon, no token.

**Subscription.** This take shows `gpt-oss-20b-ocp-ai-ops`; the scout five minutes earlier showed `gpt-oss-20b-agents`. The portal's default is not stable between sessions. The page no longer names one as "the" subscription. Deferred entry n stays unverified.

**What stays on the server.** Whether the playground keeps this chat server-side is not known: nothing was deleted. The model call stays in the platform's call records.

**Published** as `1a4ff89b`, on the owner's go of 20:05:27 CET (coordinator's log), before the commit at 20:06:07. The writer compared the file in the commit with the take's GIF: 1 046 464 bytes, SHA-256 `df603fdf6cf0...`, equal. It is the first demo of WP-290 with a GIF. The catalogue has 20 GIF files of 30 demos. No "(untested ...)" mark on rows 0:00 and 0:45 needed lifting (none there); rows 1:45 and 3:00 stay words, the prompt of row 3:00 being untested in the playground.

### observability-trace: rescout of 19:33 (as relayed by the coder)

- Row 1:45 as written found the wrong trace: the newest `model_call` of `consultant-02` was a failed call of its OpenClaw assistant (`zuno.agent=openclaw`, `error=true`, a context-length error). The persona is shared by Dify, OpenClaw and UnifAI. The walkthrough now searches with `zuno.persona=consultant-02 zuno.agent=tekos` and refuses a span whose tags say error. The page says the same.
- The span detail showed 11 of the 12 tags listed in row 3:00; `zuno.run_id` was missing, on that OpenClaw span. To confirm on a Tekos span from the first take's log. Row 5:00 copies `zuno.run_id` from the span and stays "not rehearsed".
- The Tempo search page shows a yellow banner, "Jaeger UI is deprecated". The results do not show the tag filter as text.

### unifai-agents (take, not published)

| Item | Value |
|---|---|
| Take | `unifai-agents-20261116-194517`: two personas, cut at `fb2b47f9` (as relayed) |
| Owner's go | Given in demo333's session (as relayed) |
| `consultant-02` | `pass`, 8 markers in 48.5 s; one session created and deleted; owned 21 before and 21 after; `private_addresses` count 0 |
| `ai-ops-01` | `pass`, 5 markers in 37.7 s; one session created and deleted; owned 21 before and 21 after; `private_addresses` count 0 |
| GIF | 6 083 220 bytes (read from the take), SHA-256 `384298501f55...`, 55.0 s, 960x656, 7 moments |

The GIF is over the 5 MB aim (about 5.8 MiB) and under the 8 MB limit.

**What the images show.** The recording session's own count is 6 of 13 marker images opened (partial at first). Update, as relayed: demo333 later opened all 13 marker images and 27 frames and searched the take log for patterns, and found nothing private; the earlier session titles are test prompts only. The writer opened 2 images (`consultant-02/q1-done.png`, `ai-ops-01/q-done.png`) and no frames. `consultant-02/q1-done.png`: the Collaboration Hub, team `agent-tekos`, workflow `tekos`, answer "I can help you with precise, concise technical questions about OpenShift, Kubernetes, and the surrounding Red Hat ecosystem." The live-workflow panel lists `knowledge-tekos`; the model line reads `local-gpt-oss-maas · gpt-oss-20b`. `ai-ops-01/q-done.png`: the answer says no pod of `zuno-ai-run` is in a failed or pending state, all are `Running` or `Completed` with no restarts; the mark "1 tool used · 1 call" is on the step; the tool is not named. No node name and no address on either image. **Points for the owner:** the header shows the persona display names, and the session list shows earlier session titles (accepted by the owner, as for `unifai-live-rag`; none is copied here).

As relayed: the `consultant-02` second answer is generic troubleshooting steps, not opened by the writer.

**Page.** Row 3:00 now says what was seen: a short answer from the live cluster with the "1 tool used" mark, worded differently at each run. The caption of the cut list still says "real pods and events"; that is the coder's, to change.

**Not published.** Sent to the owner; the publication waits for the caption fix and a re-cut.

### dify (take failed, as relayed)

The take failed after the Agent turn: the workflow step went to the web-app page. One `consultant-02` turn was spent. The conversation was deleted. No run-log entry was left.

## Later facts (as relayed)

- `observability-trace`: the chat take passed. The trace take **failed**: it opened the OpenClaw error trace again, not its own. One `tekos` answer was spent.
- `lora-pipeline-mlflow-kueue`, rescout at `396c4440`: the pipeline step is fine with versions shown `[v0-4-0-tekos]`. MLflow's own UI (workspace `zuno-mlops`) lists no experiment in its default view. Update (rescout of 20:41 CET, as relayed): the switch to the Model training view was made, and MLflow's own UI lists no experiment in workspace `zuno-mlops` in either view; the dashboard's Experiments page says "No experiments". The Jobs page lists `lora-comage-4c28m` as Complete. Row 2:45 has nothing to show; the GIF ends at the training job (the assist's `32b5342a` drops the moment). Deferred entry o.

## Scouts at `d80f25ef` and the re-cut (as relayed)

`openclaw` 7 of 7; `maas-portal-api-keys` 6 of 6 (empty key list, Create dialog seen and cancelled, nothing created); `dify` 9 of 9; `guardrails` both paths fine; `observability-trace`: the search finds one recent Tekos trace of `consultant-02`, but the click opened Jaeger's Compare page (selector bug). The `unifai-agents` re-cut was refused once by `gif.py` because a caption was 64 characters, and redone at `2b9f3dfb`. The owner's decision on the `openclaw` session cleanup is in the WP-290 brief.

## Take: dify, not proposed for publication

| Item | Value |
|---|---|
| Take | `dify-20261116-210141`: `consultant-02`, `pass`, 9 markers in 48.0 s, cut at `d80f25ef` (as relayed) |
| Created and cleaned | One conversation created and deleted; owned 0 before and 0 after; `private_addresses` count 0 |
| GIF | 3 694 923 bytes (read from the take), SHA-256 `379a9da29cbb...`, 49.0 s as relayed, 7 moments |
| Run log | The workflow run (id as relayed) succeeded and **stays** in Dify's run log. The user cannot delete it. |
| Blocked | The editor's `workflows/draft` autosave was refused in the browser (as relayed) |

**Review.** demo333 opened 9 marker images (as relayed). The writer opened 2 images (`studio.png`, `run-done.png`) and no frames. `studio.png`: Studio with four cards; **Zuno Agent** reads "Edited at 11/16/2026 18:42", **Zuno Technical Documentation** 11/06 17:27, **Zuno Confluence Search** 11/06 16:30, **Strategic Consulting Expert** 11/05 12:18; the account name is "x". `run-done.png`: the workflow editor with the Test Run result, a list of real Confluence page titles with their codes; no person's name seen; the editor header says "Auto-Saved 09:55:47". The owner accepted real titles at 13:12 CET; none is copied here. A company acronym is part of the titles on that frame: note it for the owner's review.

**Not proposed for publication yet**, because of the Zuno Agent finding above. All Dify takes are on hold; the coder is making the guard default-deny (as relayed).

## Limit of every GIF published so far: write guards (assist's survey, as relayed)

In a take, only `aap-audited-operations` and `genai-playground` refuse writes by default. The Grafana, lora and Tempo walkthroughs watch writes and fail after the fact. `open-webui`, `identity-personas`, `mcp-tools-by-group`, `unifai-live-rag`, `kagent`, `lightspeed` and `model-catalog-registry` had no take-time write guard: their own created chats and sessions were deleted and counted, but what else their pages may have sent was not blocked or listed. Decision of the coordinator: one shared default-deny guard in the recorder, the walkthroughs not yet taken first.

