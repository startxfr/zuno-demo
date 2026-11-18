# WP-290: Decide and record the six delicate demos

- **State:** Done (2026-11-17: 6 of 6 demos published; the limits and declared effects are written below)
- **ADRs:** [ADR-0618](../../adr/0618-give-every-catalogue-scenario-a-gif-with-real-terminal-sessions-checked-as-text-first.md)
- **Depends on:** [WP-289](wp-289-record-the-repeats-of-the-proven-patterns.md)
- **Related:** [ADR-0617](../../adr/0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md), [WP-284](wp-284-record-the-open-webui-demo-and-publish-it-as-a-gif.md)
- **Target:** v0.16
- **Estimated files touched:** ~12: the walkthroughs or still sets the owner chooses, and the decisions

> Why: ADR-0618 clause 2. Each of these six demos changes the cluster, shows a secret, or needs a desktop application. The owner decides them one by one, last. The options below are the coder's design note of 2026-11-15; the owner's choice is recorded here when it is made.

## Goal

For each of the six demos, the owner's decision is recorded and carried out, or the demo is left without a GIF by that decision.

## Steps

One decision per demo, each with the owner:

- **`blender-3d`** (desktop Blender on the presenter's laptop, not recordable by the browser chain): a screen capture made by the owner and cut by `gif.py` from a hand-made `markers.json`; or stills from the page's screenshots; or no GIF.
- **`world-model`** (the GPU node exists only with the owner's double approval, and the bundled browser may not decode the video): the GIF cut from the existing recorded fallback if its content passes the review; or a live take the next time the node is up, with a browser that decodes it; or no GIF.
- **`a2a-delegation-approval`** (Approve starts an AAP job that cannot be deleted): a take that clicks Reject only and says in the caption what Approve would do; or Approve with the owner's go for each take, one job left each time; or stills.
- **`maas-portal-api-keys`** (a key shown once): a take that creates the key with the field hidden before the dialog opens, proves the call in the terminal with the key masked and revokes the key by its id, failing if it cannot; or stills of the portal without creating a key; or no GIF.
- **`openclaw`** (a second secret, the Control UI password): a walkthrough that declares the secret and reads it under the rules of the persona password; or stills after a manual sign-in; or no GIF.
- **`genai-playground`** (a token pasted on screen): skip the paste and show the saved connection; or stills only.

## Acceptance

- Each of the six has a recorded owner's decision in this brief, and a GIF or stills carried out, or no GIF by that decision.
- No secret is on a frame, and no GIF is published without the owner's named go.
- `python3 platform/demo/consistency.py` (0 problems) and `python3 platform/docs/check_docs.py` pass.

## Owner's choices of 2026-11-16 (13:17 CET)

Given in `zuno-demo-reorg`'s session by the owner's answers to a question with options, and relayed by it; the writer has not seen the
owner's messages. Four of the six were decided on 2026-11-16 (13:17 CET); the last two on 2026-11-17 (11:14:24 CET, below).

| Demo | Owner's choice | What it means for the take |
|---|---|---|
| `a2a-delegation-approval` | **Approve, one job per take** | The take clicks Approve. Each take leaves one AAP job that cannot be deleted. The owner's go is given for each take, in the session of the recording (`zuno-demo-reorg-demo333`). |
| `maas-portal-api-keys` | **Create, hide, revoke** | The take creates the key with the key field hidden before the dialog opens, proves the call with the key masked, and revokes the key by its id. The take fails if the revoke fails. |
| `openclaw` | **Like `guardrails`** | The Control UI password is a declared second secret, read at run time. It is never in git, in a log or on a frame. |
| `genai-playground` | **Skip the paste** | The take does not paste the token and shows the saved connection. Scout of 2026-11-16 (as relayed): the MCP server `zuno-mcp-gateway` is listed but not connected in a fresh browser. The coordinator decided: no token in the recorder. The GIF covers rows 0:00 and 0:45 and the MCP settings as found; rows 1:45 and 3:00 stay words. |
| `blender-3d` | **Fixed images of the page** (2026-11-17, 11:14:24 CET), then **"Vos captures du 07/11"** (11:33:36 CET) | The first answer had no source: the page `docs/demo/blender-3d.md` embeds no image (the writer counted 0 image links and found no Blender image in `docs/assets/img`), and the WP-244 run was headless. The owner was asked again and answered that the team may open the owner's own screen captures dated 2026-11-07 in the presenter's `~/Pictures`, **only those, read only**; each is reviewed, and images showing anything but Blender are cropped or dropped. Not chosen: the owner names files, no GIF, a capture later. Offline work, assigned to the assist: no cluster action. |
| `world-model` | **Recorded fallback** (2026-11-17, 11:14:24 CET) | A GIF cut from the existing recorded fallback, if its content passes the privacy review. Offline work, assigned to the assist: no cluster action, no GPU node. Not chosen: a live take the next time the GPU node is up, no GIF. |

The choices carry the rule that every GIF still needs the owner's named go before publication, and that no secret is on a frame.
The last two choices were given in `zuno-demo-reorg`'s session by one dialog answered at **11:14:24 CET on 2026-11-17** (read there in its log, as relayed); the answers are "Images fixes de la page" and "Enregistrement de secours". Publication of each still needs the owner's named go. The four other demos are takes to scout and review like the others.

## Closed on 2026-11-17: the limits and declared effects, written

The owner chose **"Clore WP-290 et lever le gel"** (close WP-290 and lift the freeze) in `zuno-demo-reorg`'s session, answered at **12:50:28 CET on 2026-11-17** (11:50:28 UTC in its log, as relayed), after being told: six GIFs published, each on a named go; the close-out note on `devel`; nothing of the acceptance left; the declared effects; the two privacy flags. Not chosen: close but keep the freeze; leave the brief open.

**Declared effects** (they stay on the cluster): AAP job 1457, launched by the Approve of the `a2a-delegation-approval` take; the assistant's possible memory of the `openclaw` questions; the revoked key of `maas-portal-api-keys`, possibly listed as revoked in the portal; the traces and metrics of every take.

**The two privacy flags**, told to the owner before the choice: the cluster's apps domain in the panel crop of `blender-3d`, and the AAP route with job id 1457 in the motion frames of `a2a-delegation-approval`.

**Limits:** the guard sees HTTP only, so an empty `writes` list proves nothing for `openclaw` (a WebSocket); `world-model` and `blender-3d` are assembled from existing media and ran nothing on the cluster; the page row 2:15 of `world-model` says more than the recording shows (the page is not changed); the diagnosis of the `openclaw` delete is confirmed by its result, not by a dialog frame. **Every open item stays open where it is recorded**: the close-out note of the [afternoon evidence](../evidence/wp-289-gif-afternoon-2026-11-16.md).

## Published 2026-11-17: 6 of 6

The six GIFs are on `devel`: `genai-playground` (`1a4ff89b`), `maas-portal-api-keys` (`f17dc35b`), `openclaw` (`63755c1d`), `a2a-delegation-approval` (`5598eb44`), `world-model` (`3421934d`) and `blender-3d` (`f0c57126`), each on a named go of the owner. `world-model` and `blender-3d` are assembled from existing media (ADR-0618, update of 2026-11-17). The guard summaries of the six, read from the takes' files, are in [the afternoon evidence](../evidence/wp-289-gif-afternoon-2026-11-16.md), with the sprint's close-out. **What remained before Done:** nothing in the Acceptance (see the next section).

## Progress (2026-11-16)

`genai-playground` is the first of the six with a GIF: `1a4ff89b` publishes take `genai-playground-20261116-183758` on the owner's go of 20:05:27 CET (coordinator's log), before the commit at 20:06:07. The file is 1 046 464 bytes and equal to the take's GIF (SHA-256 `df603fdf6cf0...`, compared by the writer). The take follows the owner's choice "skip the paste": it shows rows 0:00 and 0:45 and the MCP settings as found (`zuno-mcp-gateway` listed, "0 active", no token). Rows 1:45 and 3:00 stay words; the prompt of row 3:00 is untested in the playground. Facts and review: [afternoon evidence](../evidence/wp-289-gif-afternoon-2026-11-16.md).

**Update 2026-11-17:** `maas-portal-api-keys` and `openclaw` are published (below), then `a2a-delegation-approval`, `world-model` and `blender-3d` on the owner's go of 12:30:26 CET (commits `5598eb44`, `3421934d` and `f0c57126`; 6 of 6). `maas-portal-api-keys` had failed its first scout at `enter` (the guard refused the portal's key-list search; nothing was created). `openclaw` scouted 7 of 7 at `d80f25ef` (as relayed). `a2a-delegation-approval` took on 2026-11-17 (go 12:03:26 CET; the Approve launched AAP job 1457, which stays). `blender-3d` and `world-model` were decided on 2026-11-17 (the table above) and assembled by the assist from existing media.

