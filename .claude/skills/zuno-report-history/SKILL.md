---
name: zuno-report-history
description: Generate "Zuno History", the private HTML report of effort per task, version band and week, comparing observed AI-assisted hours (git sessions) with modelled human-only hours, plus a forecast for open work. Use when the user asks how long the project took, what the AI assistant saved, effort per version, or when the remaining work could finish.
---

# zuno-report-history

One self-contained HTML page (English, light/dark), published as a **private Artifact**. Reads the repo and its git log only (no `oc`).
Never commit the output.

## Run

1. `bash .claude/skills/zuno-report-history/scripts/generate.sh "$(git rev-parse --show-toplevel)" <scratchpad>/zuno-history.html`
2. Publish with the Artifact tool, file path `<scratchpad>/zuno-history.html`, icon `chart`. Same path in the same conversation keeps the URL; from a new conversation pass the existing URL (`action: "list"`, title "Zuno History").
3. Tell the user: date, observed hours, modelled human-only hours, share of session hours attributed to no task, and that human-only figures are a model driven by `rates.json`.

## Method (`scripts/effort.py`)

- **AI-assisted time, observed.** Non-merge commits (dependabot excluded) are ordered by time. A gap over `session_gap_min` starts a session; a session counts its span plus `session_lead_h`. Hours are split over the session's commits, then over the WP/ADR ids each commit cites (message or touched path). Commits that cite none go to "unattributed". It is a lower bound: unseen reading or waiting is not counted.
- **Human-only time, modelled.** `hours = base + per_file*files + per_kline*lines/1000 + per_kchar*brief_kchars`, by kind (adr, doc, code, cluster, security; kind chosen from title keywords), clamped to `[min_h, max_h]`. Files and lines are observed from git when the task has commits, else from the brief's "Estimated files touched" and the median of the same kind.
- **Speed-up** per kind = human estimate / observed AI hours, over closed tasks that have both.
- **Forecast.** Open WPs and ADRs: human estimate from the brief, AI estimate = human / speed-up of its kind. Finish date = remaining AI hours / mean weekly hours of the last four full weeks, with a cross-check on WPs closed per week. It ignores waiting for owner decisions; the page counts those.
- Bands come from the first non-retired ADR a WP cites (same rule as the atlas).

## Maintain by hand

- `rates.json`: the human-only model and the session rule. The defaults are assumptions (one senior engineer alone, tests and review included). Calibrate them, then rerun; every human-only figure follows.
- `PLANNED` in `../_zuno-report-common/common.py`: bands not started.
