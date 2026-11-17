# WP-290: Decide and record the six delicate demos

- **State:** Repo work merged (2026-11-16: 1 of 6 demos published, `genai-playground`; the other five wait for scouts, the owner's choices and go)
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
owner's messages. Four of the six are decided; two are not asked yet.

| Demo | Owner's choice | What it means for the take |
|---|---|---|
| `a2a-delegation-approval` | **Approve, one job per take** | The take clicks Approve. Each take leaves one AAP job that cannot be deleted. The owner's go is given for each take, in the session of the recording (`zuno-demo-reorg-demo333`). |
| `maas-portal-api-keys` | **Create, hide, revoke** | The take creates the key with the key field hidden before the dialog opens, proves the call with the key masked, and revokes the key by its id. The take fails if the revoke fails. |
| `openclaw` | **Like `guardrails`** | The Control UI password is a declared second secret, read at run time. It is never in git, in a log or on a frame. |
| `genai-playground` | **Skip the paste** | The take does not paste the token and shows the saved connection. Scout of 2026-11-16 (as relayed): the MCP server `zuno-mcp-gateway` is listed but not connected in a fresh browser. The coordinator decided: no token in the recorder. The GIF covers rows 0:00 and 0:45 and the MCP settings as found; rows 1:45 and 3:00 stay words. |
| `blender-3d` | not asked yet | Open. |
| `world-model` | not asked yet | Open. |

The choices carry the rule that every GIF still needs the owner's named go before publication, and that no secret is on a frame.
Nothing is recorded yet for these four: each is a take to scout and review like the others.

## Progress (2026-11-16)

`genai-playground` is the first of the six with a GIF: `1a4ff89b` publishes take `genai-playground-20261116-183758` on the owner's go of 20:05:27 CET (coordinator's log), before the commit at 20:06:07. The file is 1 046 464 bytes and equal to the take's GIF (SHA-256 `df603fdf6cf0...`, compared by the writer). The take follows the owner's choice "skip the paste": it shows rows 0:00 and 0:45 and the MCP settings as found (`zuno-mcp-gateway` listed, "0 active", no token). Rows 1:45 and 3:00 stay words; the prompt of row 3:00 is untested in the playground. Facts and review: [afternoon evidence](../evidence/wp-289-gif-afternoon-2026-11-16.md).

The other five are not recorded. `maas-portal-api-keys` failed its scout at `enter` (the guard refused the portal's key-list search; nothing was created). `openclaw` scouted 7 of 7 at `d80f25ef` (as relayed). `a2a-delegation-approval` is on `devel`, unscouted. `blender-3d` and `world-model` are not asked yet.

### Owner's decision on `openclaw`, session cleanup (2026-11-16, answered just before 21:01:38 CET)

Given in `zuno-demo-reorg`'s session by an answer to a question with options, and relayed by it (the time is read from its clock right after the answer). The answer: **"Yes, session deleted"**.

- The take asks one question and deletes its own session through the UI's **Delete…** entry. That click is declared.
- The take fails if the session remains after the delete.
- What the assistant may have memorised stays in its memory. This is declared.

### Two failed takes at `feaf7d32` (2026-11-17, as relayed; the writer read the directories)

Neither is retried. Details are in [the afternoon evidence](../evidence/wp-289-gif-afternoon-2026-11-16.md).

- `maas-portal-api-keys` failed before any key was created: the check did not see the model chosen in the Create dialog, which the frame shows is chosen. A bug in the check. Fixed on `devel` as `723c5e24` (coder's `a8afb3a6`); a rescout comes before the next take. The shown-once dialog is still unseen.
- `openclaw` failed after the question was answered: the take did not recognise its own session, which the assistant had retitled, so it did not delete it. Owned sessions went from 6 to 7. The session stays until the owner decides (delete by hand, or leave for a later take). The answer frame holds real Confluence titles; the owner chose "comme guardrails".

### Scouts at `d80f25ef` (as relayed)

- `openclaw`: 7 of 7. The session menu lists Pin session, Mark as unread, Rename…, Fork, Move to group, Archive session and Delete….
- `maas-portal-api-keys`: 6 of 6. The key list was empty. The Create dialog was seen and cancelled. Nothing was created.
- `dify`: 9 of 9. `guardrails`: both paths fine.
- `observability-trace`: the bounded search finds one recent Tekos trace of `consultant-02`, but the click opened Jaeger's Compare page (a selector bug).
- `unifai-agents`: the re-cut was refused once because a caption was too long (64 characters); redone at `2b9f3dfb`.

