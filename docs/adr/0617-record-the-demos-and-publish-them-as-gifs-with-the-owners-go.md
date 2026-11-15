# ADR-0617: Record the demos and publish them as GIFs only with the owner's go, and give every demo page a presenter's shape

- **Status:** Accepted
- **Target:** v0.16
- **Date:** 2026-11-15
- **Decision owners:** Zuno Demo architecture team
- **Amends:** [ADR-0616](0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md) (clause 4: the section order of a catalogue page; the lifecycle section itself is unchanged)
- **Related:** [ADR-0606](0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md), [ADR-0605](0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md), [ADR-0608](0608-keep-the-repository-the-only-source-of-cluster-state.md)

## Context

On 2026-11-15 the 30 scenario pages and 6 workshops of `docs/demo/` were all rehearsed through `make demo`
([ADR-0616](0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)). The owner then asked for two
things: each demo page shows a short silent animation of its 5-minute version, and the pages read better for a
presenter. Open WebUI is the pilot, because it is the one demo whose browser check already signs in.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | No recording exists. | `evaluations/browser/run.mjs` opens one context per check (1440x900) and has no `recordVideo`; the repository holds no `.webm` or `.gif`, and `.gitignore` has no media pattern. |
| F2 | The Open WebUI check does not play the demo. | Its check (`run.mjs`, the `open-webui` entry) signs in as sale-01 and waits for `#chat-input`; it sends no prompt, picks no model and opens no tool list. |
| F3 | The repository is public and keeps its history. | A GIF rewritten at each publication stays in the history; the 40 PNGs of `docs/assets/img/` weigh 48 MB today. |
| F4 | A recording leaves traces. | A scripted take adds a chat to sale-01's history and spends two model answers and one title on sale-01's budget. |
| F5 | The page puts the banner and the ADR and WP references first. | The status banner is the first block of every page, and the Introduction, Personas and Presenter lifecycle sections carry `ADR-NNNN` and `WP-NNN` mentions that a presenter does not need on stage. |
| F6 | The parser does not read the banner or the Introduction. | `platform/demo/catalogue.py` needs `## Presenter lifecycle`, its six `###`, the version sections and their tables; only `platform/demo/scaffold.py` reads the first 30 lines for probe names. |

## Decision

**A demo is recorded by a dedicated scripted walkthrough, post-produced into a short silent GIF, and published only with
the owner's named "go <id>"; every catalogue page takes a presenter's shape, defined once in `docs/demo/README.md`.**

1. **A dedicated recorder.** `make demo record <id>` runs a scripted walkthrough of the demo's 5-minute version in the
   Playwright image already used by `make demo browser`. It is separate from the browser check: the check and the
   rehearsals stay unchanged and spend no extra model budget. For the pilot `evaluations/browser/run.mjs` and `run.sh`
   are not touched; the recorder carries its own copy of the Keycloak sign-in helper. Sharing it is decided at the
   extension, with the owner of that code.
2. **Markers.** The walkthrough writes a timestamped marker at each key moment, and a PNG screenshot of the page at
   each marker (a still is sharper than a frame of the low-bitrate `.webm`). A take leaves `recording.webm`,
   `markers.json` and the PNGs under `~/.cache/zuno/demo/recordings/<id>-<stamp>/`.
3. **The recorder cleans up after itself.** It deletes the chat it created, by its id, after the last marker and outside
   the cut. The `DEMO_CONFIRM` summary says so. If the deletion fails the run is FAILED and prints the chat title. A
   take that sent its first question but could not read the chat id also fails, and says that a chat may remain.
4. **A cut list per demo.** `ansible/demos/<id>/gif.yml` is versioned next to the demo's files. It lists the moments,
   each a still marker or a span from one marker to another, with a hold, a caption of a few words, and optionally a
   page step time (`step: "0:45"`), which `make demo gif` checks against the 5-minute table of the page. A motion
   moment takes `speed: <n>` or `fit: <seconds>`; `fit` computes the speed from the real span of the markers, clamped
   from 1 to 16, so the total stays inside the target on every take. A moment lasts at least 2 seconds, and the total
   is 40 to 60 seconds.
5. **A reproducible assembly.** `make demo gif <id>` assembles the GIF with ffmpeg from the latest recording. It makes
   no cluster call and spends no budget. It runs in the Playwright image by podman, because the workstation has no
   ffmpeg. The GIF is 960 px wide at 8 to 10 images per second with an optimised palette, and its size has a hard
   limit of 8 MB (the aim is 5 MB). The tool refuses a larger file, and `platform/demo/consistency.py` reports a
   published GIF above the limit as a problem.
6. **The `.webm` is never published.** `.gitignore` excludes `*.webm` and the recordings directory.
7. **The owner's go.** The GIF is built outside the repository and sent to the owner with its size, its duration and
   its list of moments. It is copied to `docs/assets/img/demo/<id>.gif`, embedded and committed only after the owner's
   named "go <id>", given in the session that commits. One publication commit holds one GIF; a re-cut stays in the
   cache until the go.
8. **A privacy review before the GIF leaves the workstation.** The recording session reviews every marker image and
   the assembled GIF, because a motion segment shows frames that no marker image covers. The review checks that
   nothing shows: a token or an API key, a session cookie, a Keycloak form with a typed password, a real person's name
   or email, chat content beyond the scripted prompts and their answers, an earlier chat title, or data of another
   tenant. The persona name and the public route host already appear in the pages. The result of the review is in
   the message that sends the GIF to the owner. The walkthrough also names, in `markers.json`, the first marker a
   motion segment may start at (`motion_from`; for Open WebUI, `q1-sent`), and `make demo gif` refuses a motion
   segment that starts before it, so the sign-in is never shown in motion. The login is still taken as a still, on the
   empty form.
