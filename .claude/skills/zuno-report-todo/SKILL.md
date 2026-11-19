---
name: zuno-report-todo
description: Generate "Zuno Todo", the private HTML board of what is left to do in zuno-demo, ranked P0-P3 (demo deadline, version-band order, blockers, hand-set tags). Use when the user asks what remains, what the priorities are, what blocks the demo, or to refresh the todo report.
---

# zuno-report-todo

One self-contained HTML page (English, light/dark), published as a **private Artifact**. Reads the repo only (no `oc`, no cluster figures).
Never commit the output.

## Run

1. `bash .claude/skills/zuno-report-todo/scripts/generate.sh "$(git rev-parse --show-toplevel)" <scratchpad>/zuno-todo.html`
   Add a third argument `--write-priorities` to append proposed tags for open items that have no entry in `priorities.json`.
2. Publish with the Artifact tool, file path `<scratchpad>/zuno-todo.html`, icon `list`. Same path in the same conversation keeps the URL; from a new conversation pass the existing URL (`action: "list"`, title "Zuno Todo").
3. Tell the user: date, counts per tag, how many tags are still "proposed", and any item that waits for an owner decision.

## Pipeline

| Step | File | Output |
|---|---|---|
| ADR + WP (state, deps, notes, band) | `../_zuno-report-common/parse_roadmap.py` (shared with atlas and history) | `raw.json` |
| Rank | `scripts/build_todo.py` + `priorities.json` | `data.json` |
| HTML | `generate.sh` injects `data.json` at `/*DATA*/null` in `assets/template.html` | final HTML |

## Ranking

Tag (P0-P3), then demo blocker, then older band, then number of open items it unblocks (transitive, from the tracker's Depends column).
Open = WP state Not started, Repo work in review, Repo work merged, Operator pending; ADR status Proposed, Accepted, Deferred or Partially implemented.
Proposed tags (when `priorities.json` has no entry): owner decision or go in the note gives P3; started work gives P1; not started with a planned date up to 2026-12-31 gives P2; the rest P3. No item is proposed as P0: set P0 and `demo: true` by hand.

## Maintain by hand

- `priorities.json`: `{"WP-224": {"tag": "P1", "demo": false, "why": "..."}}`. An entry overrides the proposal. Remove an entry to go back to the proposal.
- `PLANNED` in `../_zuno-report-common/common.py`: bands not started yet. Update when a band starts or closes (the atlas has the same rule in its template).
- `demo` and `freeze` dates in `build_todo.py`.
