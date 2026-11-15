# ADR-0618: Give every catalogue scenario a GIF, with real terminal sessions checked as text before any pixel exists

- **Status:** Accepted
- **Target:** v0.16
- **Date:** 2026-11-15
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0617](0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md) (extended: this record applies its chain to every scenario and adds terminal demos; it supersedes nothing), [ADR-0616](0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md), [ADR-0605](0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md)

## Context

The Open WebUI pilot of [ADR-0617](0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md) produced the first
published GIF on 2026-11-15 (42.9 s, 1.3 MB). The owner then asked for a GIF of every scenario, terminal demos
included. The 30 scenarios of `docs/demo/` are not alike: most play in a browser, several play in the presenter's
terminal, some mix both, and some are told with stills or cannot be recorded without a side effect.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | The pilot's chain records a browser only. | `evaluations/browser/record.mjs` drives one Playwright context; the Playwright image has no `oc`, no `gcc` and no pty server. |
| F2 | The pilot's privacy review had a gap. | The review of the first GIF looked at 29 of 429 frames, and the eight marker images were opened only after publication ([evidence](../roadmap/evidence/wp-284-open-webui-gif-2026-11-15.md)). |
| F3 | The engine does not keep what a step printed. | `platform/demo/runner.py` writes the step results to a temporary directory and deletes it; what survives is the Ansible log and the rehearsal report. |
| F4 | A terminal demo needs the presenter's session. | The Do commands use `oc` and the presenter's kubeconfig, which exist on the workstation and not in the container that runs the browser. |
| F5 | Some takes change or leave things behind. | A take of the a2a demo would click Approve and start an AAP job; the MaaS demo creates an API key shown once; a Dify run log, a Tempo trace and a model-call metric cannot be deleted by the user. |
| F6 | Some pages claim a screen the take cannot show. | On Open WebUI 0.12.5 the tools menu shows one connection, not tool names ([WP-284 evidence](../roadmap/evidence/wp-284-open-webui-gif-2026-11-15.md)); other rows may say the same. |
| F7 | There is no read of a persona's remaining budget. | The only read is an `oc exec` into Redis in `zuno-auth` (the ai-gateway ledger keys, [ADR-0593](0593-key-the-per-user-quota-and-telemetry-by-persona-across-experiences.md)) or into Limitador. Standard personas have 10M tokens per 24 hours, and sale-01 had used 3,520 that day. |

## Decision

**Every scenario of the catalogue gets a GIF built by the chain of ADR-0617, and a terminal demo is a real terminal
session captured as text, checked as text, then replayed and filmed. The owner's named "go <id>" still decides each
publication, and nothing else.**

1. **Scope.** All 30 scenarios get a GIF of their 5-minute version, terminal demos included, within the limits of
   ADR-0617 (40 to 60 s, 960 px, 8 MB). The 6 workshops get none for now: a workshop page links the GIFs of its
   scenarios. A montage cut from the scenarios' approved takes may be decided later and needs no new take.
2. **The delicate demos come last.** Six demos are decided by the owner one by one, after the others: `blender-3d`,
   `world-model`, `a2a-delegation-approval` (Approve starts an AAP job), `maas-portal-api-keys` (creates a key),
   `openclaw` (a second secret) and `genai-playground` (a token pasted on screen). Until the owner decides, they are
   not recorded.
3. **A terminal demo is captured as bytes and timing.** The driver runs on the presenter's workstation: a real bash in a
   real pty types the page's Do commands verbatim, at a human pace, waits for the prompt, and runs them against
   demo333. The session is written as an asciicast v2 file (one JSON line per chunk), with the instant each command was
   typed and the instant its prompt came back. Nothing is retyped from the engine's results.
4. **A text gate before any pixel.** The captured stream, with its escape codes removed, is checked as text: the
   existing masks of `platform/demo/readonly.py` as detectors (bearer tokens, JWTs, `sha256~` tokens, password, secret
   and token values, URL userinfo) and a deny list built at capture time from the real local values (the presenter's
   token, read privately outside the pty, the kubeconfig path, the home directory, the login name, the workstation
   host name). A hit refuses the take. The stream is never edited, so what is rendered is what happened.