### Owner's decision on `openclaw`, session cleanup (2026-11-16, answered just before 21:01:38 CET)

Given in `zuno-demo-reorg`'s session by an answer to a question with options, and relayed by it (the time is read from its clock right after the answer). The answer: **"Yes, session deleted"**.

- The take asks one question and deletes its own session through the UI's **Delete…** entry. That click is declared.
- The take fails if the session remains after the delete.
- What the assistant may have memorised stays in its memory. This is declared.

### Two failed takes at `feaf7d32` (2026-11-17, as relayed; the writer read the directories)

Neither is retried. Details are in [the afternoon evidence](../evidence/wp-289-gif-afternoon-2026-11-16.md).

- `maas-portal-api-keys` failed before any key was created: the check did not see the model chosen in the Create dialog, which the frame shows is chosen. A bug in the check. Fixed on `devel` as `723c5e24` (coder's `a8afb3a6`); a rescout comes before the next take. The shown-once dialog is still unseen.
- `openclaw` failed after the question was answered: the take did not recognise its own session, which the assistant had retitled, so it did not delete it. Owned sessions went from 6 to 7. The owner decided "Leave it" (2026-11-17, 04:09:56 CET, as relayed): the session stays in `consultant-02`'s assistant. The answer frame holds real Confluence titles; the owner chose "comme guardrails".

### `maas-portal-api-keys`: published (2026-11-17)

`f17dc35b` publishes take `maas-portal-api-keys-20261117-041246`, cut v2, on the owner's go "go de publication de guardrails et de maas-portal-api-keys." at 05:18:40 CET (the coordinator's log, as relayed), before the commit at 05:19:12 CET (git). The file is 614 271 bytes, 41.1 s, and equal to the take's GIF (SHA-256 `2bd2899a421e...`, compared by the writer). The revoke is in no frame. The take passed as below.

