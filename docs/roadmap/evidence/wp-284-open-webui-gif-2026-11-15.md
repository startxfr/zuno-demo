# WP-284: the Open WebUI demo as a GIF (2026-11-15)

One recorded take of the 5-minute version of the Open WebUI demo, cut into a GIF and published with the owner's named
"go open-webui". It is the pilot of [ADR-0617](../../adr/0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md).
The take and the review were done by session `zuno-demo-reorg-demo333` on demo333; the cut and the page are in the
repository.

## Result

| Item | Value |
|---|---|
| Take | `open-webui-20261115-202921`, as sale-01, viewport 1280x800, 23.4 s of recording |
| Published file | `docs/assets/img/demo/open-webui.gif`, 1 314 717 bytes (1.3 MB), 960x656 (a 960x600 picture and a 56 px caption band), 10 images per second, 42.9 s, 7 moments |
| Cut | `ansible/demos/open-webui/gif.yml` at `a0c6071b`, assembled offline by `make demo gif open-webui` |
| Publication | commit `dd9178fc`, after the owner's "go open-webui" given in the demo333 session; the published file has the same SHA-256 as the one in the recordings cache |
| Chat left behind | none: `chat_deleted` is true in `markers.json`, and sale-01's chat list was identical before and after |

The size is under the 8 MB limit and the duration inside 40 to 60 s (ADR-0617 clauses 4 and 5).

### The take

`markers.json` of the take, with the `t` values of the file (seconds since the start of the recording; the log of the
run prints times 0.1 to 0.2 s later):

| Marker | t (s) |
|---|---|
| `login` | 1.0 |
| `home` | 8.28 |
| `q1-sent` | 10.36 |
| `q1-done` | 13.32 |
| `code-picked` | 14.65 |
| `q2-done` | 20.73 |
| `tools` | 22.05 |
| `end` | 23.43 |

`motion_from` is `q1-sent`: the sign-in and the typing of the first question are not in motion. The two motion
moments run slowed down (the first answer at x0.5, the Zuno Code answer at x0.6), because `fit` slows a fast answer
instead of freezing it.

### The moments of the GIF

| Moment | Cut | Seconds | Caption |
|---|---|---|---|
| 1 | still `login` | 3.0 | Sign in with the company account |
| 2 | still `home` (step 0:00) | 4.0 | 0:00  Zuno picks the model |
| 3 | `q1-sent` to `q1-done` (step 0:45) | 8.92 | 0:45  An answer from a model on our own GPUs |
| 4 | still `code-picked` (step 1:45) | 3.0 | 1:45  Switch the model to Zuno Code |
| 5 | `code-picked` to `q2-done` | 14.0 | Zuno Code: code questions go to Codestral |
| 6 | still `tools` (step 3:00) | 5.0 | 3:00  My tools: the governed connection Zuno tools |
| 7 | still `end` (step 4:15) | 5.0 | Identity, models, tools and budget stay governed |

## How it went

| Step | Commit | Outcome |
|---|---|---|
| First take | `e8db6ef7` | FAILED after `login`: the walkthrough took a collapsed sidebar rail for an open sidebar. No chat was created. |
| Read-only peek, then scout | `d7c34505` | Clean: 4 steps, `zuno_code_listed` true. The scout sent no prompt and created no chat. |
| Full take | `d7c34505` | PASS in 23.4 s, 8 markers, chat deleted. |
| First cut | `d7c34505` | 48.0 s and 0.9 MB, with two defects: the caption covered the input and the switch, and about 13 s of the GIF was a frozen frame. |
| Re-cut, offline | `a0c6071b` | The caption moved to a band under the picture and `fit` stopped padding with a frozen frame: 42.9 s, 1.3 MB, 960x656, 7 moments. |

The first cut was sent to the owner; the two defects were found in it and it was replaced, as announced, by the re-cut. That first file no longer exists.

## Privacy review

Done by `zuno-demo-reorg-demo333` (the Claude session, by looking at images: no OCR and no automatic scan) before the
owner's go, against clause 8 of the ADR.

