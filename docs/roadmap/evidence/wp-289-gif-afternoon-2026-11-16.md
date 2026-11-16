# GIF afternoon of 2026-11-16: takes after the owner's order of 13:2x CET

This file continues the [sprint evidence](wp-289-gif-sprint-2026-11-16.md) for the takes of the afternoon: those of the demos
the owner's order of 13:2x CET sent to the team (see "Owner's order of 13:2x CET" in the sprint file). Takes are run by session
`zuno-demo-reorg-demo333` with the owner's go in its own session. Every fact below is read from the take directory under
`~/.cache/zuno/demo/recordings/`, or marked "as relayed". The writer (`zuno-demo-reorg-writer`) opens the marker images itself.

Privacy rule for this file: it never copies a page title, a page id, a URL of a company page or a person's name from a frame. It
says what the frame holds ("seven real Confluence onboarding pages, role titles").

## Summary

| Demo | Take directory | GIF bytes | Seconds | Moments | Published in | Reviews |
|---|---|---|---|---|---|---|
| `mcp-tools-by-group` (re-take, row 1:30 in full) | `mcp-tools-by-group-20261116-133009` | 1 996 199 | 53.0 | 7 | recorded, awaiting the owner's go, replaces `c1230da7` | recording session: N = 54, as relayed; writer: 2 of 18 images opened |

## Per demo

### `mcp-tools-by-group` re-take (browser, two personas): recorded, awaiting the owner's go

Status: **recorded, awaiting the owner's go.** Sent to the owner as the replacement of the published GIF (`c1230da7`), which stays
in place until then (as relayed).

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

**Point for the owner's review of the GIF.** The table is real company content, which the owner allowed (order of 13:2x CET).
It also shows the Atlassian host and page ids in the URLs; these are not secrets, but the repository is public.

**Pages.** The "You should see" cells of rows 1:30 and 2:45 change at publication (a separate commit, not in this file's commit).

**What stays on the server.** The chats were deleted. The Confluence search of `consultant-02` and the failed Drive call of `sale-01`
stay in the platform's tool-call records (ADR-0618 clause 12).
