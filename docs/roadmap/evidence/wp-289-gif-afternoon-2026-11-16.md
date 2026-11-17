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
- **Dify, Zuno Agent's edited date (cause measured, content never compared; `dify` is published with the effect declared).** The date moved three times on 2026-11-16 (18:42, 20:02 and 20:51 UTC), once per `dify` take at its Agent turn in Debug & Preview; opening the page moves nothing. The third take ran under the default-deny guard and no configuration write left the browser for the Agent: Dify's server moves the date when the Agent answers, or when its conversation is deleted (not separated). The comparison of the Agent's configuration with a reference is no longer needed for this cause; keep it only as "content never compared". Detail below.

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
- The span detail showed 11 of the 12 tags listed in row 3:00; `zuno.run_id` was missing, on that OpenClaw span. That note was about an **OpenClaw** span, not a Tekos one. **Update 2026-11-17: measured on a Tekos span.** In the `observability-trace` take of 04:17 CET (section below), the `ai-gateway` `model_call` span of the take's own Tekos session carries `zuno.run_id`, equal to the id of the UnifAI session the `chat` take created (the writer compared it with `markers.json` and the coder measured it too). So the run id link of row 5:00 is now measured as far as the span; the Grafana step of that row is still not rehearsed. Row 5:00 copies `zuno.run_id` from the span and stays "not rehearsed".
- The Tempo search page shows a yellow banner, "Jaeger UI is deprecated". The results do not show the tag filter as text.

### unifai-agents (published)

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

## Take: guardrails (passed; published at 05:19 CET on 2026-11-17)

Owner's named go in demo333, take at `df554323` (as relayed). Directory `guardrails-20261116-233501`; the writer read it. Both takes are `pass`.

| Item | `agent` take | `dashboard` take |
|---|---|---|
| Persona | `consultant-02`, with Dify's administrator account | `ai-ops-01` |
| Markers | 5: `login`, `agent`, `q-sent`, `q-done`, `end` (40.6 s) | 4: `login`, `dashboard`, `detections`, `end` (37.4 s) |
| Created and cleaned | One conversation created and deleted | none |
| Owned before and after | 0 and 0 | 0 and 0 |
| `private_addresses` | count 0 | count 0 |

As relayed: the DAN sentence was sent once; the model answered "I'm sorry, but I can't comply with that." The writes sent to Dify, in order: `POST` refresh-token (401), `POST` login (200), `POST` `apps/<id>/chat-messages` (200). The declared effect happened: the Zuno Agent's edited date moved again (a fourth move; the writer did not read the date). `markers.json` of the two takes carries no `writes` key; the list comes from the coordinator.

**The count on the panel is not only the take's.** `make demo check guardrails`, which `record` requires, runs the golden-path probe, and the probe sends the same prompt. It ran twice before the take (as relayed): at 22:16 UTC it failed on a page timeout, at 22:34 UTC it passed, and the owner approved the re-run. So the detections on the panel are the probes' plus the take's, and the last step is the take's. The panel frame the writer opened shows the series `dify (detected)` at 1 from about 22:19 and at 2 at its right end, and the writer cannot say from the frame which request made each step.

