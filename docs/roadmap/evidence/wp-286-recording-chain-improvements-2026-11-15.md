# WP-286: the recording chain re-proved on Open WebUI (2026-11-15)

One scout and one take of the Open WebUI demo with the improved chain of
[ADR-0618](../../adr/0618-give-every-catalogue-scenario-a-gif-with-real-terminal-sessions-checked-as-text-first.md)
clause 9, run by session `zuno-demo-reorg-demo333` on demo333 at `devel` `d819b270`, with the owner's go given in that
session (a scout and a take, one retry allowed; none was needed). Nothing was published from this take.

## Result

| Item | Value |
|---|---|
| Scout | `open-webui-20261115-220546-scout`: status `done`, 6 steps all ok |
| Take | `open-webui-20261115-220632`: `RESULT: PASS`, 8 markers in 24.6 s |
| Chat | one chat created and deleted: `created` holds the chat (kind and id), `cleaned` is true |
| What the persona owns | before 1, after 1, same: true |
| `motion_from` | `home` |
| GIF (in the cache only) | 42.8 s, 960x656, 7 moments, 1 409 885 bytes (1.4 MB), under the 8 MB limit; `open-webui.gif.json` names the take, the cut list `ansible/demos/open-webui/gif.yml` and its blob (`30c97326a2d2...`) |

The comparison of sale-01's chat list (identifier and title, before and after) that `zuno-demo-reorg-demo333` made by
hand, separately, agrees with the recorder's verdict. The size of the GIF is read from `open-webui.gif.json`: 1 409 885 bytes. The
report of the take said 1.3 MB; the file is the source.

### The scout

6 steps: `enter`, `owned` (1 chat owned), `home`, `picker` (button `#model-selector-model-button`; **Zuno Code** is
listed once), `tools` (button `#integration-menu-button`; the menu holds **Tools 1** and the single connection **Zuno
tools**, switched on) and `closed` (the menu is no longer open). The scout lists the controls the take may switch: none
(`changes` is empty), and no request was refused. `scout.json` carries the SHA-256 of the walkthrough file
(`6a8f96be3e0b...`), which `record` compares with the file it is about to run.

### The take

Marker times from `markers.json` (seconds since the start of the recording):

| Marker | t (s) |
|---|---|
| `login` | 0.81 |
| `home` | 8.23 |
| `q1-sent` | 10.34 |
| `q1-done` | 13.25 |
| `code-picked` | 14.7 |
| `q2-done` | 21.73 |
| `tools` | 23.14 |
| `end` | 24.57 |

The take was first reported with slightly different times (login 1.0, home 8.4, end 24.7), up to 0.2 s from the file's;
the file is the source.

## Offline checks at integration

By the coordinator session: `record-offline.sh` 27 of 27, and the platform test files OK (9, then 11 after the later
commits).

## What this proves, and what it does not

It proves that the improved chain runs end to end on the pilot demo: the scout gate, the phases that read what the
persona owns before and after, the list of what a take created, the click guard (no control to switch), and an offline
cut that writes `gif.json`.

Limits:

- Nothing was published from this take, and **no privacy review was done on it**: its GIF was not sent to the owner.
- The detection of a refused model answer and the refusal of a click by the guard were exercised offline only: no refusal
  happened live.
- The scout gate's refusal of a stale walkthrough hash was seen in the tests only.
- One demo, one take.
