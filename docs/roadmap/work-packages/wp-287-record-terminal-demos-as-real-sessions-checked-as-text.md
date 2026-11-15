# WP-287: Record terminal demos as real sessions checked as text

- **State:** Not started
- **ADRs:** [ADR-0618](../../adr/0618-give-every-catalogue-scenario-a-gif-with-real-terminal-sessions-checked-as-text-first.md)
- **Depends on:** [WP-286](wp-286-improve-the-recording-chain-and-reprove-it-on-open-webui.md)
- **Related:** [ADR-0617](../../adr/0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md), [WP-284](wp-284-record-the-open-webui-demo-and-publish-it-as-a-gif.md)
- **Target:** v0.16
- **Estimated files touched:** ~14: a capture driver under `platform/demo/`, a replay page and a generic `terminal` walkthrough under `evaluations/browser/`, the vendored xterm.js with its licence, the text gate, `presenter.py` routing, `demo.yml` of `vault-pki`, tests, one evidence file

> Why: ADR-0618 clauses 3 to 8. A terminal demo is a real session, and the public-repository rule asks that what is shown be checked as text before any pixel exists. The first demo is `vault-pki`: read-only, no budget, nothing to clean up.

## Goal

`make demo record vault-pki` captures a real session, refuses it on a hit of the text gate, hands the transcript to the recording session, then replays it in xterm.js and films it, and the offline cut gives a GIF. Every other pure terminal demo then needs only a cut list and its `record: {allow: [...]}` entries.

## Steps

1. **Capture driver** (Python standard library `pty`): the clean shell of ADR-0618 clause 8, the page's Do commands typed verbatim at 30 to 60 ms per key, the wait for the prompt, the instants typed and done per step, the asciicast v2 file, the allowlist check of every command and the always-refused commands. An offline test with harmless commands. About 1.5 days (the coder's estimate).
2. **Text gate and transcript:** the masks of `readonly.py` as detectors, the deny list of real local values built at capture time, `transcript.txt`, refusal on a hit, never an edit. About 1 day with the routing below.
3. **Replay page and generic walkthrough:** xterm.js vendored under `evaluations/browser/` with its licence and version and loaded from file; the page plays the cast on its own clock and calls a hook at the typed and done instants; a generic `terminal` walkthrough turns them into markers and images. An offline test from a fixture cast. About 1 day.
4. **Routing and guard:** `make demo record` routes a terminal demo to the driver, `demo.yml` takes `record: {allow: [...]}`, the guard summary shows it.
5. **First demo, `vault-pki`,** then its transcript review by the recording session, the filmed replay and the offline cut. Only the names of the ExternalSecrets and stores are shown, never values. The owner's go publishes it.

## Acceptance

- The gate refuses a fixture stream that holds a token, a JWT, a kubeconfig path or the login name, and never edits a stream.
- The replay needs no network and no cluster, and renders the same stream at another size.
- `vault-pki` has a transcript reviewed before rendering, a GIF inside the limits of ADR-0617, and no GIF is published before the owner's named go.
- `python3 platform/demo/consistency.py` (0 problems) and `python3 platform/docs/check_docs.py` pass.
