# WP-287: the `vault-pki` terminal demo recorded and published (2026-11-15)

Two takes of the `vault-pki` demo as a real terminal session, as in
[ADR-0618](../../adr/0618-give-every-catalogue-scenario-a-gif-with-real-terminal-sessions-checked-as-text-first.md)
clauses 3 to 8. The takes were run by session `zuno-demo-reorg-demo333` on demo333 with the owner's go. The owner saw
the GIF and gave the named "go vault-pki" in that session. The GIF is published on `devel` in commit `afb13dae`.

## Result

| Item | First take | Second take (published) |
|---|---|---|
| Directory under `~/.cache/zuno/demo/recordings/` | `vault-pki-20261115-221130` | `vault-pki-20261115-224743` |
| Window of the captured shell | 100 columns x 30 rows | 136 columns x 30 rows, 15 px font |
| Commands typed | 6 in 4 steps, all `rc` 0 | 6 in 4 steps, all `rc` 0 |
| Text gate (`gate.json`) | `pass`, no hit, 76 lines | `pass`, no hit, 76 lines |
| Markers | 10 in 36.9 s | 10 in 36.6 s |
| `created`, `cleaned`, `owned` | `[]`, null, null | `[]`, null, null |
| GIF | 2 256 276 bytes, 42.0 s, 960x686 | 1 286 523 bytes, 42.0 s, 960x514 |

Both GIFs have 5 moments at 10 frames per second, from the cut list `ansible/demos/vault-pki/gif.yml` (blob `c8e79d7c871a...`).
The moments follow the page's 5-minute table: 0:00, 1:00, 2:15 and 3:15, then a still of the last screen (4:15).

The published file is `docs/assets/img/demo/vault-pki.gif`. Its SHA-256 on `devel` is `c2f1959663c1...`. It is the same
as the cached cut of the second take. The embed is the last element of `## Introduction` in
`docs/demo/scenarios/foundation/vault-pki.md`.

### The first take and why it was redone

At 100 columns the tables of `oc get` wrapped and were hard to read. The first GIF was not published. The window became
a setting of the demo: `record:` in `ansible/demos/vault-pki/demo.yml` now carries `cols: 136` and `rows: 30`, and the
capture checks them (commits `98190dae` and `04b1b6b6`, with a cut that has no long still). The second take used that
window and its cast was replayed at the same size, with no change to what the session had printed.

### What the session ran

Four steps (0:00, 1:00, 2:15, 3:15) and six read-only `oc get` commands, typed verbatim from the page's Do cells at a
clean prompt: the Vault pods and their seal state, the ExternalSecrets counted by status and listed for one namespace,
the SecretStores and the ClusterSecretStores, and the certificates issued by Let's Encrypt and by the Vault issuer.
`terminal-steps.json` holds the instants typed and done of each command. Only object names and states are shown, never
a value.

### The review

The review was done by `zuno-demo-reorg-demo333` (relayed by `zuno-demo-reorg`; I did not repeat it):

- `transcript.txt` (76 lines) was read in full before anything was rendered.
- The 10 marker images of the second take were opened one by one.
- 21 of the 420 frames of the assembled GIF were sampled.
- Nothing was found that should not be public.

`zuno-demo-reorg` opened one marker image (`00-00-done.png`) and checked the published file against the cached cut.

## Limits

- The text is small at 960 px. A character is about 7 px wide. It reads on a laptop and is small on a phone.
- The output is real and was left as it was. One certificate of the cluster's mesh expires on the day of the take, and
  one column (`STORE`) is empty in the ExternalSecrets listing.
- `transcript.txt` holds a stray space where the pty wrapped a typed command. It is cosmetic and is with the assist.
- One terminal demo is proven. `record.allow` is empty, so the path of an allowed `make` row was not exercised live.
- The refusal of the text gate (a hit refuses the take) was proven offline only. The two live takes had no hit.
- The refusals of always-refused commands were not exercised in these takes.
- The privacy review is a sample (the whole transcript, every marker image, 21 of 420 frames), not every frame.
- No persona budget was used and nothing was created on the cluster.

ADR-0618 stays Accepted: WP-288, WP-289 and WP-290 are open.