5. **The transcript is reviewed by the recording session.** After the automatic gate, the recording session reads the
   text transcript, one file instead of several images, before anything is rendered. The owner's go stays for the
   publication only.
6. **Replay in a terminal emulator, then film.** The stream is played at its own timing in xterm.js inside the recorder's
   Playwright page, and the page is filmed, with markers at the typed and done instants of each step
   (`<MM-SS>-typed`, `<MM-SS>-done`). xterm.js is vendored, pinned by content, with its licence, under
   `evaluations/browser/`, and loaded from file: no network at record or cut time, and `evaluations/browser/package.json`
   stays untouched. No credential ever enters a container: the container receives one text file.
7. **What may be typed.** Each Do command first passes `platform/demo/readonly.py`. A command that the allowlist does
   not accept, such as a `make` row, is typed only when the demo lists it in `ansible/demos/<id>/demo.yml` under
   `record: {allow: [...]}`; the guard summary shows the list. `oc whoami -t`, `oc config view`, `env` and any read
   of a kubeconfig are refused whatever the list says. A refused command is not typed and the take fails naming it.
8. **A clean shell.** `env -i` with only `PATH`, `TERM`, `LC_ALL=C.UTF-8`, the `KUBECONFIG` path (never typed or echoed)
   and `PYTHONUSERBASE`; `HOME` is an empty temporary directory; `bash --noprofile --norc` with the prompt `$ `,
   no history, the repository root as the working directory and a 100x30 window. A command whose value hides a
   substitution such as `$(oc whoami -t)` stays runnable and its value is never echoed.
9. **Rules learnt on the pilot apply to every browser take.**
   - A scout is mandatory before the first take of a walkthrough and after its file changes; `record` refuses a take
     without a finished scout for the current file.
   - The recorder compares what the persona owns before and after the take, and the take fails when the two lists
     differ. A take lists what it created and whether it cleaned it up.
   - A walkthrough never clicks a control that changes the persona's settings unless it declares the control, and
     the guard summary shows the declaration.
   - The privacy review covers every marker image and a sample of the frames of the assembled GIF, and states the
     number of frames it looked at.
10. **Server-side traces are accepted and stated.** A take leaves things nobody can delete: Dify run logs, Tempo traces,
    model-call metrics, AAP job records of read-only navigation. They are normal use and the guard summary of the demo
    says so. Everything that can be deleted by its id is deleted, and the take fails when it cannot.
11. **A take that mixes pages has several videos.** A take may hold more than one video (a two-persona demo, a terminal
    page and a console); a marker names its video, and the GIF cut takes each moment from the right one.
12. **The budget is not read.** `make demo record` does not read a persona's remaining budget: a pod exec next to a
    password file is not worth it for a two-answer take. The runbook says not to record a persona right after the
    quotas demo or a stress-test persona, and a refused answer fails the take visibly.
13. **A page claims only what the take shows.** A row whose "You should see" cannot appear on screen is settled before its
    take, so that the page and the GIF agree (the tools menu of Open WebUI is the example).
14. **Order.** The chain improvements come first, with a re-proof on Open WebUI. Then the terminal chain and `vault-pki`
    (the first terminal demo, read-only, no budget, no cleanup), then `kagent`, `unifai-live-rag`,
    `identity-personas` (several videos, nothing created) and `model-serving-llmd-mig` (a terminal and a console), then
    the repeats of a proven pattern, then the six delicate demos.

## Alternatives considered

- **A terminal page re-typeset from the engine's results.** Cheaper and easy to check, but the owner refused it: it is
  not a real terminal.
- **Film a real terminal live** (a pty server and xterm.js filmed as it runs, or `ttyd`). The shell must run on the
  host, so a listening port carries a shell reachable from the browser, or `oc` and the kubeconfig are mounted next to
  a browser. A pty module or `ttyd` is a new supply-chain item, and a secret can be found only after the pixels exist.
