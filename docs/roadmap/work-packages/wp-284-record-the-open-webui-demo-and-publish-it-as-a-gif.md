# WP-284: Record the Open WebUI demo and publish it as a GIF

- **State:** Not started
- **ADRs:** [ADR-0617](../../adr/0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md)
- **Depends on:** none (Phase 56 is closed)
- **Related:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md), [ADR-0606](../../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md), [WP-285](wp-285-give-the-demo-pages-a-presenters-shape.md)
- **Target:** v0.16
- **Estimated files touched:** ~12: `evaluations/browser/record.mjs`, `record.sh` and `walkthroughs/open-webui.mjs`, `platform/demo/gif.py` and its test, `ansible/demos/open-webui/gif.yml`, the `record` and `gif` verbs in `platform/demo/presenter.py` and the Makefile, `.gitignore`, `lint.yml`, one evidence file, one GIF

> Why: the owner asked on 2026-11-15 for a short silent GIF of the 5-minute version of each demo page. Open WebUI is the
> pilot: it is the one demo whose browser check already signs in. The chain from recording to GIF is proven on one demo
> before it is extended.

## Goal

`make demo record open-webui` plays the 5-minute version in a browser on demo333 and leaves a recording, its markers and
a 40 to 60 second GIF in `~/.cache/zuno/demo/recordings/`; the GIF is sent to the owner; after the owner's named
"go open-webui" it is published at `docs/assets/img/demo/open-webui.gif` and embedded in the page.

## Steps

1. **Recorder** (`evaluations/browser/record.mjs`, `walkthroughs/open-webui.mjs`, `record.sh`; new files only,
   `run.mjs` and `run.sh` untouched). Markers `login`, `home`, `q1-sent`, `q1-done`, `code-picked`, `q2-done`, `tools`
   and `end`, a PNG per marker, `recordVideo` at 1440x900, and the deletion of the chat the take created, by its id,
   after the last marker. The persona password is read only, never printed.
2. **Assembler** (`platform/demo/gif.py`, `ansible/demos/open-webui/gif.yml`): validates the cut list against
   `markers.json` (unknown marker, `to` before `from`, a moment under 2 s, a total outside 40 to 60 s, an unknown page
   step time), computes `fit`, builds the ffmpeg argument list, runs it in the Playwright image, and prints duration, size
   and moments. Hard limit 8 MB.
3. **Verbs and guards.** `make demo record <id>` and `make demo gif <id>`, in `presenter.py`, the Makefile verb list, help
   and completion. `record` asks for the demo id, states its cost and effect, is refused during a freeze and refused
   unless the demo's last `check` passed that day. `gif` is offline. Both run locally, never through AAP.
4. **Tests and CI.** `platform/demo/tests/test_gif.py` (cut list validation, the 2 s minimum, the total, `fit`, the
   ffmpeg arguments from a fixture `markers.json`, with no ffmpeg), a `consistency.py` problem for a GIF above 8 MB,
   `node --check` on the two new `.mjs` files, the `.gitignore` entries for `*.webm` and `recordings/`.
5. **Offline chain.** Run `gif.py` on a synthetic recording: the GIF lasts 40 to 60 s, every moment lasts at least 2 s,
   and a cut list naming an unknown marker or step time is refused.
6. **Live take** (demo333, with the owner's go in that session): `make demo start open-webui`, then
   `make demo record open-webui`. Review every marker PNG for tokens, real names, earlier chat titles and other
   tenants' data. Send the GIF to the owner with its size, duration, moments and the review result. Re-cut with
   `make demo gif open-webui`.
7. **Publication,** only after the owner's named "go open-webui": copy to `docs/assets/img/demo/open-webui.gif`, add one
   embed line at the end of the Introduction, commit alone. Write `docs/roadmap/evidence/wp-284-open-webui-gif-<date>.md`.

## Acceptance

- The take leaves `recording.webm`, `markers.json`, the PNGs and the GIF; `ffprobe` gives 40 to 60 s; the size is 8 MB
  or less; every moment lasts 2 s or more; the chat text and the tool names read at 960 px; sale-01's chat list is the
  same before and after.
- `git status` shows no `.webm`; `make demo browser` is untouched (`run.mjs` has no change).
- The offline tests, `python3 platform/demo/consistency.py` (0 problems) and `python3 platform/docs/check_docs.py` pass.
- No GIF is in the repository before the owner's named go.
