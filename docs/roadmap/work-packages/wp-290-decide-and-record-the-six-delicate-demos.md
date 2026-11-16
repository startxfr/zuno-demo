# WP-290: Decide and record the six delicate demos

- **State:** Not started
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

## Owner's choices of 2026-11-16 (about 13:35 CET)

Given in `zuno-demo-reorg`'s session by the owner's answers to a question with options, and relayed by it; the writer has not seen the
owner's messages. Four of the six are decided; two are not asked yet.

| Demo | Owner's choice | What it means for the take |
|---|---|---|
| `a2a-delegation-approval` | **Approve, one job per take** | The take clicks Approve. Each take leaves one AAP job that cannot be deleted. The owner's go is given for each take, in the session of the recording (`zuno-demo-reorg-demo333`). |
| `maas-portal-api-keys` | **Create, hide, revoke** | The take creates the key with the key field hidden before the dialog opens, proves the call with the key masked, and revokes the key by its id. The take fails if the revoke fails. |
| `openclaw` | **Like `guardrails`** | The Control UI password is a declared second secret, read at run time. It is never in git, in a log or on a frame. |
| `genai-playground` | **Skip the paste** | The take does not paste the token and shows the saved connection. |
| `blender-3d` | not asked yet | Open. |
| `world-model` | not asked yet | Open. |

The choices carry the rule that every GIF still needs the owner's named go before publication, and that no secret is on a frame.
Nothing is recorded yet for these four: each is a take to scout and review like the others.