**Review.** The writer opened 3 of the 9 marker images, and no frames of a GIF: `agent/q-done.png` (the Zuno Agent's Orchestrate page; the DAN sentence; the answer above; the account name in the corner is a single letter; no node name or address), `dashboard/detections.png` (the panel "Guardrails evaluations by experience (over range)", last hour; legend entries `dify (clean)`, `dify (detected)` and the other clients; no node name or address), and `agent/login.png` (the Keycloak sign-in, empty fields). As relayed, demo333 counted 4 of 9 reviewed and a full review was asked.

**No GIF at first.** The first cut was 38.0 s (the answer came in 4.4 s) and `gif.py` refused it. The coordinator's `16eb4a9a` makes it 42.0 s on the take; the re-cut is pending (as relayed). Not published.

**Page.** `guardrails.md` row 0:45 says what was seen on 2026-11-16; row 2:00 says the detection is recorded, not blocked, and that Check has already sent the prompt once, so the count is the probes' plus the live step's.

## After midnight, 2026-11-17 (this file continues here)

The takes of the night of 2026-11-16 to 2026-11-17 go on in this file, so that the guardrails facts stay in one place.

### guardrails: candidate re-cut (not published)

The writer read the take directory `guardrails-20261116-233501` and `guardrails.gif.json`.

| Item | Value |
|---|---|
| GIF | `guardrails.gif`, 691 243 bytes (0.7 MB), 43.0 s, 7 moments, written 23:47 CET |
| Cuts, as relayed | `16eb4a9a` (42.0 s), then `0fb526ee`: a still of `agent/q-done` so the model's reply is in the GIF, caption "0:45  The model itself declines; the gateway blocked nothing" (43.0 s) |
| Review, as relayed | Complete by demo333: the 9 marker images and 12 frames, then 9 frames of the final cut. The writer opened no frame of the GIF; the 3 marker images it opened are in the section above |
| Status | Sent to the owner. **Not published.** |

### Scouts under the write guard (as relayed)

Scouts at `6df63b54` and `6f836c28`. The only write refused anywhere was `POST /api2/blueprints/blueprint.validate`, on every UnifAI hub page. Refusing it made the hub say "Workflow Unavailable" and disabled the composer. The coder's `6f836c28` allows it as a read. After that fix `writes.refused` is empty for `unifai-agents`, `a2a-delegation-approval`, `observability-trace` (chat), `maas-portal-api-keys` and `openclaw`. The writer read none of these scout files. The offline scripts retry "pasta failed" once (`6f836c28`).

### Slow first loads (deferred entry p, as relayed)

Between about 00:20 and 00:35 CET the first load of UnifAI and of the Tempo search UI took more than 30 s in 4 of 7 attempts, at a workstation load of 2 to 3. All UnifAI pods were Running. Cause unknown. The coder raises the walkthroughs' first-load waits to 90 s. Entry p of the [sprint evidence](wp-289-gif-sprint-2026-11-16.md).

### Two failed takes at `feaf7d32` (WP-290, 2026-11-17)

The owner answered **one dialog holding both questions at 02:28:30 CET on 2026-11-17**, choosing "Take maas-portal-api-keys" and "Take openclaw" (time read by `zuno-demo-reorg` in demo333's session log, as relayed). So one time covers both gos, before the takes' own starts, read from `markers.json`: `maas-portal-api-keys` 01:29:12 UTC (02:29 CET), `openclaw` 01:31:32 UTC (02:31 CET). **Which commit the takes ran at:** demo333 reports `feaf7d32`; the text of the maas question named `devel` `6f836c28` and "scout 6/6 ok". Neither `markers.json` records a commit, and no other file of the two take directories names one, so the writer cannot confirm either from the files. What git shows (measured by the coordinator, and the writer compared the SHA-256 of the blobs): `walkthroughs/maas-portal-api-keys.mjs` and `walkthroughs/_helpers.mjs` are byte-identical at `6f836c28` and `feaf7d32`, and of these three files only `record.mjs` differs (the 90 s navigation timeout), so the scout named in the question covered the same walkthrough as a take at `feaf7d32`. Neither take is retried yet. The writer read both directories and opened the images named below.

**`maas-portal-api-keys`**, take `maas-portal-api-keys-20261117-022910`, persona `ai-dev-01`.

| Item | Value |
|---|---|
| Status | `fail` after 3 markers (`login`, `portal`, `keys`): "the create dialog does not show gpt-oss-20b-ocp-ai-dev as chosen" |
| Created and cleaned | `created` empty, `cleaned` null; owned 0 before and 0 after; `private_addresses` count 0 |
| Writes | Two `POST` of the key-list search, both 200, both listed as reads. None refused, none tolerated. No key was created |

`failed.png` (opened): the Create API key dialog over the portal. The subscription field reads `gpt-oss-20b-ocp-ai-dev`, so the model **is** chosen; the name field holds a generated test name; the models table lists one model with its token limit; the account `ai-dev-01` is in the header. No node name and no address. The check was wrong, not the portal (as relayed, and consistent with the frame). The one-time key dialog was **not** reached, so it is still unseen. As relayed: the coder's `a8afb3a6` makes the check read the dialog's visible texts and held values; it is on `devel` as `723c5e24` (suite for this demo PASS, pushed about 02:50 CET). The walkthrough hash moves, so a rescout comes before the next take.

**`openclaw`**, take `openclaw-20261117-023130`, persona `consultant-02`.

| Item | Value |
|---|---|
| Status | `fail` after 6 markers (`login`, `ui`, `session`, `q-sent`, `q-done`, `end`): "a question was sent but the sidebar lists no new session" |
| Created and cleaned | `created` empty, `cleaned` false; owned **6 before and 7 after**; `private_addresses` count 0 |
| Writes | none sent, none refused |

What the frames show (opened `session.png`, `q-done.png`): in `session.png` the sidebar lists 7 sessions, the first marked "now" with a default `agent:default:dashboard:` name; in `q-done.png` the sidebar lists 7 sessions again, the first marked "now" under a title the assistant derived from the question, and the other six unchanged. So the take's new session was probably the first entry, **renamed by the assistant**, which the take did not recognise. That is the writer's reading of two frames, not a measurement. The coder's reading, as relayed and not yet verified live: the cause is that every sidebar row got the same id (a hash of an empty string), so the take could not tell its own row from the others; fix `9e553815` is on `devel` as `7dce084a` (committed at 03:01:06 CET on 2026-11-17 (commit time) and pushed right after, as relayed; the `openclaw` walkthroughs suite and the offline recorder suite PASS, as relayed); the walkthrough hash is now `dac2d8a2...` and a rescout is asked of demo333. Not yet tested live. The writer read the scout of 2026-11-16 at 22:42 UTC (`openclaw-20261116-234233-scout`): its `sessions` step reads `rows` 6 and `distinct` 1, which is consistent with that reading and was not flagged at the time. The question was answered (relayed and visible). The session was not deleted: it stays in `consultant-02`'s assistant, with the assistant's possible memory of the question (declared effect). As relayed: the owner answered "Leave it" at 04:09:56 CET on 2026-11-17: the session stays in `consultant-02`'s assistant. One Confluence answer of `consultant-02`'s budget was spent.

**Privacy.** `q-done.png` shows an answer listing real Confluence page titles, page ids and addresses of the company's wiki. This file copies none of them. As relayed, the owner chose "comme guardrails" for `openclaw` (the real titles may be shown); the next take goes through the privacy review. The earlier sessions' names in the sidebar are not copied either.

### Rescouts of 2026-11-17, 02:34 to 02:38 CET (standing go in demo333, as relayed)

The writer read the five `scout.json` files and the sub-scouts of `observability-trace`; it opened no image. Times are the scouts' `started` stamps (UTC) plus one hour.

| Scout directory | Started (CET) | Result read | Writes (read from `scout.json`) | Walkthrough SHA-256 |
|---|---|---|---|---|
| `observability-trace-20261117-023434-scout` | 02:34:36 | `done`: `chat` 5 of 5, `trace` 7 of 7 | `chat`: `blueprint.validate` (404, a read) and `session.join` (200); `trace`: none; refused none | `a3479e6a...` |
| `observability-trace-20261117-023608-scout` | 02:36:10 | same | same | `a3479e6a...` |
| `a2a-delegation-approval-20261117-023526-scout` | 02:35:28 | `done`, 6 steps | 4 sent (`session.join`, two `blueprint.validate`, `edit_lock.statuses`, all 200); refused none | `e746dd49...` |
| `a2a-delegation-approval-20261117-023659-scout` | 02:37:02 | `done`, 6 steps | same 4 sent; refused none | `e746dd49...` |
| `maas-portal-api-keys-20261117-023832-scout` | 02:38:34 | `done`, 6 steps; `changes` 0 | 4 sent, all the key-list search (200, reads); refused none | `54e88fcc...` |

- **The earlier scouts of the night failed on first loads** (the 00:xx CET scouts of both `observability-trace` and `a2a-delegation-approval` read `fail`, at `chat`, `trace` or `enter`). Of these five scouts, all five read `done`. Demo333 attributes this to the 90 s waits (as relayed: "4 of 4 enters hold against 4 of 7 failing"); the writer does not count it that way and does not know the cause. Workstation load 3.4 to 4.9 during the scouts (as relayed).
- **`observability-trace` trace step:** both `trace` sub-scouts skip the trace and the tags: "the search lists no trace now: ask Tekos as consultant-02, then scout again". So the result link stays **untested** until a take that asks Tekos first (as relayed).
- **`observability-trace` `chat`:** `blueprint.validate` returned 404 here, 200 on the `a2a` scouts. It is listed as a read and nothing was refused. The writer does not know why. The `chat` scout declares a change: the OpenShift Authorize Access page for the Tempo search UI's proxy as `ai-ops-01` (the OAuth authorization already listed in "What the cluster keeps" of the sprint evidence).
- **`maas-portal-api-keys`:** the walkthrough hash `54e88fcc...` is the one the coordinator named for `723c5e24`. Nothing was created.
- Demo333 asks the owner for new named take gos: `maas-portal-api-keys` first, then `observability-trace`; `openclaw` and `a2a-delegation-approval` are held (as relayed).

### Recorder change: multi-take scouts keep their details (`bddb4d38`)

The coder's `bddb4d38` (commit time 03:09:04 CET) is on `devel` as `b1e7c538` (commit time 03:22:16 CET on 2026-11-17; both times read from git by the writer). As relayed: in a run of several takes, the top `scout.json` now keeps each take's step details, named `<take>/<step>`, and a `writes` key whose lines start with "<take>: ". It changes `record.mjs` and one offline case only; no walkthrough hash moves. Suites passed, as relayed. The rescouts above predate it: their top `scout.json` has no step details, which is why the writer read the sub-scout files. `fb79efc8` is on `devel` as `118e2ecc` (as relayed).

### Take: maas-portal-api-keys (passed; published at 05:19 CET on 2026-11-17; WP-290)

Take `maas-portal-api-keys-20261117-041246`, persona `ai-dev-01`, started 03:12:56 UTC (04:12 CET). The owner answered **one dialog at 04:09:56 CET on 2026-11-17** with three choices, "Take maas-portal-api-keys", "Take observability-trace" and "Leave it" (time read by `zuno-demo-reorg` in demo333's log, as relayed): the go is before the start at 04:12 CET. `observability-trace` has its go at the same time and was not run yet, as far as the coordinator knows. "Leave it" is the owner's decision on the failed `openclaw` take's session: it stays in `consultant-02`'s assistant. The writer read `markers.json` and opened 4 of the 8 marker images (`keys`, `created`, `calls`, `answer`) and no GIF frame.

| Item | Value |
|---|---|
| Result | `pass`, 8 markers in 38.5 s: `login`, `portal`, `keys`, `create-form`, `created`, `calls`, `answer`, `end` |
| Created and cleaned | One API key, named `zuno-demo-gif-` plus a timestamp; `cleaned` true; owned 0 before and 0 after; `private_addresses` count 0 |
| Writes (read) | 2 key-list searches (200, reads) and 1 `POST` of `api-keys` (201, "create the take's key"); refused none, tolerated none |
| Commit | Not recorded in `markers.json`. Demo333 reports `devel` `7dce084a` (commit time 03:01:06 CET, read from git by the writer); the question put to the owner named `723c5e24` and "rescout 6/6 ok". The writer compared the blobs: `walkthroughs/maas-portal-api-keys.mjs` and `walkthroughs/_helpers.mjs` are byte-identical at the two commits; only `record.mjs` differs (the owned comparison by counts, as relayed). So the walkthrough is the same either way |

As relayed: the key was revoked (the delete answered 200) and the gateway then answered 403 with it; the recorder drew three calls: 401 without the key, 200 with it, then one chat completion on `gpt-oss-20b` (118 tokens, on `ai-dev-01`'s subscription). The writer saw the first two calls on `calls.png` and the third, with `"total_tokens":118`, on `answer.png`. The writer saw no frame of the revoke or of the 403 (`end.png` has the same size as `answer.png`; not opened).

**The shown-once dialog is seen for the first time.** `created.png`: "API key created", the warning "This is the only time you will see this key", a field that reads `sk-oai-` followed by dots (masked), an eye button and a copy button, then the name, the subscription (`gpt-oss-20b-ocp-ai-dev`) and "30 days". The key's value is not on the frame. The recorder's own line that says the portal does not show the masked key is wrong, per this frame (as the coordinator says). The writer copies no key id; the name's timestamp is not copied either.

The other frames: `keys.png` is the empty list ("No API keys") of `ai-dev-01`, no node name, no address. `calls.png` and `answer.png` are the recorder's own page ("Calls made by the recorder with the key just created", "The key is not shown"), which names the gateway as `$MAAS`, not by address. The `portal` marker is a loading spinner (relayed; not opened). Demo333 reports it opened 9 PNGs and saw nothing private (as relayed); the directory holds **8** PNGs, matching the 8 markers (the writer and the coordinator counted them), so "9" is a miscount.

**No GIF yet.** `gif.py` refused three captions over 60 characters. The coordinator's `f6083840` (`gif.yml` only) shortens three captions and shows row 0:00 on `keys` instead of the spinner; dry-run 6 moments, 43.0 s planned (as relayed). Demo333 re-cuts. Not published; no owner publication go.

**What the cluster keeps (as relayed):** possibly one key listed as revoked in `ai-dev-01`'s portal, and the traces and metrics of the three calls.

### maas-portal-api-keys: cut v2 (published at 05:19 CET)

The coordinator's `63ace45b` (commit time 04:27:23 CET, from git; `gif.yml` only) is the second re-cut of the same take. The first re-cut (`f6083840`) ended its motion on the pressed Create button, so the created-key dialog was in no frame while a caption named it; demo333 caught it and sent that cut to the owner with caveats, not recommended (as relayed).

| Item | Value (read from `maas-portal-api-keys.gif.json`, written 04:29 CET) |
|---|---|
| GIF | 614 271 bytes (0.6 MB), 41.1 s, 960x656, 7 moments, 411 frames at 100 ms; SHA-256 `2bd2899a421e...` |
| Review by demo333 (as relayed) | A scan of 13 frames: no spinner, every caption true to its frame |
| Review by the writer | A contact sheet of 13 frames (every 35th, plus the last), not a full scan. Seen: the Keycloak sign-in; the empty key list; the Create form with the Subscription chooser open and then closed; the created-key dialog with the key masked, twice; the recorder's calls page growing from 2 calls to 3. The last caption, "The platform keeps the models, the budget and the revoke", is over the recorder's calls page |
| The revoke | In **no frame**: it is in the log only (as relayed). The last caption is the page's close, as the coordinator says |

**One flag, confirmed.** In the frames where the chooser is open, the Subscription list shows five names (the coordinator names them: `gpt-oss-20b-ocp-ai-dev`, `gpt-oss-20b-agents`, `qwen35-9b-agents`, `qwen35-9b-wesh-agents` and `qwen36-27b-instruct-agents`; the writer read them at sheet size, not at full size). The coordinator checked with `git grep` that all five are already in this public repository, so the GIF discloses nothing new. It is the same matter as the deferred entry on the agents' subscriptions offered to a developer persona (entry n). The key's own name, a generated test name with a timestamp, is readable in the Create form and the created dialog; the key's value is masked after `sk-oai-` (see the take section above).

The coordinator proposes it for publication; it is sent to the owner as v2. **Not published**; no owner go yet.

### observability-trace: take at 04:17 CET (chat passed, trace failed)

Take `observability-trace-20261117-041737`. The owner's go is the 04:09:56 CET dialog (above, as relayed); the coordinator and demo333 say it ran at `7dce084a`; the take's files record no commit. The writer read both `markers.json` and `takes.json` and opened `chat/q-done.png`, `trace/search.png` and `trace/failed.png`.

| Take | Persona | Result | Detail |
|---|---|---|---|
| `chat` | `consultant-02` | `pass`, 5 markers in 120.1 s | One session created and deleted; owned 21 before and 21 after; private addresses 0 |
| `trace` | `ai-ops-01` | `fail`, 3 markers (`login`, `search`, `trace`) | "the span's tags zuno.client, zuno.agent are not drawn inside the window: the picture would not hold the row's proof"; created none; writes none; private addresses 0; `traces_listed` 1 |

- **Slow loads.** In the `chat` take the markers are late: `login` at 28.4 s, `hub` at 83.4 s. The writer does not know why; it fits entry p (slow first loads), not proven.
- **Writes of `chat`** (read; 16 sent): `blueprint.validate` answered 404, `session.join`, `edit_lock.statuses`, two `blueprint.validate` answered 200, `user.session.create`, `session.typing`, `session.leave`, `session.join`, four `session.typing`, `user.session.submit`, `session.heartbeat` and one `DELETE` of the session. None refused. As the coordinator says, the take's own session ran, so case 2 of deferred entry q (Tekos not visible to the persona) did **not** happen. Whether the first 404 is case 1 stays unknown.
- **`q-done.png`** (`chat`): the Collaboration Hub as `consultant-02`, team `agent-tekos`, the take's session "Just now", the answer drawn and the live workflow "Execution Complete". Privacy flags: the persona's display name shows in the header, and the sidebar lists earlier sessions with their titles (prompts of earlier users). The writer copies none of them; a GIF of this take would need the sidebar and the name judged.
- **`search.png`** (`trace`): the Tempo search UI, service `ai-gateway`, operation `model_call`, tags set, last 15 minutes, **one trace**, 61 spans, 7 services, "2 minutes ago". The trace is the take's own, found by search.
- **`failed.png`** (`trace`): the opened trace, a span's tags window. In view: `zuno.latency_ms`, `zuno.model`, `zuno.model_kind`, `zuno.outcome`, `zuno.persona` (`consultant-02`), `zuno.prompt_tokens`, `zuno.provider`, `zuno.request_id`, `zuno.run_id`, `zuno.task`. `zuno.client` and `zuno.agent` are above the window (scrolled out), as the check says. So the result link works and the proof tags are on the page. The writer notes that `zuno.run_id` is on this `ai-gateway` span and equals the id of the session the `chat` take created (compared against `markers.json`; not copied here). That bears on page row 5:00 (the run id on a Tekos span); the page has not been changed.
- **A walkthrough matter** (scrolling), with the coder, as relayed. The go is spent; a new take needs the fix and a new named go. Nothing published.

### observability-trace: the coder's fix `5030c11a` (as relayed)

The coder's `72d5e03d` is on `devel` as `5030c11a` (commit times 04:54:54 and 04:55:02 CET, read from git by the writer). As relayed: the take films the span's tags in two markers, `tags` (`zuno.persona`, `zuno.client`, `zuno.agent`, `zuno.model` and `zuno.estimated_cost_usd` must be drawn inside the window; a row under the UI's fixed header no longer counts) and the new `tags-run` (`zuno.persona` and `zuno.run_id`). A named tag outside the window fails the take; a named tag the span does not carry is logged, not failed. The scout searches the last six hours (read only; a take keeps 15 minutes). The cut list gains one still, `tags-run`, 5 s, caption "The run it names is the consultant's own session". The walkthrough hash is now `00ea523e...`. The `ONLY=observability-trace` suite, `test_gif` and consistency passed on the coder's side. A rescout is asked of demo333; no take before a new owner go. The page row 5:00 is **not** changed now: the coordinator asks the owner with the GIF.

### Rescouts at `5030c11a`, 05:06 and 05:07 CET (standing go in demo333, as relayed)

The writer read `observability-trace-20261117-050600-scout` (top, `chat` and `trace` files) and `openclaw-20261117-050716-scout`, and opened `trace/scout-tags.png`. Times are the scouts' `started` stamps (UTC) plus one hour. Neither scout shows an address in this file: the scout files hold the cluster's host names, which the writer does not copy.

**`observability-trace`** (started 05:06:10 CET, walkthrough `00ea523e...`): `done`, 2 takes; `chat` 5 steps, `trace` 7 steps; refused none; writes sent 2 (the `chat` take's, 0 for `trace`); private addresses 0. The six-hour search found 1 trace (the one of the failed take, 61 spans, 1 `model_call` span).

- **The `tags` step** (read from the file): `caption_in_window` **false**, `proof_in_window` **true**, `run_id_shown` true. At marker `tags` the window holds `zuno.model`, `zuno.latency_ms` and `zuno.estimated_cost_usd` and none of the other nine named tags. At marker `tags-run` it holds `zuno.persona`, `zuno.task`, `zuno.model_kind`, `zuno.provider`, `zuno.model`, `zuno.latency_ms`, `zuno.outcome` and `zuno.run_id`. `zuno.client` and `zuno.agent` are in neither window; `zuno.classification` is in neither either. All 12 named tags exist on the span (the `tags` list of the step).
- **Why:** the span's tag list is alphabetical, so `zuno.persona` cannot sit in one window with `zuno.agent` and `zuno.client`. The coordinator concludes that the framing of `5030c11a` is wrong and that a take would fail the same way (as relayed; the writer read the file, not the code). No take was asked.
- **A new privacy finding.** `scout-tags.png` (opened): below the tags a span row `zuno.user_sub` is drawn as the last row, with a UUID value, and above `zuno.latency_ms` a list of group names ("consultant/..." entries). The coordinator says `zuno.user_sub` is the Keycloak subject of `consultant-02` and that its value is not in the repository (checked with `git grep`), and that the group names are already in the repository. Carrying the subject on the span is the platform's stated design, not a defect: ADR-0593 says the raw token `sub` stays in the span attribute `zuno.user_sub` and in logs, for audit (the writer read the line), and ADR-0563 names the same span attribute; only the picture is the demo's matter. **The writer copies neither the value nor the group names.** The frame also shows `zuno.request_id` and `zuno.run_id` values (not copied).
- **Requested of the coder (as relayed):** a framing that shows `agent`, `client`, cost and model in the first picture and `persona` and `run_id` in the second, and that fails the take if `user_sub` is drawn at either marker. Framing only; no page row hidden.

**`openclaw`** (started 05:07:25 CET, walkthrough `dac2d8a2...`): `done`, 8 steps, no write seen by the guard (HTTP only; see the limit in the next section), refused none, private addresses 0. The `sessions` step: **rows 7, told apart by link, distinct 7** (the 6 earlier ones plus the one the owner chose to leave). The session menu lists seven entries (Pin session, Mark as unread, Rename..., Fork, Move to group, Archive session and Delete...). So the fix `7dce084a` holds live for the scout: the rows have links. Demo333 asks the owner for the `openclaw` take go (as relayed). The scout did not type or open anything (`nothing_typed` true, `sessions_opened` 0).

### Published at 05:19 CET on 2026-11-17: guardrails and maas-portal-api-keys

On the owner's go "go de publication de guardrails et de maas-portal-api-keys." at **05:18:40 CET** (the coordinator's session log, as relayed), before both commits at **05:19:12 CET** (read from git by the writer). The writer compared each file in the commit with the GIF the take directory holds now.

| Demo | Commit | Take | File | SHA-256 |
|---|---|---|---|---|
| `guardrails` | `e75b0ce8` | `guardrails-20261116-233501`, cut `0fb526ee` | 691 243 bytes, 43.0 s as in `guardrails.gif.json` | `331b0759959e...`, equal |
| `maas-portal-api-keys` | `f17dc35b` | `maas-portal-api-keys-20261117-041246`, cut v2 (`63ace45b`) | 614 271 bytes, 41.1 s | `2bd2899a421e...`, equal |

Each commit adds the GIF and its page caption: `guardrails.md` (the caption says the model declines, the gateway blocks nothing, and the panel's count includes the check's probes) and `maas-portal-api-keys.md` (the caption says the recorder kept the real key out, so the field shows a masked value, and that the key was revoked at the end of the take). The tree of `f17dc35b` holds **25** GIF files in `docs/assets/img/demo`. The caption of `guardrails` and the declared effect of its take (the Zuno Agent's edited date moved again) are in the section above. `maas-portal-api-keys.md` carries no "(untested ...)" mark on rows 0:00 to 4:15, so none was lifted. The writer did not open the frames of the final cuts of `guardrails`; of `maas-portal-api-keys` it saw the contact sheet of 13 frames above.

WP-289 has 17 of 18 (`observability-trace` remains) and WP-290 has 2 of 6.

### openclaw: second take, failed at the delete (WP-290, 2026-11-17)

Take `openclaw-20261117-052046`, persona `consultant-02`, started 04:21:08 UTC (05:21:08 CET, from `markers.json`; the directory name reads 05:20:46, the time it was made). The owner answered one dialog, "Take openclaw", at **05:17:35 CET on 2026-11-17** (read by `zuno-demo-reorg` in demo333's session log, as relayed), before the start. The question's text named `5030c11a` and demo333 says it ran there; `markers.json` records no commit. The writer read `markers.json` and opened `q-done.png`.

| Item | Value |
|---|---|
| Result | `fail`, 6 markers (`login`, `ui`, `session`, `q-sent`, `q-done`, `end`), the last at 72.4 s |
| Created and cleaned | One session created; `cleaned` **false**; owned **7 before and 8 after**; `private_addresses` count 0 |
| Detail (the file's words) | "the session the take created (...) is STILL listed after Delete...: delete it by hand in consultant-02's assistant; consultant-02 does not own the same items after the take: 1 more, 0 fewer" |
| Writes | none sent, none refused. **This proves nothing for `openclaw`** (see the limit below) |

- **The fix of `7dce084a` holds live.** The take found its own session, the newest of the sidebar, by its link (the rescout of 05:07 showed 7 distinct rows). That is what the first take could not do.
- **The question was answered.** `q-done.png` (opened): the chat after the question, an answer listing wiki pages, and the sidebar with 8 rows: the take's session on top marked "now", under a title the assistant derived from the question; the session left by the first failed take marked "3h" under a similar title; then six older rows. `end.png` has the same size as `q-done.png` and was not opened, so the writer saw **no frame after the Delete... click**: the failure comes from the take's own check after it.
- **Privacy.** The answer frame lists real wiki titles, page ids and addresses; this file copies none. The earlier sessions' titles are not copied either. The owner chose "comme guardrails" for `openclaw` (as relayed).
- **Cause, the coder's diagnosis, unverified live (as relayed).** The coder reports about 80% certainty, in its own words, from the take's video (frames extracted offline): the Control UI asks its confirmation in a **native browser dialog** (`window.confirm`); neither `record.mjs` nor any walkthrough listens to dialogs, so the browser driver dismissed it, which answers Cancel, and nothing was sent. The video shows the menu with Delete... and then the row still there, and no in-page dialog; a native dialog cannot be in the video, which is the unseen 20%. The writer did not view the video and checked nothing of this. Fix asked of the coder: accept one native confirm, only around the Delete... click of the take's own session. A delete-only run for the two left sessions is being put to the owner, not built.
- **A limit of the write guard, stated plainly (as relayed).** The Control UI works over its **WebSocket**, which the write guard does not see. So `writes: none` proves nothing for `openclaw`, either way: it does not show that nothing was written, and it does not show that something was. This holds for every `openclaw` scout and take above, including the scout of 05:07 CET that read "no write at all".

**Owner's decision on `openclaw`**, answered at **05:30:42 CET on 2026-11-17** in `zuno-demo-reorg`'s session (an answer to a question with options, read there in its log, as relayed): **"Suppression seule d'abord"** (delete only first). Before any new take, a separate delete-only run, asking no question, deletes only the two sessions the failed takes left in `consultant-02`'s assistant, by ids written as constants (it refuses any other). It proves the delete live without spending an answer; then the take. Not chosen: a direct take after the fix; a take that no longer deletes (the session left, declared); suspending `openclaw`. Each live run still needs its own named go in demo333's session. The coder builds the fix, then the delete-only walkthrough (`openclaw-delete-left.mjs`, no cut list, no GIF).

**What the cluster keeps now (as relayed):** **two** sessions in `consultant-02`'s OpenClaw assistant, left by the two failed takes; the assistant's possible memory of two questions (declared effect); two answers of `consultant-02`'s budget spent. The owner's "Leave it" (04:09:56 CET) covered the first session only; demo333 tells the owner about the second. **No third take** until the coder has diagnosed the delete from the take's files.

### observability-trace: the coder's framing `745e9ba2` (pushed)

The coder's `745e9ba2` is on `devel` as `c54b5eb0`, commit time 05:42:46 CET (read from git by the writer; the original `745e9ba2` is dated 05:24:22 CET). As relayed: agent, client, cost and model are required in the `tags` marker and persona and run_id in `tags-run`; the take stops before the picture if `zuno.user_sub` is in the window; the cut holds stills only; walkthrough hash `09ad43ad...`. The `ONLY=observability-trace` suite, `test_gif` and consistency passed on the coordinator's side. A rescout is asked of demo333; no take before a new owner go.

### openclaw: the fix and the delete-only run are on devel (as relayed; not run live)

Both commits are dated 05:53:20 CET in git (the writer read them): `7fcf92f0` (the coder's `30f6ab8e`) and `5852fa69` (the coder's `43f4f4fa`). As relayed by the coordinator:

- **`7fcf92f0`:** the `openclaw` walkthrough accepts **one** native dialog of type confirm, armed only around the Delete... click of the take's own session. It logs the dialog's type and length, never its text; any other dialog is dismissed and fails the take. The scout's `sessions` step now lists rows as `{id, age, rank}`, with no title. Hash `ab1b780c...`.
- **`5852fa69`:** `walkthroughs/openclaw-delete-left.mjs`, the delete-only run the owner chose at 05:30:42 CET: `consultant-02`, markers `login`, `ui`, `end`, no question, nothing typed. The ids to delete are constants: one known and one placeholder; a real run refuses to start, before any sign-in, while the placeholder is there. It fails, deleting nothing, if a listed id is absent, and fails if any other session is lost or gained. Shared code moved to `walkthroughs/_openclaw.mjs`, outside the walkthrough hash like `_dify.mjs`. No demo page, no cut list, no GIF. Hash `e259cdb2...`.
- **Checks on the coordinator's side:** `ONLY=openclaw` and `ONLY=openclaw-delete-left` PASS, consistency 0 problems, `test_demo_catalogue` and `test_capture` OK.
- **A limit to state.** `make demo scout` and `make demo record` need a catalogue entry (the coordinator read `presenter.py` `cmd_scout` and `cmd_record`), so this run is called through `record.sh` directly. That skips the freeze check and the confirmation notice of `presenter.py`. The owner's named go in demo333, naming both ids, stands in their place. **Not run live yet.**

### observability-trace: rescout at `c54b5eb0` (directory `observability-trace-20261117-054400-scout`)

The writer read `scout.json` of the top and of `trace/`, and opened `trace/scout-tags.png` and `trace/scout-tags-run.png`. Started 04:44:12 UTC (05:44 CET); walkthrough `09ad43ad...`; `done`, 8 steps in `trace`; refused none, writes none, private addresses 0. The scout declares the Tempo OAuth authorization of `ai-ops-01` (already in "What the cluster keeps").

- **`user_sub`:** the file says `user_sub_in_window` false, and neither image shows a `zuno.user_sub` row.
- **`tags` picture** (file): `caption_in_window` **true**; agent, classification, client, model, latency and cost are in the window, persona, task, model_kind, provider, outcome and run_id are not. **The image disagrees with the scout on one row:** the `zuno.model` row is cut by the window's bottom edge and its value is not readable, so the scout's "in window" counted a partly drawn row. Demo333 saw the same (as relayed).
- **`tags-run` picture:** the coordinator says `proof_in_window` is **false** (as relayed; the writer printed only the `tags` step's flat per-tag list, where `zuno.run_id` is false, and did not read a `tags-run` flag). The image shows `zuno.run_id` on the bottom edge, overlapped by the row's Copy and JSON buttons: the id is not cleanly readable.
- **`zuno.groups`** is drawn **open** as a list of about ten group names in both pictures (the writer saw it in both; the names are not copied; the coordinator says they are already in the repository).
- **Asked of the coder (as relayed):** "drawn" means the whole row inside the window with room under `zuno.run_id`, and `zuno.groups` collapsed with the UI's own arrow, said in the take's notes. No take is asked. The trace stays searchable by the scout until about 09:19 CET, six hours after the take's 03:19 UTC (as relayed).

### openclaw-delete-left: scout at `5852fa69` (directory `openclaw-delete-left-20261117-061001-scout`)

Demo333 scouted it direct through `record.sh --scout`: it found no freeze marker, and the coordinator ran `guard.check_freeze('scout')` read only and found no freeze (as relayed). The writer read `scout.json` and opened no image (all five scout images have the same size: nothing was clicked, as the file says).

| Item | Value (read from `scout.json`) |
|---|---|
| Started | 05:10:13 UTC (06:10 CET); walkthrough `e259cdb2...` |
| Result | `done`, 5 steps; refused none; writes none seen by the guard (and the guard does not see this UI's WebSocket); private addresses 0 |
| Closed step | `nothing_typed` true, `nothing_clicked` true, `native_dialogs` 0 |
| `sessions` step | rows **8**, told apart by link, **distinct 8**; each row listed as id, age and rank only (no title) |
| Left sessions | One constant is matched: the session at rank 1, age 49 minutes, `in_left` true. The second constant is a **placeholder** (null): no row is marked for it |
| Declared change | The file's `changes` line says a real run clicks Delete... in the menu of each of the 2 sessions the two failed takes left and accepts the native confirmation each opens |

- **Which row is which (as relayed).** Demo333 says the second take's session is rank 1 (the file agrees: it is the one listed as left), and the **first** failed take's session is rank 2, age 4 hours, matched by demo333 by title prefix, age and neighbours, "about 95% sure" in its words. The file does not mark rank 2 as left, because the second constant is still a placeholder. The writer did not look at titles and does not confirm the match.
- **The `owned` count of 7 against 8 rows (the coder's design, relayed by the coordinator, who did not re-read the code; the writer did not read it either).** In `openclaw-delete-left`, `owned()` counts the rows **not** in the left list, so that the recorder's before and after comparison proves nothing else was lost or gained. With one valid id in the list (the placeholder matches no row) that is 8 minus 1, so 7. Once both ids are filled it should read **6 before and 6 after** a real run. If the next scout does not read 6, that is a finding.
- **No session ids in this file.** The coordinator says they are not secrets but need not be in the docs: the text says "the two ids named in the walkthrough file".
- **Next (as relayed).** The coder fills the second constant in one commit; then a new scout must read both listed; then demo333 asks the owner for the named go. Not run live.
- **Update: the second constant is filled (as relayed).** The coder's `1eb320bf` is on `devel` as `73567024` (committed 06:27:31 CET, the original at 06:27:14 CET; both read from git by the writer). `openclaw-delete-left` now names its two sessions (hash `dba9cac0...`). The refusal with a placeholder stays tested on a mounted variant, and one more offline case runs the file as it is against the stand-in: its ids are not listed, so nothing is deleted and the run fails. `ONLY=openclaw-delete-left` passed on the coordinator's side. Demo333 rescouts: both ids must read listed and `owned` must read 6; then it asks the owner for the named go. My earlier commits are on `devel` as `d9a83ec1` (`3e5c6d33`) and `de906ef3` (`e8e79fab`, 06:31:57 CET).

### openclaw-delete-left: the delete-only run passed (2026-11-17, WP-290)

**The owner's named go:** the answer **"Delete both"** at **06:36:37 CET on 2026-11-17** in demo333's session (read by `zuno-demo-reorg` in its log, as relayed). Demo333 says the question stated both ids, their ages, that no question is asked, the two native confirms, the direct run, the WebSocket the guard does not see, its about-95% match of the second id and the consequence of a wrong row (as relayed; the writer did not read the question).

**Rescout before** (`openclaw-delete-left-20261117-063505-scout`, started 05:35:07 UTC = 06:35 CET, walkthrough `dba9cac0...`; the writer read `scout.json`): `done`, 5 steps; the `sessions` step reads rows 8, distinct 8, **both constants listed** (`left` true for both), **placeholders 0**; ranks 1 and 2 (ages 1 hour and 4 hours) are the two marked left, the other six are not; `owned` reads **6**, as the coder's design predicted; nothing typed, nothing clicked, native dialogs 0, private addresses 0; refused none, writes none seen.

**The run** (`openclaw-delete-left-20261117-063720`, started 05:37:37 UTC = 06:37 CET; the writer read `markers.json` and opened `end.png`):

| Item | Value |
|---|---|
| Result | `pass`, 3 markers (`login`, `ui`, `end`) in 32.2 s |
| Counts | `listed_before` 8, `deleted` 2, `listed_after` 6; owned **6 before and 6 after**, same; created none |
| Writes | none sent (the guard cannot see the Control UI's WebSocket, so this proves nothing) |
| Private addresses | count 0 |
| Commit | Not recorded in `markers.json`. Demo333 says `devel` `de906ef3`, run direct through `record.sh` (no presenter freeze check; no freeze, checked by the coordinator earlier), as relayed |
| Native confirms (as relayed) | Two accepted; the log gives type and length only |

`end.png` (opened): the Control UI with **6** sessions listed (ages 14 hours, then 11 and 12 days), the entry "agent:default:main" highlighted, no typed text and no dialog. The two sessions the failed takes left are no longer in the list. The writer did not view the video and did not compare the six remaining rows with the rows of the rescout beyond their ages (14h, 11d, 11d, 11d, 12d, 12d, matching ranks 3 to 8 of the rescout).

**What it proves.** The coder's diagnosis, a native confirm dismissed by the browser driver, is **confirmed live** by this run (as relayed; the writer saw two sessions gone and the count 8 to 6, not the dialogs). "What the cluster keeps" loses the two sessions. What stays is the assistant's possible memory of the two questions (declared effect). Next, as relayed: an `openclaw` rescout (rows 6), then the take on a new owner go.

### openclaw: the third take passed (2026-11-17, WP-290; no GIF yet)

**Go:** "Take openclaw" at **06:42:25 CET on 2026-11-17** in demo333's session (read by `zuno-demo-reorg` in its log, as relayed).

**Rescout before** (newest `openclaw-*-scout`, `openclaw-20261117-064056-scout`, started 05:41:18 UTC = 06:41 CET, walkthrough `ab1b780c...`; the writer read `scout.json`): `done`, 8 steps; the `sessions` step reads rows 6, distinct 6, told apart by link; `owned` 6; the session menu lists seven entries including Delete...; nothing typed, no session opened, native dialogs 0; no write seen by the guard; private addresses 0.

**The take** (`openclaw-20261117-064651`, persona `consultant-02`, started 05:46:53 UTC = 06:46 CET; the writer read `markers.json` and opened `session.png` and `q-done.png`):

| Item | Value |
|---|---|
| Result | `pass`, 6 markers (`login`, `ui`, `session`, `q-sent`, `q-done`, `end`) in 66.1 s |
| Created and cleaned | One session created; `cleaned` **true**; owned **6 before and 6 after**; private addresses 0 |
| Writes | none seen by the guard (it does not see the Control UI's WebSocket, so this proves nothing) |
| Commit | Not recorded in `markers.json`. Demo333 says `devel` `de906ef3`, as relayed. Its walkthrough hash is `ab1b780c...` in the rescout before |
| Delete (as relayed) | The native confirm was accepted (66 characters, the text not logged) and the session deleted through the Control UI's menu |

- **Frames the writer saw.** `session.png`: the Control UI with a new session "now" at the top of the sidebar under its default technical name, six other rows, an empty chat ready for a question. `q-done.png`: the answer to the question, a list of seven wiki pages with their addresses; the sidebar shows the take's session "now" under a title the assistant derived from the question, and the six other sessions (one with a French title, five with technical `agent:default:` names). `end.png` has the same size as `q-done.png` and was not opened. **No frame can show the delete:** it happens after the last marker.
- **Review by demo333 (as relayed):** 6 PNGs opened; the question is a short French request to search the wiki for onboarding pages. The coordinator opened `q-done.png` too and saw the same, and the writer agrees: no person name, no email, and the answer shows the **real wiki page titles, page ids and addresses** of the company's Confluence, which this file does not copy. The owner accepted this kind of content with "comme guardrails" (as relayed). The assistant is called "Bob" on the frames.
- **No GIF.** `gif.py` refused one caption of 61 characters, and the cut planned only 32 s. The coordinator's `24fa7d9e` (committed 06:50:29 CET, read from git by the writer; `gif.yml` only) uses the question, the answer arriving, then the answer as a still, with the target back to 40 to 60 s; dry-run 6 moments, 42.0 s (as relayed). Demo333 re-cuts. **Not published**; no publication go.
- **What the cluster keeps:** the assistant's possible memory of this third question (declared); one more answer of `consultant-02`'s budget spent (as relayed).

### openclaw: cut v2 (candidate, not published)

The first cut was the coordinator's `24fa7d9e` (42.0 s, 3.7 MB, 6 moments). Demo333's scan of 14 frames plus the 6 PNGs found nothing private (no token, key, node or address, person name or email; the Control UI password field is in no frame; the tool line shows the tool's name and its one argument "onboarding"), and found two captions saying more than the frames: nothing on screen says namespace, rights, or the absence of a key (as relayed). The coordinator's `9df87235` (committed 06:54:25 CET, read from git by the writer; `gif.yml` only) changes them to "0:00  My own assistant, with its own sessions" and "0:45  It calls the platform's Confluence search tool". Demo333 re-cut the same take and checked both captions on their frames: true (as relayed).

| Item | Value (read from `openclaw.gif.json`, written 06:56 CET) |
|---|---|
| GIF | 3 916 978 bytes (3.7 MB), 42.0 s planned and real, 960x656, 6 moments, 420 frames; SHA-256 `71dc64eca811...` |
| Review by the writer | A contact sheet of 13 frames (every 35th, plus the last), not a full scan |

**What the sheet shows.** The Keycloak sign-in ("Sign in with the company account at the door"); the Control UI with an empty chat and the sidebar; the question typed and sent; the tool line and the answer arriving; the answer, a list of seven wiki pages with their addresses, held for the rest of the GIF. No token, no key, no node name, no person name or email on any of the 13 frames. The answer frames show the real wiki page titles, ids and addresses of the company's Confluence, as the owner accepted ("comme guardrails", as relayed); this file copies none. The sidebar shows the assistant's own session titles and technical session names.

**One flag the writer raises.** The **last caption**, held on the last four sampled frames, reads "No key, no internet: the platform decides models and tools". Nothing on those frames shows a key, the absence of internet, or the platform deciding anything: they show the answer and the sidebar. It is the same kind of caption that demo333 found overstating on the first cut; the coordinator's fix changed two captions and not this one. The writer did not check it against the rows of `openclaw.md`, and it may be the page's own message sentence, but the frames do not carry it. To the coordinator to judge.

**The coordinator's answer (as relayed).** It is the page's close, row 4:15 of `openclaw.md` (its Say column reads "Everyone can have their own AI assistant. It holds no key, it cannot reach the internet, and the platform decides which models and tools it may use."; the writer checked the row, and the caption shortens that sentence), carried with step "4:15" on the last screen, as every published GIF closes: a row that is words, not a screen. The coordinator keeps it and tells the owner in the proposal that the closing caption is the page's sentence and that no frame shows it. The two captions changed were on moments that claimed to show something. The flag and the answer are recorded as they are.

**Also not shown:** the delete of the take's session (it happens after the last marker), so no frame of the GIF shows it.

The coordinator proposes cut v2 for publication; it is sent to the owner. **Not published**; no publication go.

### observability-trace: the coder's framing v3 `51a80b6f` (pushed)

On `devel` as `cb2ebf0d`, committed 07:02:30 CET (the original `51a80b6f` at 06:43:03 CET; both read from git by the writer; as relayed for the rest): the whole-row meaning of "drawn"; both pictures framed from the bottom; the pointer moved off the rows; `zuno.groups` folded with the UI's own arrow, reported in the scout. **The coder states it never saw the arrow's element, so the fold is unproven live.** Walkthrough hash `5032b93b...`. `ONLY=observability-trace` PASS, `test_gif` OK and consistency 0 problems on the coordinator's side. A rescout is asked of demo333 before the trace leaves the six-hour search at about 09:19 CET. No take is asked.

### observability-trace: rescout at `cb2ebf0d`, clean (directory `observability-trace-20261117-070325-scout`)

Started 06:03:37 UTC (07:03 CET); walkthrough `5032b93b...`. The writer read `scout.json` of the top and of `trace/` and opened `trace/scout-tags.png` and `trace/scout-tags-run.png`. Status `done`; `chat` writes: the 404 `blueprint.validate` and `session.join`; `trace` writes none; refused none; private addresses 0. The search found 1 trace (61 spans, 1 `model_call` span). The scout declares the Tempo OAuth authorization of `ai-ops-01` again.

| Check | `tags` picture | `tags-run` picture |
|---|---|---|
| Read from the file | `groups` collapsed true "by" a `[role='button']` control, row height 274 to 35; `caption_in_window` true; `user_sub_in_window` false | all 12 named tags in the window; `proof_in_window` true; `user_sub_in_window` false |
| Seen on the image (the writer) | The span header; two rows above `zuno.agent` (`otel.scope.name`, `span.kind`); agent, classification, client, completion_tokens, estimated cost, **`zuno.groups` folded to a one-line arrow with three dots**, latency, model and model_kind, the last row on the bottom edge but whole; no `zuno.user_sub`, no group names | The tags from `zuno.agent` to `zuno.task`, `zuno.groups` folded, `zuno.persona`, `zuno.run_id` and `zuno.task` (the last row) whole; no `zuno.user_sub`, no group names, no Copy or JSON buttons |

So the fold is **proven live, in a scout** (the coder said it had never seen the arrow's element; the scout's file and the image agree that the UI's own control folded the list). The writer saw the request id and the run id values on `tags-run` and copied none. As relayed, demo333 opened both images too and saw the same. demo333 asks the owner for the named take go (chat, then trace); the coordinator integrates `7c12f760` with its next commit.

### Take: observability-trace (passed; GIF candidate, not published)

**Go:** "Take observability-trace" at **07:08:22 CET on 2026-11-17** in demo333's session (read by `zuno-demo-reorg` in its log, as relayed), before the take. The take directory is `observability-trace-20261117-071006`. Demo333 says it ran at `cb2ebf0d`; the files record no commit, but the walkthrough hash of the rescout before it was `5032b93b...`. The writer read both `markers.json`, `takes.json` and `observability-trace.gif.json`, opened five images and a contact sheet of the GIF (below).

| Item | `chat` take | `trace` take |
|---|---|---|
| Persona | `consultant-02` | `ai-ops-01` |
| Started | 06:10:08 UTC (07:10:08 CET) | 06:12:06 UTC (07:12:06 CET) |
| Result | `pass`, 5 markers (`login`, `hub`, `q-sent`, `q-done`, `end`) in 83.9 s | `pass`, 6 markers (`login`, `search`, `trace`, `tags`, `tags-run`, `end`) in 68.9 s |
| Created and cleaned | One session created, `cleaned` true; owned 21 before and 21 after | none; owned 0 and 0 |
| Writes | 18 sent, none refused, none tolerated (`blueprint.validate` x3, `session.join` x2, `edit_lock.statuses` x2, `user.session.create`, `session.typing` x6, `session.leave`, `user.session.submit`, `session.heartbeat` and one `DELETE` of the session) | none |
| Private addresses | count 0 | count 0 |
| Notes (the file) | | `traces_listed` 1; `run_id_is_the_chat_session` **true**; `groups_collapsed` true; `tags_in_window` 7; `tags_run_in_window` 12 |

**The GIF** (`observability-trace.gif.json`, written 07:14 CET): 1 526 414 bytes (1.5 MB), 42.0 s planned and real, 960x656, 7 moments, 420 frames; SHA-256 `092005bb6030...`. As relayed by demo333, at `cb2ebf0d`.

**Review.** The directory holds **11** PNGs (5 in `chat`, 6 in `trace`; the writer and the coordinator counted them). Demo333 says "N=11" and lists 10: it left `chat/end.png` as equal to `q-done.png`. **The two are not byte-equal**: `chat/end.png` is 467 483 bytes and `q-done.png` 467 163 (the writer opened `chat/end.png`: it shows the same state as the answered chat, the session "Just now", 22 sessions). The writer opened 3 PNGs (`chat/end.png`, `chat/hub.png`, `trace/tags.png`) and a contact sheet of 13 frames of the GIF; the coordinator opened `chat/q-done.png` and `trace/tags-run.png`. Demo333 samples 13 frames and says nothing private (as relayed).

- **`trace/tags.png`:** the span `model_call` of service `ai-gateway`, its tags from `otel.scope.name` to `zuno.model_kind`, `zuno.groups` folded to one line, no `zuno.user_sub`, no group names, no hover buttons.
- **The GIF's captions and what the frames show** (contact sheet): "Sign in with the company account" over the Keycloak sign-in; "0:45  A consultant asks our technical agent" over the Collaboration Hub with the question typed, sent and answered; "1:45  The operator finds that turn by who asked" over the Tempo search with the tags filter and one trace; "One trace: UnifAI's spans and the gateway's model calls" over the span list; "3:00  Which app, which agent, which model, what cost" over the span's tags; "Who asked, and the run: the consultant's own session" over the tags with `zuno.persona` and `zuno.run_id`; "Every call leaves a count and a trace" on the last still.
- **Two captions the frames do not carry entirely.** (1) "the consultant's own session": the frames show the persona and a run id; that the run id **equals the chat session's id** is in the take's notes (`run_id_is_the_chat_session`) and log, not in a frame, because the chat frames do not show the session id (the coordinator's note; the writer agrees). (2) "Every call leaves a count and a trace" is the page's close (as for the other published GIFs: words, not a screen); the frames show a trace, no count.
- **Privacy flags.** The Collaboration Hub frames show the persona's display name in the header and earlier sessions of that account listed by the first words of their prompts, with dates (the same finding as for `unifai-agents`). The writer copies neither. The trace frames show request and run id values and the trace id; none is copied. As relayed: no `zuno.user_sub`, no group names, no address, host, node, token or email.

Sent to the owner; the coordinator proposes it for publication. **Not published**; no publication go. **What the cluster keeps (as relayed):** the trace in Tempo, one Tekos answer of `consultant-02`'s budget, and the Tempo OAuth authorization of `ai-ops-01` (already listed).

### The last two WP-290 decisions (2026-11-17, 11:14:24 CET, as relayed)

The owner answered one dialog in `zuno-demo-reorg`'s session at **11:14:24 CET on 2026-11-17** (read in its log by the coordinator; the writer has not seen the owner's words). `blender-3d`: **"Images fixes de la page"**, a GIF made of the screenshots already in the demo's page, with captions (not chosen: a screen capture by the owner, no GIF). `world-model`: **"Enregistrement de secours"**, a GIF cut from the existing recorded fallback, if its content passes the privacy review (not chosen: a live take the next time the GPU node is up, no GIF). Both are offline work, assigned to the assist: no cluster action, no GPU node. Publication of each still needs the owner's named go. The WP-290 decisions table is updated. The publication gos for `openclaw` and `observability-trace` are still open (as relayed).

### blender-3d and world-model: the assist's inventory (2026-11-17, as relayed; nothing committed, nothing live)

**`blender-3d`.** The decision "Images fixes de la page" had no source: `docs/demo/blender-3d.md` embeds no image and never did (the writer found 0 image links in the page and no Blender image in `docs/assets/img`; `git log -S` on the page finds no image link added), and the WP-244 run was headless. The coordinator asked the owner again: the answer **"Vos captures du 07/11"** at **11:33:36 CET on 2026-11-17** (the coordinator's log, as relayed): the team may open the owner's own screen captures dated 2026-11-07 in `~/Pictures`, only those, read only; each is reviewed, and images showing anything but Blender are cropped or dropped. Not chosen: the owner names files, no GIF, a capture later. The assist had not opened them before the answer (as relayed).

**`world-model`.** The recorded fallback is a workstation-only file, not in git: an H.264 mp4, 1280x720, 23.9 s, 7 060 580 bytes, showing only the generated world with a burnt-in band that says it was recorded on 2026-11-08, real output of the demo's GPU runtime, not live; no interface, URL or persona. The assist's privacy review: PASS, 1039 frames by machine (band brightness, 2 scene cuts) and about 150 by eye; no text, person or identifier. The writer did not see the file or the review. Three facts the coordinator will tell the owner with the GIF: frame 0 is black; the red sky of the prompt edit lasts 5 frames (about 0.09 s) while the page row 2:15 says it is still red-pink about 1.2 s later (the page says more than the recording shows; the page is not changed); the textures smear from about 9 s and the village is gone by 16 s, so the cut plays 0 to 8 s. Proposed cut: 640 px, 6 fps, 41.0 s, 4.82 MB.

**A `gif.py` change agreed with the assist (as relayed).** A take kind "assembled" (made by hand from existing media; `created` empty, `cleaned` null, no owned count; a required `source` list of path and SHA-256, verified and copied into `gif.json`), a `video` file name in `markers.json`, and a caption limit scaled to the width (unchanged at 960 px). The assist will tell the coordinator the line that ADR-0618 clause 9 needs; that text is the coordinator's. Nothing of this is committed.

### Published at 11:38 CET on 2026-11-17: openclaw and observability-trace

On the owner's go "go de publication d'openclaw et d'observability-trace" at **11:37:38 CET** (the coordinator's log, as relayed), before both commits at **11:38:58 CET** (read from git by the writer). The writer compared each file in the commit with the GIF the take directory holds now.

| Demo | Commit | Take | File | SHA-256 |
|---|---|---|---|---|
| `openclaw` | `63755c1d` | `openclaw-20261117-064651`, cut v2 (`9df87235`) | 3 916 978 bytes, 42.0 s | `71dc64eca811...`, equal |
| `observability-trace` | `6b57720c` | `observability-trace-20261117-071006` | 1 526 414 bytes, 42.0 s | `092005bb6030...`, equal |

The tree of `6b57720c` holds **27** GIF files in `docs/assets/img/demo`. Each commit adds the GIF and its page caption. The `openclaw` caption says the page titles and links are real pages of the company's Confluence, and that the session the recording created was deleted afterwards. The `observability-trace` caption says the list at the left of the chat shows earlier test sessions of the team. Marks: on `observability-trace.md`, row 3:00 said "Not yet checked on a Tekos span"; the take ran that row (all 12 tags on a Tekos span, `zuno.run_id` equal to the session id), so the writer lifted that sentence on the page. Rows 5:00 (Grafana) and the rest of the 15-minute version stay "not rehearsed": no take ran them. `openclaw.md` has no mark on the rows the take ran.

**WP-289 has 18 of 18.** Before it can be Done (the coordinator's decision, not the writer's), per its Acceptance: each demo has a published GIF and a stated review (met: every section above); no GIF without the owner's named go (met); `consistency.py` and `check_docs.py` pass (met at this commit); each demo has "a guard summary that lists what remains on the server": that is the sprint evidence's "What the cluster keeps" and the sections above, and the writer has not checked it demo by demo. Open and **outside the brief**: the deferred entries a to q; the open items for the owner (Playwright pin on `main`, the AAP user `consultant-03`); the Tempo and Grafana authorizations that stay on the cluster; the Grafana step of `observability-trace` row 5:00, not rehearsed; the `dify` and `guardrails` edited-date effect, declared.

**WP-290 has 3 of 6** (`genai-playground`, `maas-portal-api-keys`, `openclaw`). Left: `a2a-delegation-approval` (a take, held), and `world-model` and `blender-3d` (assembled GIFs, offline, assist).

### Guard summaries of the 18 demos of WP-289 (the writer's check, 2026-11-17)

The coordinator asked, before deciding on WP-289: for each demo, where the evidence states what the take left on the server (or "nothing", with its basis), and a flag where that statement is missing or only relayed. The writer read the evidence files; it did not re-open any frame or take. "Sprint" is `wp-289-gif-sprint-2026-11-16.md`, "afternoon" this file. **Stated** means a sentence of the evidence says what stays. **Implied** means no such sentence, only a basis (the commands or the counts). Common to all: the gateway's model-call metrics and the traces of a demo's own calls cannot be deleted by a take (ADR-0618 clause 12; sprint, "What stays on the server").

| # | Demo | What the take left | Where | Basis | Flag |
|---|---|---|---|---|---|
| 1 | `gitops-day0-3` | Nothing: two reads | Sprint, its section | Stated; `created` empty | none |
| 2 | `image-signing-admission` | Nothing: four reads | Sprint, its section | Stated; `created` empty | none |
| 3 | `external-models` | Nothing: reads. The published re-take has four read commands | Sprint, re-take section (the statement "three reads" is in the section of the replaced first take) | Stated for the first take; the re-take lists "four reads, all `rc` 0" but has no sentence of its own | **Implied** for the published take |
| 4 | `ai-gateway-sovereignty` | Two real model calls of the probe (Arkos at C1 raised to C3, and the Tekos control) | Sprint, re-take section | Stated | none |
| 5 | `okf-signed-agent-release` | Nothing: two commands, `git show` and `oc logs`, `rc` 0 | Sprint, its section | Commands and `created` empty, `cleaned` null | **Implied**: no sentence |
| 6 | `service-mesh-kiali` | Nothing: three commands, `oc get`, `rc` 0 | Sprint, re-take section | Commands and `created` empty, `cleaned` null | **Implied**: no sentence |
| 7 | `lightspeed` | The conversation was deleted; the model calls behind the answers stay in the platform's records | Sprint, its section | Stated | none |
| 8 | `model-catalog-registry` | Nothing: read-only | Sprint, its section | `created` empty, `cleaned` null, owned 0 and 0 | **Implied**: no sentence |
| 9 | `mcp-tools-by-group` | The chats were deleted; the Confluence search of `consultant-02` and the failed Drive call of `sale-01` stay in the tool records | Afternoon, re-take section | Stated | none |
| 10 | `ai-gateway-routing` | `chat`: one chat created and deleted; `dashboard`: read-only | Sprint, its section | `chat` owned 1 and 1; no sentence on the model call or on the Grafana sign-in | **Implied**; the Grafana authorizations are in "What the cluster keeps" |
| 11 | `evaluation-trustyai-evalhub` | Nothing from the take: read-only | Sprint, its section | Owned 0 and 0 | **Implied**; the Grafana authorizations are in "What the cluster keeps" |
| 12 | `aap-audited-operations` | Nothing: a take under a default-deny guard | Afternoon, its section | `created` empty, owned 0 and 0 | **Implied**; the AAP user `consultant-03` is an open item ("What the cluster keeps": whether AAP created it is not confirmed) |
| 13 | `quotas` | Nothing from the take: stills of Grafana panels | Afternoon, its section | `created` empty, owned 0 and 0; no take-time write guard (it watches writes and fails afterwards) | **Implied**; the Grafana authorizations are in "What the cluster keeps" |
| 14 | `unifai-agents` | One session per persona, created and deleted | Afternoon, its section | Owned 21 and 21 for both takes; no sentence on what stays (traces, the model call) | **Implied**; taken before the write guard (the guard section above) |
| 15 | `lora-pipeline-mlflow-kueue` | Nothing: stills of runs that had finished | Afternoon, its section | `created` empty, owned 0 and 0; "no write watched" is **relayed** | **Implied and partly relayed** |
| 16 | `dify` | The workflow run stays in the run log; the Zuno Agent's edited date moved (declared) | Afternoon (take and publication), sprint ("What the cluster keeps"; the order table: the run log it leaves stays) | Stated; conversation created and deleted, owned 0 and 0; the writes list is **relayed** | The writes list is relayed |
| 17 | `guardrails` | One conversation created and deleted; the Zuno Agent's edited date moved again (declared); the detections the probes and the take left on the dashboard | Afternoon, its section; sprint ("What the cluster keeps", the declared effect) | Stated; the writes list is **relayed**; the probes' part of the count is stated | The writes list is relayed |
| 18 | `observability-trace` | The trace in Tempo; one Tekos answer of `consultant-02`'s budget; the Tempo OAuth authorization of `ai-ops-01`; one session created and deleted | Afternoon, its take section | Stated, but "What the cluster keeps" there is **relayed**; the session count (21 and 21) and the 18 writes are read from the file | The keeps line is relayed |

**Summary.** Stated by a sentence, with a basis the writer read: 1, 2, 4, 7, 9. Stated and partly relayed: 16, 17, 18. Implied only (a basis but no sentence): 3 (for the published re-take), 5, 6, 8, 10, 11, 12, 13, 14, 15. **No demo has neither a basis nor a statement.** Open and recorded elsewhere, not closed here: the Grafana authorizations (rows 10, 11, 13), `consultant-03` (row 12), the declared edited-date effect (rows 16, 17), the deferred entries a to q.

## Limit of every GIF published so far: write guards (assist's survey, as relayed)

In a take, only `aap-audited-operations` and `genai-playground` refuse writes by default. The Grafana, lora and Tempo walkthroughs watch writes and fail after the fact. `open-webui`, `identity-personas`, `mcp-tools-by-group`, `unifai-live-rag`, `kagent`, `lightspeed` and `model-catalog-registry` had no take-time write guard: their own created chats and sessions were deleted and counted, but what else their pages may have sent was not blocked or listed. Decision of the coordinator: one shared default-deny guard in the recorder, the walkthroughs not yet taken first.

### Answer: the shared write guard (devel `15016318`, `86424b77`, head `6df63b54`)

As relayed by the coordinator; the writer checked the code at `6df63b54` (file list and the guard's lines in `record.mjs`), and ran nothing.

- **The mechanism** (`15016318`, in `evaluations/browser/record.mjs`): a walkthrough that declares `allows` is guarded. Every write it does not declare is aborted in the browser, in takes and in scouts. A take **fails** on an undeclared write. `markers.json` and `scout.json` list the writes `sent`, `refused`, `tolerated` and `through`.
- **Converted walkthroughs** (`15016318`, `86424b77`): `dify`, `guardrails`, `unifai-agents`, `a2a-delegation-approval`, `observability-trace`, `maas-portal-api-keys` and `openclaw`. The writer's grep for `allows` at `6df63b54` finds these seven and the shared `_dify.mjs`, and no other walkthrough. The `openclaw` take is un-refused, per the owner's decision of 21:01 CET (as relayed).
- **Of the published GIFs, only `dify` was taken under the guard**: its last take, `dify-20261116-215039` (section above). The `unifai-agents` take (directory `unifai-agents-20261116-194517`) predates the guard commits, which are dated 22:56 CET.

**The limit that remains, exactly.** Not converted yet: the walkthroughs of the GIFs already published. Their published takes predate any take-time guard. Only `aap-audited-operations` and `genai-playground` have their own default-deny in a take. `ai-gateway-routing`, `evaluation-trustyai-evalhub`, `quotas` (Grafana), `lora-pipeline-mlflow-kueue` and the Tempo part watch writes and fail after the fact. `open-webui`, `identity-personas`, `mcp-tools-by-group`, `unifai-live-rag`, `kagent`, `lightspeed` and `model-catalog-registry` have no take-time write guard. The coordinator confirmed this reading after the assist's survey (as relayed); the writer did not read those walkthroughs.

A lora rescout at `889fe3c9` passed 8 of 8 (as relayed); its take is with the owner.

## Take: lora-pipeline-mlflow-kueue (published, stills only)

| Item | Value |
|---|---|
| Take | `lora-pipeline-mlflow-kueue-20261116-211512`: `ai-dev-01`, `pass`, 5 markers in 37.9 s, cut at `889fe3c9` (as relayed) |
| Owner's go | Given in demo333's session, told "writes watched, not blocked" (as relayed) |
| Created and cleaned | `created` empty, `cleaned` null; owned 0 before and 0 after; `private_addresses` count 0; no write watched (as relayed) |
| GIF | 1 590 868 bytes (read from the take), SHA-256 `c46fbd50492c...`, 44.0 s as relayed, 5 moments |

**Review.** demo333 opened the 5 marker images (as relayed). The writer opened 2 (`pipeline.png`, `trainjob.png`) and no frames. `pipeline.png`: the pipeline version `v0-4-0-tekos`, a version dropdown, tabs Graph, Summary and Pipeline spec, a graph of four nodes `component` to `component-4`, and the step names in the description line; the account `ai-dev-01` in the header; no node name, no address. `trainjob.png`: the **Jobs** page of Zuno MLOps with one row, `lora-comage-4c28m`, type TrainJob, nodes 0, cluster queue "-", created "2 months ago"; no status column at 1280 px.

**Not yet a publication candidate.** Two captions overstate; the assist fixes `gif.yml` and the GIF is re-cut from the same take (as relayed). Page: row 1:45 now matches the Jobs frame: the job, its type and its age. Its `Complete` state and its date 2026-09-08 come from `oc get trainjob`, not from the page. Sent to the owner.

## Published at 21:31 CET: unifai-agents and lora-pipeline-mlflow-kueue

On the owner's go "go de publication pour unifai-agents et lora-pipeline-mlflow-kueue" (coordinator's log 21:30:55 CET; commits at 21:31:13). The writer compared each file in the commit with the GIF the take directory holds now.

| Demo | Commit | Take | File | SHA-256 |
|---|---|---|---|---|
| `unifai-agents` | `84f41734` | `unifai-agents-20261116-194517`, re-cut at `2b9f3dfb` | 5 639 585 bytes, 45.0 s as relayed | `5121d0a6f8b2...`, equal |
| `lora-pipeline-mlflow-kueue` | `a4285b25` | `lora-pipeline-mlflow-kueue-20261116-211512`, stills-only cut `e839d037` | 323 266 bytes, 42.0 s as relayed | `4cf2301253f2...`, equal |

The sizes and moments quoted in the two take sections above are those of the first cuts; the published files are the re-cuts. For `lora`: two re-cuts, the captions corrected by the assist (`aa80972f`), then stills only (`1d4a1118`), because the motion spans were mostly loading pages. The writer did not open the frames of the final cuts. The catalogue has 22 GIF files of 30 demos. No "(untested ...)" mark needed lifting on rows these takes ran (`unifai-agents` has none; the marks left on the `lora` page are on the MLflow tab, which the GIF does not show).

## Owner's decision on Dify: "one take to know" (answered 21:30:11 CET, as relayed)

One `dify` take under the default-deny guard (the coder's `f974ada4`, in test). Its log lists every write sent and every write refused. The aim is to learn what moves the Zuno Agent's edited date. Cost: one Agent turn, and the date may move once more. The take needs the owner's go in demo333. The coder read upstream Dify's source: by that code a debug turn writes a conversation and a message, not the app (not our exact build). The cause is **not settled**.

## Take: dify "to know" (measured, published at 23:19 CET)

Owner's go in demo333 ("Take dify to know"), as relayed. All times UTC.

| Item | Value |
|---|---|
| Take | `dify-20261116-215039`: `consultant-02`, `pass`, 9 markers in 61.7 s, started 20:50 |
| Created and cleaned | One conversation created and deleted; owned 0 before and 0 after; `private_addresses` count 0 |
| GIF | 2 379 935 bytes (read from the take), SHA-256 `27114b527b11...`, 49.0 s as relayed |
| Before | Scout at 20:47: Zuno Agent "Edited at 11/16/2026 20:02"; the scout refused nothing and sent no write when it opened the Agent page (as relayed) |
| Writes sent to Dify, in order (as relayed) | `POST` refresh-token (401), `POST` login (200), `POST` `apps/<id>/chat-messages` (200), `POST` `apps/<id>/workflows/draft/run` (200), then the conversation delete |
| Refused in the browser | `POST apps/<id>/workflows/draft`, once |
| After | Scout at 20:52: "Edited at 11/16/2026 20:51"; the other three cards unchanged (as relayed) |
| Workflow run | Succeeded and **stays** in the run log |

The writer opened `studio.png` (the Studio frame at the take's start): the Zuno Agent card reads "Edited at 11/16/2026 20:02", the other three 11/06 17:27, 11/06 16:30 and 11/05 12:18. The writer opened no other image of this take and no frame; demo333's review count is not relayed.

**Conclusion, as measured and not proven server-side:** no configuration write left the browser for the Agent. Dify's server moves the application's edited date when the Agent answers in Debug & Preview, or when its conversation is deleted; the two were not separated.

**Owner's decision**, answered just before 21:55:25 CET in `zuno-demo-reorg`'s session (as relayed): **"Yes, declared effect"** for `dify` and `guardrails`. The moved date is declared as an effect of those takes.

**Published.** See the next section.

## Published at 23:19 CET: dify

On the owner's "go de publication de dify" (coordinator's log 23:18:57 CET; commit `00a57123` at 23:19:46, as relayed). The writer compared the file in the commit with the GIF the take directory holds now.

| Demo | Commit | Take | File | SHA-256 |
|---|---|---|---|---|
| `dify` | `00a57123` | `dify-20261116-215039` | 2 379 935 bytes, 49.0 s as relayed | `27114b527b11...`, equal |

The commit also adds the GIF to `dify.md`; the page declares the edited-date effect and the run log that stays. The caption says the page titles in the answers are real pages of the company's Confluence, as the owner allowed. The writer opened only `studio.png` of this take, not the frames of the GIF. No "(untested ...)" mark was left on `dify.md`, so none was lifted. The catalogue has 23 GIF files of 30 demos. WP-289 has 16 of 18; `guardrails` and `observability-trace` remain.

