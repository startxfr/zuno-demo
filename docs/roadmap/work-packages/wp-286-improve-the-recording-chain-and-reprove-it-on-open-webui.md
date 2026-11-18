# WP-286: Improve the recording chain and re-prove it on Open WebUI

- **State:** Done (2026-11-15)
- **ADRs:** [ADR-0618](../../adr/0618-give-every-catalogue-scenario-a-gif-with-real-terminal-sessions-checked-as-text-first.md)
- **Depends on:** [WP-284](wp-284-record-the-open-webui-demo-and-publish-it-as-a-gif.md) (Done)
- **Related:** [ADR-0617](../../adr/0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md), [WP-284](wp-284-record-the-open-webui-demo-and-publish-it-as-a-gif.md)
- **Target:** v0.16
- **Estimated files touched:** ~12: `evaluations/browser/record.mjs`, a shared helper file and the Open WebUI walkthrough, `platform/demo/gif.py`, `presenter.py`, their tests, one evidence file

> Why: the pilot showed what every later take needs. The changes below are a contract that all later walkthroughs depend on, so they land first. The effort figures are the coder's estimates, not measures.

## Goal

The chain of WP-284 carries the rules of ADR-0618 clause 9, and Open WebUI is recorded again with it to prove that nothing regressed.

## Steps

1. **`created` and `cleaned`.** `markers.json` carries `created: [{kind, id}]` (no titles: they are private) and `cleaned: true|false|null` (null when nothing was created) in place of `chat_deleted`; `gif.py` refuses `cleaned: false`. Old takes are cache only. The coder proposes `motion_from` = `home` for Open WebUI once the review accepts it (to confirm). About 2 h of the coder and 1 h of the assist.
2. **A shared helper file** for the recorder side (`evaluations/browser/walkthroughs/_helpers.mjs`, never imported by `run.mjs`): first visible element, really on screen, new text, buttons, API calls in the page, answer-finished polling, the Keycloak and the OpenShift sign-ins. A pure refactor proven offline. About half a day.
3. **Phases instead of one run:** `enter` (sign-in to the first screen), `owned` (what the persona owns, read in its own session), `run` and `cleanup`. The recorder calls `owned` after `enter` and after `cleanup` and fails the take when the two lists differ, printing the difference to the local log only. It sees only what the application's API lists, not a server-side run log. About half a day, then about 1 h per walkthrough.
4. **A scout that is mandatory and richer.** `--check` refuses a walkthrough without a scout; each scout step dumps, for the elements a menu added, the tag, id, role, aria attributes, state and first classes (text cut at 60 characters); `scout.json` carries the SHA-256 of the walkthrough file; `record` refuses a take without a finished scout for the current file. About 3 h of the coder and 2 h of the assist.
5. **"Never click a control that changes the persona's settings"** written in the helper header and the runbook, and enforced where cheap: the helpers' click refuses switches, checkboxes and submit buttons outside the prompt box unless the walkthrough lists them in an exported `changes` list, which `--check` prints and the guard summary shows. About 2 h.
6. **Re-proof.** One scout and one take of `open-webui` with the owner's go in the demo333 session, with a privacy review that states how many frames it looked at and covers every marker image before the go.

## Acceptance

- The offline tests of the recorder, `gif.py` and the presenter pass, and `node --check` passes on the new files.
- The re-proof take of Open WebUI passes, lists what it created and cleaned, and the persona's list is the same before and after.
- `python3 platform/demo/consistency.py` (0 problems) and `python3 platform/docs/check_docs.py` pass.
- No GIF is published without the owner's named go.

## Result (2026-11-15)

The chain carries the rules of ADR-0618 clause 9 and Open WebUI was re-proved live on demo333, with the owner's go: a
scout of 6 steps (status done, no control to switch, no refused request), then a take that passed in 24.6 s, created one
chat and cleaned it, left what the persona owns unchanged (1 before, 1 after) and cut into a 42.8 s, 1.4 MB GIF in the
cache ([evidence](../evidence/wp-286-recording-chain-improvements-2026-11-15.md)). Limits, stated in the evidence: nothing
published and no privacy review of this take, the refusal paths exercised offline only, one demo.