**What was looked at.** Only the assembled GIF, as contact sheets of sampled frames: for the first cut 48 frames, one per
second, over its 48 s; for the final cut 29 frames, one per 1.5 s of its 42.9 s, covering every segment. That is 29 of
the 429 frames of the published GIF, not every frame. The commit message of `dd9178fc` says "frame by frame": the
sampling above is what was done. **The 8 marker images were not opened one by one for this review** (they show the same
screens as the stills of the GIF, which was not verified file by file), so clause 8's "every marker image" was not met to
the letter. The images of the failed first take and of the scout were opened too; they are not published.

**Completed after the publication.** The coordinator session (`zuno-demo-reorg`) opened the 8 marker images of the take
one by one on 2026-11-15, after `dd9178fc`, with the same list: the empty Keycloak form of realm "ZUNO DEMO"; the home
page with the INFO banner and three suggestion cards; the two scripted prompts and their answers (the first answer names
Drive, Gmail and diagrams; the code holds only `example@example.com`); the chat title "Assistant Offer" of the take's own
chat; the tools panel with "Zuno tools" on. Nothing on the list was found. The motion frames between the markers remain
covered by the sample only.

**What was seen on the sampled frames,** item by item:

| Item | Result |
|---|---|
| Token or API key | none seen |
| Session cookie | none seen (no developer tools and no address bar in the frames) |
| Keycloak form with a typed password | none: the form is empty in the login still |
| Real person's name or email | none; only `example@example.com` inside the generated code |
| Chat content beyond the scripted prompts and answers | none: the two scripted prompts and their answers only |
| Earlier chat title | none: the sidebar is collapsed, and the only titles seen are the take's own chat ("New Chat", then "Assistant Offer") |
| Data of another tenant | none seen |

**Not checked:** pixel-level small text (the blue INFO banner at the top, "Zuno chooses the model for each answer...",
stays on screen the whole GIF in tiny text), and the avatar at the bottom left was not zoomed (it is a generic
placeholder). The chat list of sale-01 was compared by identifier and title by hand, outside the recorder: one earlier
chat existed, was never shown and was not touched, and the list was identical before and after. The chat of the take
was deleted through the API (`chat_deleted` true).

**The owner's go.** The owner wrote "go open-webui" in the demo333 session on 2026-11-15, after that session sent the
re-cut GIF (file time 20:40:38 +0100). The exact minute of the go was not recorded: the file was copied into the
repository at 20:50:01 and `dd9178fc` is dated 20:50:28, so the go came between about 20:41 and 20:50. The GIF sent to
the owner (the second send) and the published file have the same SHA-256, `1311ca10ee10...`. The first GIF sent (48.0 s,
0.9 MB) was overwritten by the re-cut and no longer exists; the owner was told it was replaced.

## A finding about the page

The first wording of the page said the tools menu lists the tool names. On Open WebUI 0.12.5 the button under the
prompt opens an **Integrations** menu with one row, **Tools 1**, then a panel with a single entry, **Zuno tools**,
switched on. The tool names are not on that screen. By the owner's decision the rows 3:00 and 5:00 of
[the page](../../demo/scenarios/experiences/open-webui.md) now say so, and the presenter names the tools aloud; the GIF
shows the connection, not the names.

## Limits

- One take of one demo. Nothing is proven for the other demos or for a second take.
- The walkthrough's selectors are tied to Open WebUI 0.12.5 and to its screen of 2026-11-15; a new version of Open
  WebUI can break them. The scout mode checks them without spending budget.
- Motion starts at `q1-sent`: the typing of the first question is not in the GIF.
- The `record` guards (a passed `check` of the day, the refusal during a freeze) were exercised offline only, plus the
  real `check` of that day. No freeze was set on demo333 to see the refusal.
- The privacy review before the go was a sample of the GIF's frames (29 of 429); the 8 marker images were opened one by
  one only after the publication. The motion frames are covered by the sample only.
- Not measured: sale-01's remaining budget after the take, and which provider served each answer (Grafana was not looked at; the take used the local gpt-oss and Zuno routing).