Take `maas-portal-api-keys-20261117-041246`: 8 markers in 38.5 s, one key created and cleaned, owned 0 to 0, private addresses 0 (the writer read `markers.json`). The shown-once dialog was seen for the first time, with the key masked after `sk-oai-`. The recorder drew the calls (401 without the key, 200 with it, one chat completion). The key was revoked and the gateway answered 403 with it (as relayed). Details in [the afternoon evidence](../evidence/wp-289-gif-afternoon-2026-11-16.md).

### `openclaw`: the second take failed at the delete; the owner's decision (2026-11-17, as relayed)

Take `openclaw-20261117-052046` (go 05:17:35 CET): the take found its own session (the row-id fix holds live) and the question was answered, but the session stayed listed after Delete... (owned 7 to 8; the writer read `markers.json`). The coder's diagnosis, about 80% sure and unverified live: the Control UI confirms in a native browser dialog that the driver dismissed. The write guard does not see the Control UI's WebSocket, so an empty `writes` list proves nothing for `openclaw`. Two sessions are now left in `consultant-02`'s assistant. Owner's decision at 05:30:42 CET: **"Suppression seule d'abord"**, a delete-only run by constant ids before any new take; each live run needs its own named go. **Update (2026-11-17, 06:36:37 CET, "Delete both"):** the delete-only run passed: 8 sessions listed, 2 deleted, 6 left, `owned` 6 to 6. The native-confirm diagnosis is confirmed live (as relayed). The next step is an `openclaw` rescout, then the take on a new owner go. Details in [the afternoon evidence](../evidence/wp-289-gif-afternoon-2026-11-16.md).

### `openclaw`: published (2026-11-17)

`63755c1d` publishes take `openclaw-20261117-064651`, cut v2, on the owner's go "go de publication d'openclaw et d'observability-trace" at 11:37:38 CET (the coordinator's log, as relayed), before the commit at 11:38:58 CET (git). The file is 3 916 978 bytes, 42.0 s, equal to the take's GIF (SHA-256 `71dc64eca811...`, compared by the writer). The last caption is the page's close, as the coordinator answered. The take:

Take `openclaw-20261117-064651` (go 06:42:25 CET, as relayed): 6 markers in 66.1 s, one session created and **cleaned** (the native confirm accepted), owned 6 to 6, private addresses 0 (the writer read `markers.json`). The answer frame holds real wiki titles and addresses, accepted in kind by the owner ("comme guardrails"); the docs copy none. `gif.py` refused a 61-character caption; the coordinator's `24fa7d9e` re-plans the cut (42.0 s); demo333 re-cuts. Details in [the afternoon evidence](../evidence/wp-289-gif-afternoon-2026-11-16.md).

### Scouts at `d80f25ef` (as relayed)

- `openclaw`: 7 of 7. The session menu lists Pin session, Mark as unread, Rename…, Fork, Move to group, Archive session and Delete….
- `maas-portal-api-keys`: 6 of 6. The key list was empty. The Create dialog was seen and cancelled. Nothing was created.
- `dify`: 9 of 9. `guardrails`: both paths fine.
- `observability-trace`: the bounded search finds one recent Tekos trace of `consultant-02`, but the click opened Jaeger's Compare page (a selector bug).
- `unifai-agents`: the re-cut was refused once because a caption was too long (64 characters); redone at `2b9f3dfb`.