- **Stills only** (drawn with ffmpeg `drawtext`). Brittle for multi-line monospace text, and there is no typing. It stays
  the fallback for demos that cannot be taken.
- **Read the budget before a take.** There is no endpoint, and the only read is a pod exec (F7). Rejected: the runbook
  and a visible failure are enough.
- **A GIF for each workshop now.** It would need a new take and a new review of pixels; a montage of approved takes
  can come later.
- **Record the six delicate demos like the others.** Rejected: each one changes the cluster, shows a secret or needs a
  desktop application.

## Consequences

- Five work packages, WP-286 to WP-290, in Phase 57; the pilot's chain changes (`created`/`cleaned`, phases, scout).
- The engine keeps what a recording needs (the transcript of a terminal take); it keeps nothing for a rehearsal.
- A terminal GIF shows the session as it was played: its pauses and its output, shortened by the cut only.
- A published GIF stays in the history of a public repository; the 8 MB limit bounds the weight (36 GIFs at most about
  290 MB, to be revisited with the owner).

## Security considerations

- A terminal take runs real commands on demo333 with the presenter's session, so the allowlist and the explicit
  `record: {allow: [...]}` list are the only door; the always-refused commands cannot be allowed.
- The text gate runs before any rendering and can only refuse, never edit.
- A browser take reads the persona's password at run time and never prints it; a walkthrough that needs a second secret
  declares it, and the owner decides each one.
- The repository is public: nothing is published without the owner's named go.

## Operational considerations

- Recordings and transcripts stay in `~/.cache/zuno/demo/recordings/` on the presenter's workstation.
- A take needs the demo to be installed and its last `check` passed that day; it is refused during a freeze.
- Every sign-in flow other than the Keycloak form, and every delete-by-id call outside Open WebUI, is unverified until a
  scout of that demo.

## Work packages

- [WP-286](../roadmap/work-packages/wp-286-improve-the-recording-chain-and-reprove-it-on-open-webui.md) (the chain
  improvements and the re-proof on Open WebUI).
- [WP-287](../roadmap/work-packages/wp-287-record-terminal-demos-as-real-sessions-checked-as-text.md) (the terminal chain
  and `vault-pki`).
- [WP-288](../roadmap/work-packages/wp-288-record-the-first-batch-of-browser-demos.md) (`kagent`, `unifai-live-rag`,
  `identity-personas`, `model-serving-llmd-mig`).
- [WP-289](../roadmap/work-packages/wp-289-record-the-repeats-of-the-proven-patterns.md) (the repeats, including the demos
  told with stills).
- [WP-290](../roadmap/work-packages/wp-290-decide-and-record-the-six-delicate-demos.md) (the six delicate demos).

## Update 2026-11-15 (WP-287): what the capture driver does as built

The build of the capture driver fixes six details of clauses 3 to 8. The clauses stay as decided; this is a dated
precision.

- **Clause 4, where the checks live:** the pattern masks used as detectors are in `platform/demo/probe_rows.py`, not in
  `readonly.py`. The deny list of real local values (the token, the kubeconfig path, `HOME`, the login name as a whole
  word, the host name, the variables of a step whose name looks like a credential) runs inside the capture process, in
  memory, and on a hit no cast is written. The pattern detectors and `transcript.txt` run on the written cast.
- **Clause 8, the prompt:** the prompt shows `$ ` and carries one invisible OSC sequence holding the last exit code,
  which the driver needs to know that the prompt is back. It is part of the real bytes of the session; the transcript
  strips it like the other escape codes.
- **Clause 7, refusals:** every command of the demo is checked before the shell starts. Besides the four commands the
  clause names, the driver never types `printenv`, `set`, `export`, `declare`, nor a command that expands `$HOME`,
  `$PATH` or `$PYTHONUSERBASE`.
- **A failing command:** a command that ends with a non-zero exit code fails the take. An entry for a command that may
  fail is not built yet.
- **Clause 6, markers:** one `typed` and one `done` marker per row, and the driver sends Ctrl-L between rows.