9. **Guards.** `make demo record` is a live action: it asks for the demo id (`DEMO_CONFIRM=<id>`) and states its cost
   and effect (the answers spent, the chat created and deleted). It is refused during a freeze, as `rehearse` is, and
   refused unless the demo's last `check` passed that day, so a cold or broken demo is not recorded. `make demo gif` is
   offline and allowed during a freeze. Neither verb goes through AAP.
10. **The shape of a page.** Every scenario page and workshop follows one order: `# title`, `## Introduction` (a
    paragraph and "The message", then the GIF when one exists), `## Personas`, `## Presenter lifecycle`, the version
    sections, `## If something goes wrong`, `## Limits`, `## Appendix A - HLD`, `## Appendix B - LLD`,
    `## References`, and `## Page status` last. `## Page status` holds the status banner unchanged. `## References`
    holds the decisions (ADRs, with their one-line meaning) and the work-package evidence links. The Introduction, the
    Personas and the Presenter lifecycle carry no `ADR-NNNN`, no `WP-NNN` and no link into `docs/adr/` or
    `docs/roadmap/`; a sentence that cited one is reworded so that it still reads. The GIF is embedded as the last
    element of the Introduction.
11. **One text for the contract.** `docs/demo/README.md` holds the contract of a page, and both templates repeat it.
    This record names it as the single text; it amends clause 4 of ADR-0616 only for the position of the sections.
    The lifecycle section and its six `###` stay as ADR-0616 defines them.
12. **Pilot, then rollout.** The pilot is Open WebUI. Its page takes the new shape first, with the scenario template and
    the README contract, and the owner and the team review it with the GIF. The other 29 scenarios, the 6 workshops and
    the workshop template change shape only after the owner's gate, and the page-shape checks of `consistency.py` and
    the probe reading of `scaffold.py` (which then reads `## Page status`) are switched on in the same push as the last
    page. GIFs of the other demos are a later work package, one owner's go per GIF.
13. **The generators follow the page.** The tools that write the rehearsal result into a page's status banner and into
    the README write into `## Page status` once a page has it, and into the top banner before.

## Alternatives considered

- **Record the browser check itself.** It spends no extra budget, but it plays no demo (F2) and its change would
  touch the code the freeze protocol relies on. Rejected: a separate walkthrough.
- **Publish a video.** A `.webm` or an MP4 weighs more, does not play inline in a repository page and cannot be
  reviewed as a file. A short silent GIF renders on GitHub as an image.
- **Git LFS or an external host for the GIFs.** Rejected: the repository is the only source (ADR-0608), and a link to
  another host breaks the page when it moves. The 8 MB limit and one commit per GIF bound the weight (about 290 MB
  for 36 demos, to be revisited at the extension).
- **Keep the banner at the top and only add the GIF.** A presenter reads the status banner before every show, but it is
  a long record of prerequisites and rehearsals; it belongs with the page's status, at the end.
- **Leave the chat in sale-01's history.** Deleting is a change made by the recorder to its own object, by its id; leaving
  it would show an earlier chat title on later takes.

## Consequences

- Two new verbs, `record` and `gif`, in `make demo`; new files under `evaluations/browser/` and one cut list per
  recorded demo.
- A recording spends two model answers and one title on sale-01's budget, and a take needs a warm model: the runbook
  is `make demo start <id>`, then `record`.
- Every page changes shape once, in the rollout; links to the old anchors of a page do not move, because the heading
  names stay.
- The pilot page has the new shape while the other pages keep the old one; the README says so until the rollout.

## Security considerations

- The `.webm` can show tokens and earlier chat titles. It stays in the user's cache and is never published; the PNGs
  are reviewed before they leave the workstation (clause 8).
- The walkthrough reads the persona's password at run time from the Vault-backed Secret through `oc`, passes it to the
  container by environment and never prints it.
- The repository is public: a GIF is published only after the owner's go, and removing one later leaves it in the
  history. That is why a re-cut is not committed.
- `record` creates and deletes one chat of one persona; it makes no other change to the cluster.

## Operational considerations

- The recordings live under `~/.cache/zuno/demo/recordings/` on the presenter's workstation and are not backed up.
- Podman and the cached Playwright image are the only tools needed; the workstation needs no ffmpeg.
- The recording runs on demo333 with the owner's named go in the session that runs it, outside a freeze.

## Work packages

- [WP-284](../roadmap/work-packages/wp-284-record-the-open-webui-demo-and-publish-it-as-a-gif.md) (the recording chain, the
  Open WebUI pilot, the owner's go and the publication).
- [WP-285](../roadmap/work-packages/wp-285-give-the-demo-pages-a-presenters-shape.md) (the page shape: the pilot on three
  files, then the rollout after the owner's gate).

## Update 2026-11-15 (WP-284): what the recording chain does as built

The build of WP-284 fixes four details of clauses 3 to 5. The clauses stay as decided; this is a dated precision.

- **Clause 4, `fit`:** the speed is the span of the markers divided by the `fit` seconds, clamped from 0.5 to 16 (not
  from 1 to 16). A fast answer is slowed down rather than padded: `fit` never adds a frozen frame, and `hold` is the
  only freeze of a moment.
- **Clause 5, captions and size:** the caption is drawn in a band under the picture, not over it, so it hides nothing.
  The GIF is 960x656: a 960x600 picture and a 56 px band.
- **Clause 3, a scout mode:** `record.sh <id> --scout` signs in and opens the menus, sends no prompt, makes no model
  call and creates no chat, and it refuses any chat request that is not a GET. It is run before a first take to check
  the selectors without spending budget.
- **The walkthrough never clicks a tool switch:** it only opens the menus and shows the state the persona has.
